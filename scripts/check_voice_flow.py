"""Check the things that make the voice pause.

A pause in the middle of a reply is usually not silence in the text — it is the
wait for the next TTS request. One request per sentence, each a round-trip, is
what fragments speech. These checks keep the settings that reduce that count
from being quietly undone.

    python scripts/check_voice_flow.py

Needs `livekit-agents` installed (it is in requirements.txt). It does not need
credentials: it exercises the tokenizer and the prompt, not the providers.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/agent/src"))
sys.path.insert(0, str(ROOT))

# agent.py validates its config at import time; give it the minimum it needs.
os.environ.setdefault("LIVEKIT_URL", "wss://check.invalid")
os.environ.setdefault("LIVEKIT_API_KEY", "check")
os.environ.setdefault("LIVEKIT_API_SECRET", "check")
os.environ.setdefault("RAG_ENABLED", "false")

from livekit.agents import tokenize  # noqa: E402

failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail else ""))


async def tts_requests(text: str) -> list[str]:
    """The segments the SDK's own tokenizer would turn into TTS requests."""
    stream = tokenize.blingfire.SentenceTokenizer(retain_format=True).stream()
    out: list[str] = []

    async def feed() -> None:
        import re

        for piece in re.split(r"(?<=[.!?؟])\s+", text):
            if piece:
                stream.push_text(piece + " ")
            await asyncio.sleep(0)
        stream.end_input()

    async def drain() -> None:
        async for ev in stream:
            out.append(ev.token.strip())

    await asyncio.gather(feed(), drain())
    await stream.aclose()
    return [seg for seg in out if seg]


def load_agent():
    spec = importlib.util.spec_from_file_location("agent_under_test", ROOT / "agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def main() -> int:
    fragmenty = (
        "حتماً. بذارید چک کنم. این استراتژی فروش عالیه و نرخ تبدیل را بالا می‌بره. "
        "برای شما پیاده کنم؟"
    )
    whole = (
        "این استراتژی فروش نرخ تبدیل را بالا می‌بره و همین الان می‌تونم براتون پیادش کنم."
    )
    fragmented = await tts_requests(fragmenty)
    consolidated = await tts_requests(whole)
    check(
        "a reply of fragments costs many TTS requests (the pause mechanism)",
        len(fragmented) >= 3,
        f"{len(fragmented)} requests",
    )
    check(
        "one complete sentence costs a single request",
        len(consolidated) == 1,
        f"{len(consolidated)} request",
    )

    agent_module = load_agent()

    class _Tool:
        info = type("Info", (), {"name": "search_knowledge", "description": "x"})()

    instructions = str(agent_module.PersianAssistant(knowledge_tool=_Tool()).instructions)
    check("prompt asks for a complete first sentence", "جمله‌ی کامل شروع کن" in instructions)
    check("prompt forbids breaking sentences up", "جمله‌ها را نشکن" in instructions)
    check(
        "the old 'max six words' rule is gone",
        "حداکثر شش کلمه" not in instructions,
    )
    check(
        "first sentence has a length target, not just 'short'",
        "پنج تا نه کلمه" in instructions,
    )

    # The profile that matters most: "balanced" must already carry preemptive
    # TTS, otherwise the default configuration is the one that stutters.
    class _Log:
        def info(self, *a, **k):
            pass

        def warning(self, *a, **k):
            print("WARN", a)

    os.environ.pop("AGENT_SPEED_PROFILE", None)
    balanced = agent_module._speed_profile(_Log())
    check(
        "balanced profile pre-generates TTS (next sentence ready before the gap)",
        balanced.get("preemptive_generation", {}).get("preemptive_tts") is True,
        str(balanced),
    )

    print()
    if failures:
        print(f"{failures} check(s) failed — the voice will pause more than it needs to.")
        return 1
    print("all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
