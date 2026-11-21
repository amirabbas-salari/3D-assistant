import os
from livekit.agents import inference, APIConnectOptions
from .providers import speech_provider

try:
    from livekit.plugins import deepgram as deepgram_plugin
    _deepgram_err=None
except ImportError as exc:
    deepgram_plugin=None
    _deepgram_err=exc

def build_stt(provider: str, *, model: str, language: str, conn_options: APIConnectOptions, fallback: list[str], job_logger):
    if provider == "direct":
        api_key=os.getenv("DEEPGRAM_API_KEY","").strip()
        if not api_key: raise RuntimeError("SPEECH_PROVIDER=direct needs DEEPGRAM_API_KEY")
        if deepgram_plugin is None: raise RuntimeError(f"deepgram plugin missing ({_deepgram_err})")
        mname=model.split("/",1)[-1] if "/" in model else model
        job_logger.info("STT via Deepgram API directly (model=%s, language=%s)", mname, language)
        return deepgram_plugin.STT(model=mname, language=language, api_key=api_key)
    return inference.STT(model=model, language=language, conn_options=conn_options, **({"fallback":fallback} if fallback else {}))

def build_tts(provider: str, *, model: str, voice: str, language: str, conn_options: APIConnectOptions, job_logger):
    if provider == "cloudflare":
        # New: Cloudflare Workers AI → elevenlabs/eleven-v3
        from .cloudflare_tts import CloudflareTTS

        cf_model = os.getenv("CLOUDFLARE_TTS_MODEL", model).strip() or model
        # voice_id can be explicit or fallback to LIVEKIT_TTS_VOICE
        cf_voice_id = (
            os.getenv("CLOUDFLARE_TTS_VOICE_ID", "").strip()
            or os.getenv("ELEVENLABS_VOICE_ID", "").strip()
            or voice
        )
        # sample_rate: prefer CLOUDFLARE_TTS_SAMPLE_RATE else 24000
        try:
            sr = int(os.getenv("CLOUDFLARE_TTS_SAMPLE_RATE", "24000").strip() or "24000")
        except ValueError:
            sr = 24000
        job_logger.info("TTS via Cloudflare Workers AI (model=%s, voice_id=%s, lang=%s, sr=%s)", cf_model, cf_voice_id, language, sr)
        return CloudflareTTS(model=cf_model, voice_id=cf_voice_id, sample_rate=sr)

    if provider == "direct":
        api_key=os.getenv("GOOGLE_API_KEY","").strip()
        if not api_key: raise RuntimeError("SPEECH_PROVIDER=direct needs GOOGLE_API_KEY")
        try:
            from livekit.plugins import google as google_plugin
            _gerr=None
        except ImportError as exc:
            raise RuntimeError(f"google plugin missing ({exc})")
        mname=model.split("/",1)[-1] if "/" in model else model
        job_logger.info("TTS via Google Gemini API directly (model=%s, voice=%s); language %s not sent to Gemini", mname, voice, language)
        return google_plugin.beta.GeminiTTS(model=mname, voice_name=voice, api_key=api_key)
    return inference.TTS(model=model, voice=voice, language=language, conn_options=conn_options)
