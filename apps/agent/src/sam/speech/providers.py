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
    # TTS_PROVIDER > CLOUDFLARE_TTS_ENABLED > SPEECH_PROVIDER
    raw = os.getenv("TTS_PROVIDER", "").strip().lower()
    if not raw:
        # boolean toggle for Cloudflare
        if os.getenv("CLOUDFLARE_TTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
            return "cloudflare"
        # also allow CLOUDFLARE_TTS_MODEL containing elevenlabs to imply cloudflare
        # but don't auto-enable; explicit TTS_PROVIDER is required otherwise fallback
        raw = os.getenv("SPEECH_PROVIDER", "inference").strip().lower()
    if raw in {"cloudflare", "cf", "elevenlabs", "eleven-v3", "eleven_v3", "elevenlabs/eleven-v3"}:
        return "cloudflare"
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
    if prov == "cloudflare":
        missing = [n for n in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN") if not (os.getenv(n) or "").strip()]
        if missing:
            raise RuntimeError(f"TTS_PROVIDER=cloudflare requires {', '.join(missing)}")
        # voice_id optional — has default, but warn if missing
        if not (os.getenv("CLOUDFLARE_TTS_VOICE_ID") or os.getenv("ELEVENLABS_VOICE_ID") or "").strip():
            # not fatal — default voice_id will be used
            pass
    elif prov == "direct":
        missing = [n for n in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY") if not (os.getenv(n) or "").strip()]
        # Only warn for TTS direct needs GOOGLE_API_KEY
        if not os.getenv("GOOGLE_API_KEY", "").strip():
            raise RuntimeError("TTS_PROVIDER=direct requires GOOGLE_API_KEY")
