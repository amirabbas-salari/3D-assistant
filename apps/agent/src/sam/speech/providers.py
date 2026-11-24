import os

# STT still uses SPEECH_PROVIDER for backwards compat; TTS can be overridden separately

def speech_provider() -> str:
    p = os.getenv("SPEECH_PROVIDER", "inference").strip().lower()
    return "direct" if p in {"direct", "byok", "provider", "own-keys"} else "inference"


def stt_provider() -> str:
    # STT_PROVIDER overrides SPEECH_PROVIDER if set
    raw = os.getenv("STT_PROVIDER", "").strip().lower()
    if raw:
        return "direct" if raw in {"direct", "byok", "provider", "own-keys"} else "inference"
    return speech_provider()


def tts_provider() -> str:
    # TTS_PROVIDER > legacy CLOUD→OPENROUTER mapping > SPEECH_PROVIDER
    raw = os.getenv("TTS_PROVIDER", "").strip().lower()
    if not raw:
        # Backward compat: old CLOUDFLARE_TTS_ENABLED now implies openrouter
        if os.getenv("CLOUDFLARE_TTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
            return "openrouter"
        raw = os.getenv("SPEECH_PROVIDER", "inference").strip().lower()
    # مستقیم از elevenlabs.io — مدل درخواستی eleven_flash_v2_5 هم اینجا می‌آید
    if raw in {"elevenlabs", "eleven", "elevenlabs.io", "eleven_flash_v2_5", "eleven_flash_v2", "eleven_turbo_v2_5", "eleven_turbo_v2", "eleven_multilingual_v2", "eleven_multilingual_v1", "eleven_v3", "eleven_v4", "eleven_v4_turbo"}:
        return "elevenlabs"
    # OpenRouter: eleven-v3-conversational via OpenRouter
    if raw in {"openrouter", "or", "open-router", "open_router", "elevenlabs/eleven-v3-conversational", "eleven-v3-conversational", "eleven_v3_conversational", "conversational", "or-conversational"}:
        return "openrouter"
    # Legacy: cloudflare was previous home of eleven-v3 — now migrate to openrouter with warning
    if raw in {"cloudflare", "cf", "eleven-v3", "eleven_v3", "elevenlabs/eleven-v3", "elevenlabs/eleven-v3-conversational"}:
        return "openrouter"
    if raw in {"direct", "byok", "provider", "own-keys"}:
        return "direct"
    return "inference"


def validate_speech_config() -> None:
    if speech_provider() != "direct":
        return
    missing = [n for n in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY") if not (os.getenv(n) or "").strip()]
    if missing:
        raise RuntimeError(f"SPEECH_PROVIDER=direct requires {', '.join(missing)}. Add them to .env or set SPEECH_PROVIDER=inference")


def validate_tts_config() -> None:
    prov = tts_provider()
    if prov == "openrouter":
        if not (os.getenv("OPENROUTER_API_KEY") or "").strip():
            raise RuntimeError("TTS_PROVIDER=openrouter requires OPENROUTER_API_KEY (get one at https://openrouter.ai/settings/keys)")
    elif prov == "elevenlabs":
        # مستقیم از elevenlabs.io با مدل eleven_flash_v2_5
        if not (os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY") or "").strip():
            raise RuntimeError("TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY (یا ELEVEN_API_KEY)")
    elif prov == "direct":
        missing = [n for n in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY") if not (os.getenv(n) or "").strip()]
        # Only warn for TTS direct needs GOOGLE_API_KEY
        if not os.getenv("GOOGLE_API_KEY", "").strip():
            raise RuntimeError("TTS_PROVIDER=direct requires GOOGLE_API_KEY")
