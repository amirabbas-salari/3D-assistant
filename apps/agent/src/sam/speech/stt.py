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
    if provider == "openrouter":
        from .openrouter_tts import OpenRouterTTS

        or_model = os.getenv("OPENROUTER_TTS_MODEL", "elevenlabs/eleven-v3-conversational").strip() or "elevenlabs/eleven-v3-conversational"
        or_voice = (
            os.getenv("OPENROUTER_TTS_VOICE", "").strip()
            or os.getenv("OPENROUTER_VOICE", "").strip()
            or voice
        )
        or_format = os.getenv("OPENROUTER_TTS_RESPONSE_FORMAT", "mp3").strip() or "mp3"
        try:
            sr = int(os.getenv("OPENROUTER_TTS_SAMPLE_RATE", "24000").strip() or "24000")
        except ValueError:
            sr = 24000
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip() or "https://openrouter.ai/api/v1"
        job_logger.info("TTS via OpenRouter (model=%s, voice=%s, format=%s, sr=%s, base=%s)", or_model, or_voice or "default", or_format, sr, base_url)
        return OpenRouterTTS(model=or_model, voice=or_voice, response_format=or_format, sample_rate=sr, base_url=base_url)

    if provider == "elevenlabs":
        # مستقیم از elevenlabs.io — مدل درخواستی eleven_flash_v2_5
        api_key = (
            os.getenv("ELEVENLABS_API_KEY", "").strip()
            or os.getenv("ELEVEN_API_KEY", "").strip()
        )
        if not api_key:
            raise RuntimeError("TTS_PROVIDER=elevenlabs needs ELEVENLABS_API_KEY (یا ELEVEN_API_KEY)")
        try:
            from livekit.plugins import elevenlabs as eleven_plugin
        except ImportError as exc:
            raise RuntimeError(f"elevenlabs plugin missing ({exc}) — pip install livekit-plugins-elevenlabs")
        # مدل: اولویت با ELEVENLABS_MODEL → ELEVENLABS_TTS_MODEL → مقدار ورودی
        el_model = (
            os.getenv("ELEVENLABS_MODEL", "").strip()
            or os.getenv("ELEVENLABS_TTS_MODEL", "").strip()
            or os.getenv("ELEVEN_TTS_MODEL", "").strip()
            or "eleven_flash_v2_5"
        )
        # voice_id: اولویت ELEVENLABS_VOICE_ID → LIVEKIT_TTS_VOICE
        el_voice_id = (
            os.getenv("ELEVENLABS_VOICE_ID", "").strip()
            or os.getenv("ELEVEN_VOICE_ID", "").strip()
            or voice
        ).strip() or "JBFqnCBsd6RMkjVDRZzb"
        # encoding: پیش‌فرض mp3_22050_32 (بهینه برای TTFB)، قابل تنظیم با ELEVENLABS_ENCODING
        encoding = os.getenv("ELEVENLABS_ENCODING", "").strip() or "mp3_22050_32"
        job_logger.info("TTS via ElevenLabs direct (model=%s, voice_id=%s, lang=%s, encoding=%s) — مستقیم از elevenlabs.io", el_model, el_voice_id, language, encoding)
        return eleven_plugin.TTS(
            api_key=api_key,
            voice_id=el_voice_id,
            model=el_model,
            encoding=encoding,
            language=language or "fa",
        )

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
