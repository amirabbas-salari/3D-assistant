"""Ask the LiveKit Inference gateway why it rejects STT/TTS requests.

The agent only ever sees ``APIStatusError('Invalid response status (429)')``,
which hides the reason: an exhausted Build-plan allowance and a burst of
concurrent connections produce the same message. This script opens the same
STT and TTS WebSockets the agent opens, with the same credentials, and prints
the gateway's own answer, including the response body and quota headers.

Usage (from the project root, with the same .env the agent uses):

    python scripts/check_inference.py
    python scripts/check_inference.py --connections 3   # open three in a row

Exit code is 0 when the gateway accepts, 1 when it rejects, so it can be used
in a quick smoke test before starting the agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

QUOTA_HEADER_PREFIXES = ("x-livekit-inference-", "x-ratelimit-", "retry-after")


def _gateway_helpers():
    """Import the gateway plumbing lazily.

    With ``SPEECH_PROVIDER=direct`` no LiveKit project credentials are needed, so
    the script must not fail on these imports before it can say so.
    """
    from livekit.agents.inference._utils import (
        get_default_inference_url,
        get_inference_headers,
    )

    return get_default_inference_url, get_inference_headers


def _token() -> str:
    from livekit.api import AccessToken

    api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise SystemExit("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in .env")

    import datetime

    from livekit import api

    grant = api.access_token.InferenceGrants(perform=True)
    return (
        AccessToken(api_key, api_secret)
        .with_identity("inference-diagnostic")
        .with_inference_grants(grant)
        .with_ttl(datetime.timedelta(seconds=300))
        .to_jwt()
    )


def _ws_url() -> str:
    get_default_inference_url, _ = _gateway_helpers()
    base = get_default_inference_url()
    return base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)


async def _probe(
    session: aiohttp.ClientSession, kind: str, payload: dict, headers: dict
) -> dict:
    """Open one gateway connection and report exactly what came back."""
    url = f"{_ws_url()}/{kind}"
    result: dict = {"kind": kind, "url": url}
    try:
        async with session.ws_connect(url, headers=headers) as ws:
            await ws.send_str(json.dumps(payload))
            # The gateway rejects with an HTTP status during the handshake; a
            # successful upgrade answers with a JSON message instead.
            msg = await asyncio.wait_for(ws.receive(), timeout=10)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                result["status"] = "accepted"
                result["first_message"] = data.get("type", str(data)[:200])
            else:
                result["status"] = f"unexpected {msg.type.name}"
    except aiohttp.WSServerHandshakeError as exc:
        result["status"] = "rejected"
        result["http_status"] = exc.status
        result["reason"] = exc.message
        body = ""
        try:
            body = await exc.response.text()
        except Exception:  # pragma: no cover - body is best effort
            body = "<unreadable>"
        result["body"] = body[:800]
        result["headers"] = {
            k: v
            for k, v in exc.headers.items()
            if any(k.lower().startswith(p) for p in QUOTA_HEADER_PREFIXES)
        }
    except asyncio.TimeoutError:
        result["status"] = "timed_out"
    except Exception as exc:  # pragma: no cover - network level failures
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connections", type=int, default=1, help="how many STT and TTS connections to open")
    parser.add_argument("--stt-model", default=os.getenv("LIVEKIT_STT_MODEL", "deepgram/nova-3"))
    parser.add_argument("--stt-language", default=os.getenv("LIVEKIT_STT_LANGUAGE", "fa"))
    parser.add_argument("--tts-model", default=os.getenv("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-tts"))
    parser.add_argument("--tts-voice", default=os.getenv("LIVEKIT_TTS_VOICE", "Charon"))
    parser.add_argument("--tts-language", default=os.getenv("LIVEKIT_TTS_LANGUAGE", "fa"))
    args = parser.parse_args()

    provider = (os.getenv("SPEECH_PROVIDER", "inference") or "inference").strip().lower()
    direct = provider in {"direct", "byok", "provider", "own-keys"}
    if direct:
        # The agent is not using the gateway at all: its 429s cannot happen, and
        # probing the gateway would only be confusing. Check the keys instead.
        missing = [
            name
            for name in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY")
            if not (os.getenv(name) or "").strip()
        ]
        print("SPEECH_PROVIDER=direct: STT and TTS bypass the LiveKit gateway.")
        if missing:
            print(f"❌ missing in .env: {', '.join(missing)}")
            print("   Add them, or set SPEECH_PROVIDER=inference to go back to the gateway.")
            return 1
        print("✅ DEEPGRAM_API_KEY and GOOGLE_API_KEY are present.")
        print("   LiveKit Inference quota is irrelevant on this path; a 401/403 in the agent")
        print("   log would mean a key is wrong or its API is not enabled on that account.")
        return 0

    _, get_inference_headers = _gateway_helpers()
    token = _token()
    headers = {
        **get_inference_headers(),
        "Authorization": f"Bearer {token}",
    }
    stt_payload = {
        "type": "session.create",
        "model": args.stt_model,
        "settings": {
            "sample_rate": "16000",
            "encoding": "pcm_s16le",
            "language": args.stt_language,
            "extra": {},
        },
    }
    tts_payload = {
        "type": "session.create",
        "model": args.tts_model,
        "voice": args.tts_voice,
        "language": args.tts_language,
        "sample_rate": "24000",
        "encoding": "pcm_s16le",
        "extra": {},
    }

    print(f"gateway: {_ws_url()}")
    print(f"stt: {args.stt_model} ({args.stt_language}) · tts: {args.tts_model} voice={args.tts_voice} ({args.tts_language})")

    failures = 0
    async with aiohttp.ClientSession() as session:
        probes = []
        for _ in range(max(1, args.connections)):
            probes.append(_probe(session, "stt", stt_payload, headers))
            probes.append(_probe(session, "tts", tts_payload, headers))
        results = await asyncio.gather(*probes)

    for result in results:
        if result["status"] == "accepted":
            print(f"\n✅ {result['kind']}: accepted (first message: {result['first_message']})")
            continue
        failures += 1
        print(f"\n❌ {result['kind']}: {result['status']}")
        if "http_status" in result:
            print(f"   HTTP {result['http_status']} {result.get('reason', '')}".rstrip())
        if result.get("body"):
            print(f"   body: {result['body']}")
        if result.get("headers"):
            print(f"   quota headers: {json.dumps(result['headers'], indent=2)}")
        if result.get("error"):
            print(f"   error: {result['error']}")

    if failures:
        rejected = [r for r in results if r["status"] == "rejected"]
        if rejected:
            codes = sorted({r.get("http_status") for r in rejected})
            print(
                f"\nThe gateway rejected {len(rejected)} connection(s) with HTTP {codes}. "
                "Compare the body and headers above with LiveKit Cloud → Settings → Project "
                "(Build plan: 5 concurrent STT and 5 concurrent TTS). A 429 whose body names an "
                "allowance means the monthly quota is used up; a bare 429 usually means too many "
                "concurrent connections are already open."
            )
        else:
            print(
                "\nThe gateway could not be reached from here. This is a network, proxy or DNS "
                "problem on this machine, not a quota problem: fix connectivity first (the agent "
                "needs outbound HTTPS/WSS to agent-gateway.livekit.cloud)."
            )
        return 1

    print("\nAll connections were accepted; if the agent still fails, check it uses the same .env.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
