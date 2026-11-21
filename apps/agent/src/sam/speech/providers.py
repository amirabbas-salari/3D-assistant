import os
def speech_provider() -> str:
    p = os.getenv("SPEECH_PROVIDER","inference").strip().lower()
    return "direct" if p in {"direct","byok","provider","own-keys"} else "inference"
def validate_speech_config() -> None:
    if speech_provider() != "direct": return
    missing = [n for n in ("DEEPGRAM_API_KEY","GOOGLE_API_KEY") if not (os.getenv(n) or "").strip()]
    if missing: raise RuntimeError(f"SPEECH_PROVIDER=direct requires {', '.join(missing)}. Add them to .env or set SPEECH_PROVIDER=inference")
