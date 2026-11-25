"""Check why the agent cannot reach (or start against) LiveKit.

``lk agent dev`` fails before the agent runs with terse messages like
``api-key is required``. The agent's own start-up failures say even less. This
script reads the same ``.env`` the agent does and reports, in order:

1. whether ``.env`` exists and which ``LIVEKIT_*`` keys it actually defines;
2. whether the values look well-formed (URL shape, key/secret pairing);
3. whether LiveKit accepts the credentials (a real token-authenticated call);
4. optionally, what LiveKit Inference answers, and whether the speech keys for
   ``SPEECH_PROVIDER=direct`` are present.

Only presence and validity are reported — secrets are never printed.

Usage (from the project root, with the venv the agent uses):

    python scripts/check_env.py
    python scripts/check_env.py --skip-network    # offline / no credentials yet

Exit code 0 when the setup looks usable, 1 when something must be fixed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
UNTERMINATED: list[str] = []


def _mask(value: str) -> str:
    """Show just enough of a secret to confirm it is the one you think it is."""
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return f"{value[:2]}…{value[-2:]} ({len(value)} chars)"
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)"


def load_env_file() -> dict[str, str]:
    """Read .env the way the two real readers do, not with a naive split.

    ``agent.py`` uses ``python-dotenv`` and ``lk`` uses ``godotenv``. Both accept
    a trailing comment after a quoted value (``KEY="value" # note``): the quote
    closes the value and everything after it is discarded. Both also accept a
    comment after an *unquoted* value when the ``#`` follows whitespace.

    An earlier version of this function only stripped matching outer quotes, so
    ``"wss://host" # a2`` became ``"wss://host" # a2`` verbatim and this script
    reported a perfectly good .env as malformed. Parsing like the real readers
    is the whole point of checking them.
    """
    values: dict[str, str] = {}
    UNTERMINATED.clear()
    if not ENV_PATH.exists():
        return values
    for raw in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            print(f"  ⚠ خط نامعتبر (بدون =): {raw[:60]}")
            continue
        key, _, rest = line.partition("=")
        values[key.strip()] = _parse_value(rest.strip())
    return values


def _parse_value(src: str) -> str:
    """Value of one ``KEY=...`` line, following godotenv's rules.

    Quoted: the value ends at the closing quote (respecting backslash escapes),
    and a trailing comment is dropped. Unquoted: a `` #`` starts a comment.
    """
    if src[:1] in {"'", '"'}:
        quote = src[0]
        i = 1
        while i < len(src):
            if src[i] == quote:
                backslashes = 0
                j = i - 1
                while j >= 0 and src[j] == "\\":
                    backslashes += 1
                    j -= 1
                if backslashes % 2 == 0:
                    return src[1:i]
            i += 1
        # Unterminated quote: godotenv fails the whole file and python-dotenv
        # returns nothing useful, so this is a hard error, not a warning.
        UNTERMINATED.append(src[:40])
        return ""
    for index, char in enumerate(src):
        if char == "#" and index > 0 and src[index - 1] in " \t":
            return src[:index].strip()
    return src.strip()


def check_files() -> list[str]:
    problems: list[str] = []
    print("۱) فایل‌های محیطی")
    if not ENV_PATH.exists():
        print("  ❌ .env وجود ندارد")
        print("     راه‌حل: cp .env.example .env  (ویندوز: Copy-Item .env.example .env)")
        return ["فایل .env نیست"]
    print(f"  ✅ .env پیدا شد ({ENV_PATH.stat().st_size} بایت)")

    env_local = ROOT / ".env.local"
    if env_local.exists():
        print("  ℹ️  .env.local هم وجود دارد — lk آن را بر .env مقدم می‌داند")
        # Duplicate keys across the two files are a classic source of confusion.
        local = {}
        for raw in env_local.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" in line:
                k, _, v = line.partition("=")
                local[k.strip()] = _parse_value(v.strip())
        file_values = load_env_file()
        both = sorted(set(local) & set(file_values))
        if both:
            print(f"     ⚠ این کلیدها در هر دو فایل هستند: {', '.join(both)}")
            print("       مقدار .env.local برنده است؛ اگر قدیمی است، حذف یا به‌روزش کنید")
    return problems


def check_values(values: dict[str, str]) -> list[str]:
    problems: list[str] = []
    print("\n۲) کلیدهای LiveKit در .env")
    for snippet in UNTERMINATED:
        print(f"  ❌ کوتیشن بسته نشده در خطی که با این شروع می‌شود: {snippet}")
        problems.append("کوتیشن بسته‌نشده در .env")
    required = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    missing = [k for k in required if not values.get(k, "").strip()]
    for key in required:
        value = values.get(key, "").strip()
        if not value:
            print(f"  ❌ {key} خالی یا تعریف نشده")
        elif key == "LIVEKIT_API_SECRET":
            print(f"  ✅ {key} = {_mask(value)}")
        else:
            print(f"  ✅ {key} = {value}")
    if missing:
        problems.append("کلیدهای غایب: " + ", ".join(missing))
        print("\n     ⚠ بدون این‌ها هم lk و هم خود ایجنت متوقف می‌شوند.")
        print("       lk دقیقاً به همین دلیل «api-key is required» می‌دهد: نه در .env")
        print("       هست، نه در متغیرهای محیطی، نه در تنظیمات lk.")
        return problems

    url = values["LIVEKIT_URL"].strip()
    # wss:// is the normal LiveKit Cloud value and both readers accept it; the
    # SDK rewrites it to https:// for the REST API. Only a wrong scheme is a bug.
    if not url.startswith(("wss://", "ws://", "https://", "http://")):
        print(f"  ⚠ LIVEKIT_URL باید با wss:// یا https:// شروع شود، نه {url[:24]!r}")
        problems.append("LIVEKIT_URL با طرح نادرست")
    elif url.startswith("ws://") and "localhost" not in url and "127.0.0.1" not in url and "livekit:" not in url:
        print("  ⚠ برای سرور راه دور از wss:// استفاده کنید (ws:// رمزنگاری‌نشده است)")

    # تشخیص لوکال — ws://localhost یا devkey
    is_local = any(x in url for x in ("localhost", "127.0.0.1", "livekit:")) or url.startswith("ws://")
    if is_local:
        print("  ℹ️  LiveKit لوکال تشخیص داده شد — Inference در لوکال وجود ندارد؛ SPEECH_PROVIDER=direct و LLM_PROVIDER=openrouter/cloudflare بگذارید")
        if values["LIVEKIT_API_KEY"].strip() == "devkey" and values["LIVEKIT_API_SECRET"].strip() == "secret":
            print("  ✅ کلیدهای پیش‌فرض dev (--dev) — برای production عوض کنید")
        speech = (values.get("SPEECH_PROVIDER") or values.get("TTS_PROVIDER") or "inference").strip().lower()
        llm = (values.get("LLM_PROVIDER") or "").strip().lower()
        if speech in {"inference", ""}:
            print("  ⚠ لوکال با SPEECH_PROVIDER=inference کار نمی‌کند — بگذارید direct یا openrouter/elevenlabs")
        if llm in {"livekit", "inference", "lk", ""} and not values.get("OPENROUTER_API_KEY", "").strip() and not (values.get("CLOUDFLARE_API_TOKEN", "").strip() and values.get("CLOUDFLARE_ACCOUNT_ID", "").strip()):
            print("  ⚠ لوکال با LLM_PROVIDER=livekit کار نمی‌کند — بگذارید openrouter یا cloudflare")

    key, secret = values["LIVEKIT_API_KEY"].strip(), values["LIVEKIT_API_SECRET"].strip()
    if secret.startswith("API") and key.startswith("API"):
        print("  ⚠ به نظر می‌رسد key و secret جابه‌جا شده‌اند (secret با API شروع می‌شود)")
        problems.append("احتمال جابه‌جایی key/secret")

    # A library-style 401/403 later is much easier to read if the shape is checked here.
    if len(key) < 8:
        print(f"  ⚠ API key کوتاه است ({len(key)} نویسه) — معمولاً با API شروع می‌شود")
    return problems


def check_network(values: dict[str, str]) -> list[str]:
    """Ask LiveKit whether it accepts these credentials."""
    print("\n۳) اعتبارسنجی با LiveKit")
    if not all(values.get(k, "").strip() for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")):
        print("  ⏭  رد شد (کلیدها کامل نیستند)")
        return []

    try:
        from livekit import api
    except ImportError:
        print("  ⏭  رد شد (پکیج livekit نصب نیست)")
        return []

    import asyncio

    url = values["LIVEKIT_URL"].strip().replace("wss://", "https://", 1).replace("ws://", "http://", 1)

    async def probe() -> None:
        http_url = url.replace("https://", "http://", 1).replace("wss://", "ws://", 1)
        async with api.LiveKitAPI(http_url, values["LIVEKIT_API_KEY"], values["LIVEKIT_API_SECRET"]) as client:
            rooms = await client.room.list_rooms(api.ListRoomsRequest())
            print(f"  ✅ LiveKit کلید را پذیرفت ({len(rooms.rooms)} room فعال)")

    try:
        asyncio.run(probe())
    except Exception as exc:  # noqa: BLE001 - the message is the point
        text = str(exc)
        print(f"  ❌ اتصال یا اعتبارسنجی ناموفق: {type(exc).__name__}")
        print(f"     {text[:300]}")
        if "401" in text or "unauthorized" in text.lower():
            print("     یعنی کلید/secret غلط است یا برای پروژه‌ی دیگری است.")
        elif "Cannot connect" in text or "ConnectError" in type(exc).__name__:
            print("     یعنی مشکل شبکه/DNS/پراکسی است، نه کلید.")
        return ["LiveKit اتصال/اعتبارسنجی را رد کرد"]
    return []


def check_speech(values: dict[str, str]) -> list[str]:
    print("\n۴) مسیر گفتار (STT/TTS)")
    provider = (values.get("SPEECH_PROVIDER") or "inference").strip().lower()
    if provider in {"direct", "byok", "provider", "own-keys"}:
        print("  ℹ️  SPEECH_PROVIDER=direct — گیت‌وی LiveKit Inference لازم نیست")
        missing = [k for k in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY") if not values.get(k, "").strip()]
        for key in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY"):
            value = values.get(key, "").strip()
            print(f"  {chr(9989) if value else chr(10060)} {key} = {_mask(value)}")
        if missing:
            print("\n     ⚠ agent.py با پیام «SPEECH_PROVIDER=direct requires ...» متوقف می‌شود")
            return ["کلیدهای گفتار غایب: " + ", ".join(missing)]
        return []
    print("  ℹ️  SPEECH_PROVIDER=inference — از گیت‌وی استفاده می‌شود و به همین کلیدهای LiveKit وابسته است")
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-network", action="store_true", help="only check files and values")
    args = parser.parse_args()

    print(f"ریشه‌ی پروژه: {ROOT}\n")
    problems = check_files()
    values = load_env_file()
    problems += check_values(values)
    if not args.skip_network:
        problems += check_network(values)
    problems += check_speech(values)

    print("\n" + "=" * 60)
    if problems:
        print("نتیجه: چند مورد باید درست شود:")
        for item in problems:
            print(f"  • {item}")
        return 1
    print("نتیجه: تنظیمات برای اجرا آماده به نظر می‌رسد.")
    print("مرحله‌ی بعد: python agent.py dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
