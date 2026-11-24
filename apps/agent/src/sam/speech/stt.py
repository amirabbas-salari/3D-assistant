import inspect
import os

from livekit.agents import APIConnectOptions, inference

try:
    from livekit.plugins import deepgram as deepgram_plugin
    _deepgram_err = None
except ImportError as exc:
    deepgram_plugin = None
    _deepgram_err = exc

_OR_DEFAULT_BASE = "https://openrouter.ai/api/v1"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _first_env(*names: str, default: str = "") -> str:
    for n in names:
        v = _env(n)
        if v:
            return v
    return default


def _supported_kwargs(cls, **kwargs):
    """فقط kwargs هایی را بده که سازندهٔ این نسخهٔ پلاگین می‌شناسد (جلوگیری از TypeError بین نسخه‌ها)."""
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in params}


def build_stt(provider: str, *, model: str, language: str, conn_options: APIConnectOptions, fallback: list[str], job_logger):
    if provider == "direct":
        api_key = _env("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("SPEECH_PROVIDER=direct needs DEEPGRAM_API_KEY")
        if deepgram_plugin is None:
            raise RuntimeError(f"deepgram plugin missing ({_deepgram_err})")
        mname = model.split("/", 1)[-1] if "/" in model else model
        job_logger.info("STT via Deepgram API directly (model=%s, language=%s)", mname, language)
        return deepgram_plugin.STT(model=mname, language=language, api_key=api_key)
    return inference.STT(model=model, language=language, conn_options=conn_options, **({"fallback": fallback} if fallback else {}))


def build_tts(provider: str, *, model: str, voice: str, language: str, conn_options: APIConnectOptions, job_logger):
    if provider == "openrouter":
        from .openrouter_tts import OpenRouterTTS

        # قبلاً: os.getenv("OPENROUTER_TTS_MODEL").strip() → AttributeError وقتی متغیر تنظیم نشده بود
        or_model = _env("OPENROUTER_TTS_MODEL") or None  # None → پیش‌فرض خود OpenRouterTTS

        # voice فالبک (مثلاً "Charon" که صدای Gemini است) فقط برای مدل‌های google/ معنا دارد؛
        # برای openai/elevenlabs/... باعث 400 invalid voice می‌شد.
        fallback_voice = voice if (or_model or "").startswith("google/") else ""
        or_voice = _first_env("OPENROUTER_TTS_VOICE", "OPENROUTER_VOICE") or fallback_voice

        or_format = _env("OPENROUTER_TTS_RESPONSE_FORMAT", "mp3")
        try:
            sr = int(_env("OPENROUTER_TTS_SAMPLE_RATE", "24000"))
        except ValueError:
            sr = 24000
        base_url = _env("OPENROUTER_BASE_URL", _OR_DEFAULT_BASE)
        job_logger.info("TTS via OpenRouter (model=%s, voice=%s, format=%s, sr=%s, base=%s)",
                        or_model or "default", or_voice or "auto/omit", or_format, sr, base_url)
        return OpenRouterTTS(model=or_model, voice=or_voice or None, response_format=or_format, sample_rate=sr, base_url=base_url)

    if provider == "elevenlabs":
        api_key = _first_env("ELEVENLABS_API_KEY", "ELEVEN_API_KEY")
        if not api_key:
            raise RuntimeError("TTS_PROVIDER=elevenlabs needs ELEVENLABS_API_KEY (یا ELEVEN_API_KEY)")
        try:
            from livekit.plugins import elevenlabs as eleven_plugin
        except ImportError as exc:
            raise RuntimeError(f"elevenlabs plugin missing ({exc}) — pip install livekit-plugins-elevenlabs")
        el_model = _first_env("ELEVENLABS_MODEL", "ELEVENLABS_TTS_MODEL", "ELEVEN_TTS_MODEL", default="eleven_flash_v2_5")
        el_voice_id = _first_env("ELEVENLABS_VOICE_ID", "ELEVEN_VOICE_ID", default=voice) or "JBFqnCBsd6RMkjVDRZzb"
        encoding = _env("ELEVENLABS_ENCODING", "mp3_22050_32")
        # auto_mode: تاخیر کمتر وقتی جمله‌های کامل می‌فرستیم؛ فقط اگر این نسخهٔ پلاگین بشناسد اعمال می‌شود.
        # برای خاموش‌کردن: ELEVENLABS_AUTO_MODE=false
        extra = {}
        if _env("ELEVENLABS_AUTO_MODE", "true").lower() not in {"0", "false", "no", "off"}:
            extra = _supported_kwargs(eleven_plugin.TTS, auto_mode=True)
        job_logger.info("TTS via ElevenLabs direct (model=%s, voice_id=%s, lang=%s, encoding=%s, extra=%s)",
                        el_model, el_voice_id, language, encoding, list(extra) or "-")
        return eleven_plugin.TTS(api_key=api_key, voice_id=el_voice_id, model=el_model, encoding=encoding,
                                 language=language or "fa", **extra)

    if provider == "direct":
        api_key = _env("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("SPEECH_PROVIDER=direct needs GOOGLE_API_KEY")
        try:
            from livekit.plugins import google as google_plugin
        except ImportError as exc:
            raise RuntimeError(f"google plugin missing ({exc})")
        mname = model.split("/", 1)[-1] if "/" in model else model
        job_logger.info("TTS via Google Gemini API directly (model=%s, voice=%s)", mname, voice)
        return google_plugin.beta.GeminiTTS(model=mname, voice_name=voice, api_key=api_key)
    return inference.TTS(model=model, voice=voice, language=language, conn_options=conn_options)