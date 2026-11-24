"""Generic OpenRouter TTS — any model via audio/speech.

Uses OpenRouter's OpenAI-compatible endpoint:
  POST https://openrouter.ai/api/v1/audio/speech
  { model: "<OPENROUTER_TTS_MODEL>", input: "text", voice: "...", response_format: "mp3" }
→ raw audio bytes

Supports switching model with only:
  OPENROUTER_TTS_MODEL=openai/tts-1
  OPENROUTER_TTS_MODEL=google/gemini-2.5-flash-tts
  OPENROUTER_TTS_MODEL=elevenlabs/eleven-v3-conversational
  OPENROUTER_TTS_MODEL=minimax/minimax-speech-02-hd
etc. Voice/response_format are optional per model.

Docs: https://openrouter.ai/docs/guides/overview/multimodal/tts
"""

from __future__ import annotations

import os
import json as _json

try:
    import httpx as _httpx  # type: ignore
except ImportError:
    import httpx2 as _httpx  # type: ignore

from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

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


def _normalize_voice(voice: str, model: str) -> str | None:
    """Return normalized voice or None if not needed.
    For elevenlabs models default to george, for others keep empty to omit.
    """
    v = (voice or "").strip()
    if not v:
        # No voice specified — only default for elevenlabs family for backward compat
        if "elevenlabs" in model.lower():
            return "george"
        return None
    if v in _LEGACY_VOICE_MAP:
        return _LEGACY_VOICE_MAP[v]
    if len(v) > 18 and v.isalnum():
        # Looks like legacy ID, map to george for elevenlabs else drop
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
        self._base_url = (base_url or os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)).strip() or DEFAULT_BASE_URL
        self._base_url = self._base_url.rstrip("/")
        self._model = (model or os.getenv("OPENROUTER_TTS_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        # Warn if model looks invalid — fish-audio/drama-3 → fish-audio/fish-speech-1.5
        if self._model == "fish-audio/drama-3":
            # Common mistake: drama-3 is not on OpenRouter
            import logging
            logging.getLogger("sam.speech.openrouter_tts").warning(
                "OPENROUTER_TTS_MODEL=fish-audio/drama-3 not on OpenRouter (400). Did you mean fish-audio/fish-speech-1.5? See https://openrouter.ai/models?fmt=audio"
            )
        if self._model not in KNOWN_TTS_MODELS:
            import logging
            # Still allow custom models, just log hint
            logging.getLogger("sam.speech.openrouter_tts").info(
                "OPENROUTER_TTS_MODEL=%s not in known list, will try anyway (if 400, check https://openrouter.ai/models?fmt=audio)", self._model
            )

        # Voice — generic: any model can have voice, but don't force it
        raw_voice = (
            (voice or "").strip()
            or os.getenv("OPENROUTER_TTS_VOICE", "").strip()
            or os.getenv("OPENROUTER_VOICE", "").strip()
            or os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        )
        self._voice = _normalize_voice(raw_voice, self._model)

        # Response format — let user control, normalize common aliases
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
        # OPENROUTER_TTS_EXTRA='{"speed": 1.0, "language": "fa"}'
        self._extra_params: dict = {}
        if extra_params:
            self._extra_params = extra_params
        else:
            extra_raw = os.getenv("OPENROUTER_TTS_EXTRA", "").strip()
            if extra_raw:
                try:
                    self._extra_params = _json.loads(extra_raw)
                except Exception:
                    pass
            # Also support instructions/prompt for models like openai/gpt-4o-mini-tts
            instr = os.getenv("OPENROUTER_TTS_INSTRUCTIONS", "").strip()
            if instr:
                self._extra_params["instructions"] = instr

        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for TTS_PROVIDER=openrouter (https://openrouter.ai/settings/keys)")

        self._http = _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
            follow_redirects=True,
            limits=_httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openrouter"

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> tts.ChunkedStream:
        return OpenRouterChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        await self._http.aclose()


class OpenRouterChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: OpenRouterTTS, input_text: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: OpenRouterTTS = tts  # type: ignore

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
        # Only send voice if model needs it (elevenlabs, openai tts, etc.)
        if self._tts._voice:
            payload["voice"] = self._tts._voice
        # Merge generic extra params (speed, language, instructions, etc.)
        if self._tts._extra_params:
            payload.update(self._tts._extra_params)

        headers = {"Authorization": f"Bearer {self._tts._api_key}", "Content-Type": "application/json"}
        if self._tts._http_referer:
            headers["HTTP-Referer"] = self._tts._http_referer
        if self._tts._x_title:
            headers["X-Title"] = self._tts._x_title

        try:
            resp = await self._tts._http.post(url, json=payload, headers=headers)
        except _httpx.TimeoutException as e:
            raise APITimeoutError() from e
        except Exception as e:
            raise APIConnectionError() from e

        if resp.status_code != 200:
            try:
                body = resp.text
            except Exception:
                body = ""
            raise APIStatusError(
                f"OpenRouter TTS HTTP {resp.status_code} model={self._tts._model}: {body[:800]}",
                status_code=resp.status_code,
                request_id=resp.headers.get("x-request-id", "") or resp.headers.get("x-generation-id", ""),
                body=body,
            )

        audio_bytes = resp.content
        if not audio_bytes:
            raise APIStatusError("OpenRouter TTS returned empty audio", status_code=200, request_id="", body="")

        ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if ct in {"audio/mpeg", "audio/mp3", "audio/ogg", "audio/opus", "audio/wav", "audio/webm", "audio/pcm"}:
            mime_type = ct
        elif self._tts._response_format == "mp3":
            mime_type = "audio/mpeg"
        elif self._tts._response_format == "pcm":
            mime_type = "audio/pcm"
        else:
            mime_type = "audio/mpeg"

        output_emitter.initialize(
            request_id=resp.headers.get("x-generation-id", "") or resp.headers.get("x-request-id", "") or "",
            sample_rate=self._tts.sample_rate,
            num_channels=NUM_CHANNELS,
            mime_type=mime_type,
            stream=False,
        )
        output_emitter.push(audio_bytes)
        output_emitter.flush()
