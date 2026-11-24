"""Generic OpenRouter TTS — any model via audio/speech.

Uses OpenRouter's OpenAI-compatible endpoint:
  POST https://openrouter.ai/api/v1/audio/speech
  { model: "<OPENROUTER_TTS_MODEL>", input: "text", voice: "...", response_format: "mp3" }
→ raw audio bytes

تغییرات نسبت به نسخهٔ قبل (همه برای کاهش تأخیر / پایداری):
  * بدنهٔ پاسخ استریم می‌شود (client.stream + aiter_bytes) و هر تکه بلافاصله به emitter می‌رسد؛
    قبلاً کل mp3 جمله باید کامل دانلود می‌شد تا اولین صدا پخش شود.
  * timeout از conn_options خوانده می‌شود (قبلاً read=30s ثابت بود و FallbackAdapter/Session
    تا ۳۰ ثانیه منتظر یک درخواست گیرکرده می‌ماند).
  * keepalive_expiry=120s (پیش‌فرض httpx فقط ۵ ثانیه است؛ یعنی تقریباً هر نوبت یک TLS handshake جدید).
  * prewarm(): اتصال TLS قبل از اولین نوبت گرم می‌شود.
  * اگر بعد از ارسال بخشی از صدا خطا شد، retry نمی‌شود (جلوگیری از پخش دوبارهٔ صدا).
  * پاسخ ۲۰۰ با content-type غیرصوتی (JSON خطا) به‌جای ورود به دیکودر mp3 خطای تمیز می‌دهد.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os

import httpx as _httpx

from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger("sam.speech.openrouter_tts")

SAMPLE_RATE = 24000
NUM_CHANNELS = 1

DEFAULT_MODEL = "elevenlabs/eleven-v3-conversational"
DEFAULT_RESPONSE_FORMAT = "mp3"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Validated OpenRouter TTS models (2024-2025). Others return 400 Reference not found.
KNOWN_TTS_MODELS = {
    "elevenlabs/eleven-v3-conversational",
    "elevenlabs/eleven-v3",
    "elevenlabs/eleven-multilingual-v2",
    "openai/tts-1", "openai/tts-1-hd", "openai/gpt-4o-mini-tts",
    "google/gemini-2.5-flash-tts", "google/gemini-2.5-pro-tts",
    "minimax/minimax-speech-02-hd", "minimax/minimax-speech-02-turbo",
    "qwen/qwen3-tts-flash",
    "fish-audio/fish-speech-1.5", "fish-audio/fish-speech-1.4",
}

# Legacy ElevenLabs voice IDs → OpenRouter voice names (for old .env)
_LEGACY_VOICE_MAP = {
    "JBFqnCBsd6RMkjVDRZzb": "george",
    "21m00Tcm4TlvDq8ikWAM": "rachel",
    "EXAVITQu4vr4xnSDxMaL": "sarah",
    "FGY2WhTYpPnrIDTqs33q": "bella",
    "IKne3meq5aSn9XLyUdCD": "charlie",
    "On5p47yCR6tAlT5xT1oY": "adam",
    "TxGEqnHWznW5bvQe8BfY": "jessica",
    "ThT5KcBeYPX3keUQqHPh": "daniel",
    "pFZP5JQG7iQjIQuC4Bku": "lily",
    "XB0fDUnXU5powFXDhCwa": "charlotte",
}

_AUDIO_MIME = {"audio/mpeg", "audio/mp3", "audio/ogg", "audio/opus", "audio/wav", "audio/webm", "audio/pcm"}


def _normalize_voice(voice: str, model: str) -> str | None:
    """Return normalized voice or None if not needed.
    For elevenlabs models default to george, for others keep empty to omit.
    """
    v = (voice or "").strip()
    if not v:
        if "elevenlabs" in model.lower():
            return "george"
        return None
    if v in _LEGACY_VOICE_MAP:
        return _LEGACY_VOICE_MAP[v]
    if len(v) > 18 and v.isalnum():
        return "george" if "elevenlabs" in model.lower() else None
    return v.lower().strip()


class OpenRouterTTS(tts.TTS):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int = SAMPLE_RATE,
        http_referer: str | None = None,
        x_title: str | None = None,
        extra_params: dict | None = None,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=NUM_CHANNELS,
        )
        self._api_key = (api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for TTS_PROVIDER=openrouter (https://openrouter.ai/settings/keys)")

        self._base_url = (base_url or os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)).strip() or DEFAULT_BASE_URL
        self._base_url = self._base_url.rstrip("/")
        self._model = (model or os.getenv("OPENROUTER_TTS_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        if self._model == "fish-audio/drama-3":
            logger.warning("OPENROUTER_TTS_MODEL=fish-audio/drama-3 not on OpenRouter (400). Did you mean fish-audio/fish-speech-1.5? See https://openrouter.ai/models?fmt=audio")
        if self._model not in KNOWN_TTS_MODELS:
            logger.info("OPENROUTER_TTS_MODEL=%s not in known list, will try anyway (if 400, check https://openrouter.ai/models?fmt=audio)", self._model)

        raw_voice = (
            (voice or "").strip()
            or os.getenv("OPENROUTER_TTS_VOICE", "").strip()
            or os.getenv("OPENROUTER_VOICE", "").strip()
            or os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        )
        self._voice = _normalize_voice(raw_voice, self._model)

        fmt = (
            (response_format or "").strip()
            or os.getenv("OPENROUTER_TTS_RESPONSE_FORMAT", "").strip()
            or os.getenv("OPENROUTER_RESPONSE_FORMAT", "").strip()
            or DEFAULT_RESPONSE_FORMAT
        ).strip() or DEFAULT_RESPONSE_FORMAT
        if fmt.lower() in {"mp3_44100_128", "mp3_22050_32", "mp3"}:
            fmt = "mp3"
        elif fmt.lower() in {"pcm", "pcm_24000", "pcm_16000", "pcm_44100", "wav"}:
            fmt = fmt.lower().split("_")[0]  # pcm or wav
        self._response_format = fmt

        self._http_referer = (http_referer or os.getenv("OPENROUTER_HTTP_REFERER", "") or os.getenv("OPENROUTER_REFERER", "")).strip() or None
        self._x_title = (x_title or os.getenv("OPENROUTER_X_TITLE", "")).strip() or None

        # Generic extra params via JSON env (e.g. speed, language, instructions)
        self._extra_params: dict = {}
        if extra_params:
            self._extra_params = dict(extra_params)
        else:
            extra_raw = os.getenv("OPENROUTER_TTS_EXTRA", "").strip()
            if extra_raw:
                try:
                    self._extra_params = _json.loads(extra_raw)
                except Exception as e:
                    logger.warning("OPENROUTER_TTS_EXTRA is not valid JSON (%s) — ignored", e)
            instr = os.getenv("OPENROUTER_TTS_INSTRUCTIONS", "").strip()
            if instr:
                self._extra_params["instructions"] = instr

        # keepalive_expiry پیش‌فرض httpx = 5s است → بین نوبت‌های مکالمه اتصال بسته می‌شد
        self._http = _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),  # per-request override می‌شود
            follow_redirects=True,
            limits=_httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=120.0),
        )
        self._warm_task: asyncio.Task | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openrouter"

    def prewarm(self) -> None:
        """TLS handshake را قبل از اولین نوبت انجام بده (فقط داخل event loop کار می‌کند)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._warm_task is None or self._warm_task.done():
            self._warm_task = loop.create_task(self._warm())

    async def _warm(self) -> None:
        try:
            await self._http.head(self._base_url, timeout=3.0)
        except Exception:
            pass

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> tts.ChunkedStream:
        return OpenRouterChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        if self._warm_task is not None and not self._warm_task.done():
            self._warm_task.cancel()
        await self._http.aclose()


class OpenRouterChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: OpenRouterTTS, input_text: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: OpenRouterTTS = tts  # type: ignore

    def _request_timeout(self) -> _httpx.Timeout:
        t = float(getattr(self._conn_options, "timeout", 10.0) or 10.0)
        # read = فاصلهٔ بین دو تکهٔ بایت (شامل انتظار برای اولین بایت)
        return _httpx.Timeout(connect=min(5.0, t), read=t, write=min(10.0, t), pool=min(5.0, t))

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        text = self.input_text.strip()
        if not text:
            output_emitter.initialize(request_id="", sample_rate=self._tts.sample_rate, num_channels=NUM_CHANNELS, mime_type="audio/pcm", stream=False)
            output_emitter.flush()
            return

        url = f"{self._tts._base_url}/audio/speech"
        payload: dict = {
            "model": self._tts._model,
            "input": text,
            "response_format": self._tts._response_format,
        }
        if self._tts._voice:
            payload["voice"] = self._tts._voice
        if self._tts._extra_params:
            payload.update(self._tts._extra_params)

        headers = {"Authorization": f"Bearer {self._tts._api_key}", "Content-Type": "application/json"}
        if self._tts._http_referer:
            headers["HTTP-Referer"] = self._tts._http_referer
        if self._tts._x_title:
            headers["X-Title"] = self._tts._x_title

        pushed = False
        try:
            async with self._tts._http.stream("POST", url, json=payload, headers=headers, timeout=self._request_timeout()) as resp:
                request_id = resp.headers.get("x-generation-id", "") or resp.headers.get("x-request-id", "") or ""

                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise APIStatusError(
                        f"OpenRouter TTS HTTP {resp.status_code} model={self._tts._model}: {body[:800]}",
                        status_code=resp.status_code,
                        request_id=request_id,
                        body=body,
                    )

                ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if "json" in ct or ct.startswith("text/"):
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise APIStatusError(
                        f"OpenRouter TTS returned non-audio content-type '{ct}' model={self._tts._model}: {body[:800]}",
                        status_code=502,
                        request_id=request_id,
                        body=body,
                    )

                if ct in _AUDIO_MIME:
                    mime_type = ct
                elif self._tts._response_format == "pcm":
                    mime_type = "audio/pcm"
                else:
                    mime_type = "audio/mpeg"

                output_emitter.initialize(
                    request_id=request_id,
                    sample_rate=self._tts.sample_rate,
                    num_channels=NUM_CHANNELS,
                    mime_type=mime_type,
                    stream=False,
                )
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        output_emitter.push(chunk)   # صدا همین‌جا شروع به دیکود/پخش می‌کند
                        pushed = True

            if not pushed:
                raise APIStatusError("OpenRouter TTS returned empty audio", status_code=502, request_id="", body="")
            output_emitter.flush()

        except _httpx.TimeoutException as e:
            err = APITimeoutError()
            err.retryable = not pushed      # بعد از پخش بخشی از صدا retry = صدای تکراری
            raise err from e
        except _httpx.HTTPError as e:
            err = APIConnectionError()
            err.retryable = not pushed
            raise err from e