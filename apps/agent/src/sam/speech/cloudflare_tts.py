"""Cloudflare Workers AI TTS via elevenlabs/eleven-v3.

Uses the REST endpoint:
  POST https://api.cloudflare.com/client/v4/accounts/{id}/ai/run
  { model: "elevenlabs/eleven-v3", input: { text, voice_id, output_format, ... } }
→ { result: { audio: "https://..." } }  (mp3 URL)

Then downloads the audio URL and emits PCM frames via AudioEmitter.

Non-streaming (ChunkedStream). Wrapped by SDK StreamAdapter for sentence-level streaming.
"""

from __future__ import annotations

import os
import asyncio
import json

try:
    import httpx as _httpx  # type: ignore
except ImportError:
    import httpx2 as _httpx  # type: ignore  # livekit's alias

from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

SAMPLE_RATE = 24000
NUM_CHANNELS = 1

# Default voice_id from Cloudflare docs example — user can override via env
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL = "elevenlabs/eleven-v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class CloudflareTTS(tts.TTS):
    def __init__(
        self,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        model: str | None = None,
        voice_id: str | None = None,
        output_format: str | None = None,
        language_code: str | None = None,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=NUM_CHANNELS,
        )
        self._account_id = (account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")).strip()
        self._api_token = (api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")).strip()
        self._model = (model or os.getenv("CLOUDFLARE_TTS_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        # voice_id can be CLOUDFLARE_TTS_VOICE_ID or ELEVENLABS_VOICE_ID
        self._voice_id = (
            voice_id
            or os.getenv("CLOUDFLARE_TTS_VOICE_ID", "")
            or os.getenv("ELEVENLABS_VOICE_ID", "")
            or os.getenv("CLOUDFLARE_TTS_VOICE", "")
        ).strip() or DEFAULT_VOICE_ID
        self._output_format = (output_format or os.getenv("CLOUDFLARE_TTS_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT)).strip() or DEFAULT_OUTPUT_FORMAT
        self._language_code = (language_code or os.getenv("CLOUDFLARE_TTS_LANGUAGE_CODE", "")).strip() or None

        if not self._account_id or not self._api_token:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN required for Cloudflare TTS")

        self._http = _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
            follow_redirects=True,
            limits=_httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "cloudflare"

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        return CloudflareChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        await self._http.aclose()


class CloudflareChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: CloudflareTTS, input_text: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: CloudflareTTS = tts  # type: ignore

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        text = self.input_text.strip()
        if not text:
            output_emitter.initialize(
                request_id="",
                sample_rate=self._tts.sample_rate,
                num_channels=NUM_CHANNELS,
                mime_type="audio/pcm",
                stream=False,
            )
            output_emitter.flush()
            return

        # Call Cloudflare Workers AI
        url = f"https://api.cloudflare.com/client/v4/accounts/{self._tts._account_id}/ai/run"
        payload: dict = {
            "model": self._tts._model,
            "input": {
                "text": text,
                "voice_id": self._tts._voice_id,
                "output_format": self._tts._output_format,
            },
        }
        # Only add optional fields if set
        if self._tts._language_code:
            payload["input"]["language_code"] = self._tts._language_code

        headers = {
            "Authorization": f"Bearer {self._tts._api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self._tts._http.post(url, json=payload, headers=headers)
        except _httpx.TimeoutException as e:
            raise APITimeoutError() from e
        except Exception as e:
            raise APIConnectionError() from e

        if resp.status_code != 200:
            try:
                body = resp.text
            except Exception:
                body = ""
            raise APIStatusError(
                f"Cloudflare TTS HTTP {resp.status_code}: {body[:500]}",
                status_code=resp.status_code,
                request_id=resp.headers.get("cf-ray", ""),
                body=body,
            )

        try:
            data = resp.json()
        except Exception as e:
            raise APIStatusError(f"Cloudflare TTS invalid JSON: {resp.text[:500]}", status_code=200, request_id="", body=resp.text) from e

        # Cloudflare returns { result: { audio: "https://..." } } or sometimes { result: "https://..." }
        result = data.get("result")
        audio_url: str | None = None
        if isinstance(result, dict):
            audio_url = result.get("audio") or result.get("url") or result.get("audio_url")
        elif isinstance(result, str):
            audio_url = result

        if not audio_url or not isinstance(audio_url, str):
            # Some models return base64 audio directly
            # Try alternative fields
            if isinstance(result, dict) and "audio" in result:
                audio_url = result["audio"]
            else:
                raise APIStatusError(f"Cloudflare TTS no audio URL: {json.dumps(data)[:800]}", status_code=200, request_id="", body=json.dumps(data))

        # If audio is base64, handle directly; else download URL
        audio_bytes: bytes | None = None
        if audio_url.startswith("data:"):
            import base64
            try:
                audio_bytes = base64.b64decode(audio_url.split(",", 1)[1])
            except Exception as e:
                raise APIStatusError(f"base64 decode failed: {e}", status_code=200, request_id="", body=audio_url[:500]) from e
            mime_type = "audio/mpeg"
        elif audio_url.startswith("http"):
            # Download audio file
            try:
                audio_resp = await self._tts._http.get(audio_url, timeout=20.0)
            except _httpx.TimeoutException as e:
                raise APITimeoutError() from e
            except Exception as e:
                raise APIConnectionError() from e
            if audio_resp.status_code != 200:
                raise APIStatusError(f"audio download HTTP {audio_resp.status_code}", status_code=audio_resp.status_code, request_id="", body=audio_resp.text[:500])
            audio_bytes = audio_resp.content
            # Infer mime from content-type or URL extension
            ct = audio_resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ct in {"audio/mpeg", "audio/mp3", "audio/ogg", "audio/opus", "audio/wav", "audio/webm"}:
                mime_type = ct
            elif audio_url.endswith(".mp3"):
                mime_type = "audio/mpeg"
            elif audio_url.endswith(".wav"):
                mime_type = "audio/wav"
            elif audio_url.endswith(".opus"):
                mime_type = "audio/opus"
            elif audio_url.endswith(".ogg"):
                mime_type = "audio/ogg"
            else:
                mime_type = "audio/mpeg"
        else:
            # Assume raw base64 without prefix
            try:
                import base64
                audio_bytes = base64.b64decode(audio_url)
                mime_type = "audio/mpeg"
            except Exception:
                raise APIStatusError(f"unexpected audio field: {audio_url[:500]}", status_code=200, request_id="", body=audio_url[:500])

        # Emit audio — AudioEmitter will decode mp3/opus and resample to sample_rate
        output_emitter.initialize(
            request_id=resp.headers.get("cf-ray", "") or "",
            sample_rate=self._tts.sample_rate,
            num_channels=NUM_CHANNELS,
            mime_type=mime_type,
            stream=False,
        )
        output_emitter.push(audio_bytes)
        output_emitter.flush()
