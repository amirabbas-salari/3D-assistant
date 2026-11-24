import os

# STT still uses SPEECH_PROVIDER for backwards compat; TTS can be overridden separately

_DIRECT = {"direct", "byok", "provider", "own-keys"}

# مستقیم از elevenlabs.io
_ELEVENLABS = {
    "elevenlabs", "eleven", "elevenlabs.io", "eleven_flash_v2_5", "eleven_flash_v2", "eleven_turbo_v2_5",
    "eleven_turbo_v2", "eleven_multilingual_v2", "eleven_multilingual_v1", "eleven_v3", "eleven_v4", "eleven_v4_turbo",
}

# OpenRouter (شامل نام‌های legacy که قبلاً cloudflare بودند؛ قبلاً در یک شاخهٔ جدا و بخشی از آن غیرقابل‌دسترس بود)
_OPENROUTER = {
    "openrouter", "or", "open-router", "open_router",
    "elevenlabs/eleven-v3-conversational", "eleven-v3-conversational", "eleven_v3_conversational",
    "conversational", "or-conversational",
    "cloudflare", "cf", "eleven-v3", "elevenlabs/eleven-v3",
}

_TRUE = {"1", "true", "yes", "on"}


def _raw(name: str) -> str:
    return os.getenv(name, "").strip().lower()


def _has(*names: str) -> bool:
    return any((os.getenv(n) or "").strip() for n in names)


def speech_provider() -> str:
    return "direct" if (_raw("SPEECH_PROVIDER") or "inference") in _DIRECT else "inference"


def stt_provider() -> str:
    # STT_PROVIDER overrides SPEECH_PROVIDER if set
    raw = _raw("STT_PROVIDER")
    if raw:
        return "direct" if raw in _DIRECT else "inference"
    return speech_provider()


def tts_provider() -> str:
    # TTS_PROVIDER > legacy CLOUDFLARE_TTS_ENABLED→OPENROUTER mapping > SPEECH_PROVIDER
    raw = _raw("TTS_PROVIDER")
    if not raw:
        if _raw("CLOUDFLARE_TTS_ENABLED") in _TRUE:
            return "openrouter"
        raw = _raw("SPEECH_PROVIDER") or "inference"
    if raw in _ELEVENLABS:
        return "elevenlabs"
    if raw in _OPENROUTER:
        return "openrouter"
    if raw in _DIRECT:
        return "direct"
    return "inference"


def validate_stt_config() -> None:
    """فقط کلیدهای لازمِ STT (قبلاً SPEECH_PROVIDER=direct هر دو کلید Deepgram و Google را می‌خواست)."""
    if stt_provider() == "direct" and not _has("DEEPGRAM_API_KEY"):
        raise RuntimeError("STT_PROVIDER/SPEECH_PROVIDER=direct requires DEEPGRAM_API_KEY. Add it to .env or set it to 'inference'")


def validate_tts_config() -> None:
    prov = tts_provider()
    if prov == "openrouter":
        if not _has("OPENROUTER_API_KEY"):
            raise RuntimeError("TTS_PROVIDER=openrouter requires OPENROUTER_API_KEY (get one at https://openrouter.ai/settings/keys)")
    elif prov == "elevenlabs":
        if not _has("ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
            raise RuntimeError("TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY (یا ELEVEN_API_KEY)")
    elif prov == "direct":
        if not _has("GOOGLE_API_KEY"):
            raise RuntimeError("TTS_PROVIDER=direct requires GOOGLE_API_KEY")


def validate_speech_config() -> None:
    """سازگاری با نسخهٔ قبل: هر دو را چک می‌کند."""
    validate_stt_config()
    validate_tts_config()