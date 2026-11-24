"""Measure time-to-first-token for the LLM (OpenRouter or Cloudflare Workers AI).

Supports both providers:
  - OpenRouter:  OPENROUTER_API_KEY + OPENROUTER_LLM_MODEL (or LLM_MODEL)
  - Cloudflare:  CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN + CLOUDFLARE_LLM_MODEL

    python scripts/check_llm_speed.py
    python scripts/check_llm_speed.py --runs 5 --prompt "سلام، حالت چطوره؟"
    python scripts/check_llm_speed.py --provider openrouter --model openai/gpt-4o-mini
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
VARIANTS = (
    ("بدون تنظیم (پیش‌فرض provider)", {}),
    ("reasoning_effort=low", {"reasoning_effort": "low"}),
    ("reasoning_effort=low + پاسخ کوتاه", {"reasoning_effort": "low", "_fast_start": True}),
    ("reasoning_effort=medium", {"reasoning_effort": "medium"}),
)

SENTENCE_END = frozenset(".!?؟۔\n")

FAST_START_HINT = (
    " همیشه پاسخ را با یک جمله‌ی کوتاه و کامل شروع کن (حدود پنج تا نه کلمه و حاوی جواب اصلی)، بعد اگر لازم بود ادامه بده."
)


async def measure(base_url: str, api_key: str, model: str, prompt: str,
                  variant: dict, runs: int) -> dict:
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
                if not saw_first_sentence and any(ch in SENTENCE_END for ch in gathered):
                    saw_first_sentence = True
                    first_sentence_times.append((time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}

    await client.close()
    return {"ttft": ttfts, "first_sentence": first_sentence_times}


def _fmt(values: list[float]) -> str:
    if not values:
        return "—"
    mean = statistics.fmean(values)
    worst = max(values)
    return f"میانگین {mean:.0f} ms · بدترین {worst:.0f} ms"


def _detect_provider(explicit: str | None) -> tuple[str, str, str, str]:
    """Return (provider, base_url, api_key, model)."""
    if explicit:
        explicit = explicit.strip().lower()
    # explicit provider
    if explicit in {"openrouter", "or"}:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        base_url = (os.getenv("OPENROUTER_BASE_URL", "").strip() or "https://openrouter.ai/api/v1")
        model = os.getenv("OPENROUTER_LLM_MODEL", "").strip() or os.getenv("LLM_MODEL", "").strip() or "openai/gpt-4o-mini"
        return "openrouter", base_url, api_key, model
    if explicit in {"cloudflare", "cf", "workers"}:
        account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1" if account else ""
        model = os.getenv("CLOUDFLARE_LLM_MODEL", "").strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        return "cloudflare", base_url, token, model
    # auto-detect: prefer OpenRouter if its key exists
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        base_url = (os.getenv("OPENROUTER_BASE_URL", "").strip() or "https://openrouter.ai/api/v1")
        model = os.getenv("OPENROUTER_LLM_MODEL", "").strip() or os.getenv("LLM_MODEL", "").strip() or "openai/gpt-4o-mini"
        return "openrouter", base_url, api_key, model
    # fallback cloudflare
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    base_url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1" if account else ""
    model = os.getenv("CLOUDFLARE_LLM_MODEL", "").strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    return "cloudflare", base_url, token, model


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="runs per variant")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=None, help="override model (e.g. openai/gpt-4o-mini or @cf/meta/llama-3.3-70b-instruct-fp8-fast)")
    parser.add_argument("--provider", default=None, help="openrouter or cloudflare (auto-detect if omitted)")
    args = parser.parse_args()

    provider, base_url, api_key, detected_model = _detect_provider(args.provider)
    model = args.model or detected_model

    if not base_url or not api_key:
        if provider == "openrouter":
            print("❌ OPENROUTER_API_KEY باید در .env باشد (https://openrouter.ai/settings/keys)")
            print("   و OPENROUTER_LLM_MODEL را تنظیم کنید (مثلاً openai/gpt-4o-mini)")
        else:
            print("❌ CLOUDFLARE_ACCOUNT_ID و CLOUDFLARE_API_TOKEN باید در .env باشند")
        return 1

    print(f"Provider: {provider}")
    print(f"مدل: {model}")
    print(f"Base URL: {base_url}")
    print(f"هر حالت {args.runs} بار · همان پرامپت هر بار")
    print(f"پرامپت: {args.prompt}\n")

    results: list[tuple[str, dict]] = []
    for name, variant in VARIANTS:
        print(f"… {name}", end="", flush=True)
        result = await measure(base_url, api_key, model, args.prompt, variant, args.runs)
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
    if provider == "cloudflare":
        print("اگر reasoning_effort=low تفاوت نساخت، Workers AI این فیلد را نادیده می‌گیرد؛")
        print("CLOUDFLARE_LLM_REASONING_NESTED=true را امتحان کنید یا مدل را عوض کنید.")
    else:
        print("برای OpenRouter، مدل‌های سریع پیشنهادی: openai/gpt-4o-mini, google/gemini-2.0-flash-001")
        print("مدل‌های reasoning (deepseek-r1, o1) کندترند — برای voice استفاده نکنید.")
    failed = any("error" in r for _, r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
