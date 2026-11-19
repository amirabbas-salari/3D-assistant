"""Measure time-to-first-token for the Cloudflare Workers AI LLM.

The latency log showed time-to-first-token jumping between 1.0 s and 5.4 s for
the same short questions. That spread is the model's reasoning depth, not the
network, and the fix is a request parameter. This script measures it directly
so the effect can be seen in seconds instead of by talking to the agent.

For each variant it reports the first-token time over several runs, which is
the number the agent's own latency log calls `llm_node_ttft`.

    python scripts/check_llm_speed.py
    python scripts/check_llm_speed.py --runs 5 --prompt "سلام، حالت چطوره؟"

Only timings and token counts are printed; the API token is never shown.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_PROMPT = "سلام! در یک جمله بگو امروز چه هوایی است."
# Deliberately short questions: an agent waiting 2 s for a one-line reply is the
# complaint this script exists to answer.
VARIANTS = (
    ("بدون تنظیم (پیش‌فرض provider)", {}),
    ("reasoning_effort=low", {"reasoning_effort": "low"}),
    ("reasoning_effort=low + پاسخ کوتاه", {"reasoning_effort": "low", "_fast_start": True}),
    ("reasoning_effort=medium", {"reasoning_effort": "medium"}),
)

# The characters the SDK's sentence tokenizer treats as a boundary. Whisper-
# style Persian punctuation included, since a reply may end its first sentence
# with "؟" or "!".
SENTENCE_END = frozenset(".!?؟۔\n")

FAST_START_HINT = (
    " همیشه پاسخ را با یک جمله‌ی کوتاه و کامل شروع کن (حداکثر شش کلمه)، بعد اگر لازم بود ادامه بده."
)


async def measure(base_url: str, api_key: str, model: str, prompt: str,
                  variant: dict, runs: int) -> dict:
    """One variant: first-token and first-sentence timings in milliseconds."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
    messages = []
    if variant.get("_fast_start"):
        messages.append({"role": "system", "content": FAST_START_HINT.strip()})
    messages.append({"role": "user", "content": prompt})

    extra: dict = {"max_tokens": 512}
    if "reasoning_effort" in variant:
        extra["reasoning_effort"] = variant["reasoning_effort"]

    ttfts: list[float] = []
    first_sentence_times: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        gathered = ""
        saw_first_token = False
        saw_first_sentence = False
        try:
            stream = await client.chat.completions.create(
                model=model, messages=messages, stream=True, extra_body=extra
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                text = getattr(chunk.choices[0].delta, "content", None)
                if not text:
                    continue
                if not saw_first_token:
                    saw_first_token = True
                    ttfts.append((time.perf_counter() - started) * 1000)
                gathered += text
                # TTS starts at the first sentence boundary, so time-to-first-
                # sentence is what decides when speech actually begins.
                if not saw_first_sentence and any(ch in SENTENCE_END for ch in gathered):
                    saw_first_sentence = True
                    first_sentence_times.append((time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001 - the error text is the result
            return {"error": f"{type(exc).__name__}: {str(exc)[:220]}"}

    await client.close()
    return {"ttft": ttfts, "first_sentence": first_sentence_times}


def _fmt(values: list[float]) -> str:
    if not values:
        return "—"
    mean = statistics.fmean(values)
    worst = max(values)
    return f"میانگین {mean:.0f} ms · بدترین {worst:.0f} ms"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="runs per variant")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=os.getenv("CLOUDFLARE_LLM_MODEL", "@cf/openai/gpt-oss-120b"))
    args = parser.parse_args()

    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        print("❌ CLOUDFLARE_ACCOUNT_ID و CLOUDFLARE_API_TOKEN باید در .env باشند")
        return 1

    base_url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1"
    print(f"مدل: {args.model}")
    print(f"هر حالت {args.runs} بار · همان پرامپت هر بار")
    print(f"پرامپت: {args.prompt}\n")

    results: list[tuple[str, dict]] = []
    for name, variant in VARIANTS:
        print(f"… {name}", end="", flush=True)
        result = await measure(base_url, token, args.model, args.prompt, variant, args.runs)
        results.append((name, result))
        if "error" in result:
            print(f"\r  ❌ {name}: {result['error']}")
        else:
            print(f"\r  ✅ {name}")

    print("\n" + "=" * 68)
    print(f"{'حالت':34} {'اولین توکن':32}")
    print("-" * 68)
    baseline = None
    for name, result in results:
        if "error" in result:
            print(f"{name:34} {'خطا':32}")
            continue
        cell = _fmt(result["ttft"])
        if baseline is None and result["ttft"]:
            baseline = statistics.fmean(result["ttft"])
        elif baseline and result["ttft"]:
            mean = statistics.fmean(result["ttft"])
            delta = mean - baseline
            cell += f"  ({delta:+.0f} ms)"
        print(f"{name:34} {cell:32}")

    print("\nنکته: «اولین توکن» همان چیزی است که لاگ ایجنت llm_node_ttft می‌نامد.")
    print("اگر reasoning_effort=low تفاوت معناداری نساخت، Workers AI این فیلد را")
    print("نادیده می‌گیرد؛ در آن صورت از CLOUDFLARE_LLM_REASONING_NESTED=true استفاده کنید")
    print("یا مدل را به یک مدل غیراستدلالی تغییر دهید (CLOUDFLARE_LLM_MODEL).")
    failed = any("error" in r for _, r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
