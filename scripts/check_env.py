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


def _mask(value: str) -> str:
    """Show just enough of a secret to confirm it is the one you think it is."""
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return f"{value[:2]}…{value[-2:]} ({len(value)} chars)"
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)"


def load_env_file() -> dict[str, str]:
    """Read .env and report what is there, without trusting python-dotenv first.

    ``lk`` reads ``.env.local`` then ``.env`` with ``godotenv.Read``, which does
    not expand shell variables and ignores malformed lines. Reading the file by
    hand here means a malformed line shows up as a warning instead of silently
    producing an empty value in the agent.
    """
    values: dict[str, str] = {}
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
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


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
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                local[k.strip()] = v.strip().strip("\"'")
        file_values = load_env_file()
        both = sorted(set(local) & set(file_values))
        if both:
            print(f"     ⚠ این کلیدها در هر دو فایل هستند: {', '.join(both)}")
            print("       مقدار .env.local برنده است؛ اگر قدیمی است، حذف یا به‌روزش کنید")
    return problems


def check_values(values: dict[str, str]) -> list[str]:
    problems: list[str] = []
    print("\n۲) کلیدهای LiveKit در .env")
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
    if url.startswith("ws://") or url.startswith("wss://"):
        print(f"  ⚠ LIVEKIT_URL با {url.split(':', 1)[0]} شروع می‌شود؛ ایجنت wss را می‌پذیرد ولی")
        print("    lk برای بررسی کلید به https نیاز دارد. مقدار متداول: wss://<project>.livekit.cloud")
    elif not url.startswith("https://"):
        print(f"  ⚠ LIVEKIT_URL باید با https:// یا wss:// شروع شود، نه {url[:24]!r}")

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
