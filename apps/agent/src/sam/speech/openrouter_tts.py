"""OpenRouter TTS via elevenlabs/eleven-v3-conversational.

Uses OpenRouter's OpenAI-compatible Audio Speech endpoint:
  POST https://openrouter.ai/api/v1/audio/speech
  { model: "elevenlabs/eleven-v3-conversational", input: "text", voice: "george", response_format: "mp3" }
→ raw audio bytes (audio/mpeg or audio/pcm)

Non-streaming (ChunkedStream). Wrapped by SDK StreamAdapter for sentence-level streaming.
Docs: https://openrouter.ai/docs/guides/overview/multimodal/tts
"""

from __future__ import annotations

import os

try:
    import httpx as _httpx  # type: ignore
except ImportError:
    import httpx2 as _httpx  # type: ignore  # livekit's alias

from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

SAMPLE_RATE = 24000
NUM_CHANNELS = 1

DEFAULT_MODEL = "elevenlabs/eleven-v3-conversational"
DEFAULT_VOICE = "george"
DEFAULT_RESPONSE_FORMAT = "mp3"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Map legacy ElevenLabs voice IDs (from Cloudflare) to OpenRouter voice names
_LEGACY_VOICE_MAP = {
    "JBFqnCBsd6RMkjVDRZzb": "george",
    "21m00Tcm4TlvDq8ikWAM": "rachel",
    "EXAVITQu4vr4xnSDxMaL": "sarah",
    "FGY2WhTYpPnrIDTqs33q": "bella",
    "IKne3meq5aSn9XLyUdCD": "charlie",
    "JBFqnCBsd6RMkjVDRZzb": "george",
    "On5p47yCR6tAlT5xT1oY": "adam",
    "TxGEqnHWznW5bvQe8BfY": "jessica",
    "ThT5KcBeYPX3keUQqHPh": "daniel",
    "pFZP5JQG7iQjIQuC4Bku": "lily",
    "XB0fDUnXU5powFXDhCwa": "charlotte",
}


def _normalize_voice(voice: str) -> str:
    v = (voice or "").strip()
    if not v:
        return DEFAULT_VOICE
    # Legacy ID -> name
    if v in _LEGACY_VOICE_MAP:
        return _LEGACY_VOICE_MAP[v]
    # If it looks like a legacy ID (20+ alphanum, mixed case), default to george
    if len(v) > 18 and v.isalnum():
        return DEFAULT_VOICE
    return v.lower()


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
        raw_voice = (
            voice
            or os.getenv("OPENROUTER_TTS_VOICE", "")
            or os.getenv("OPENROUTER_VOICE", "")
            or os.getenv("ELEVENLABS_VOICE_ID", "")
        ).strip()
        self._voice = _normalize_voice(raw_voice) if raw_voice else DEFAULT_VOICE
        self._response_format = (
            response_format
            or os.getenv("OPENROUTER_TTS_RESPONSE_FORMAT", "")
            or os.getenv("OPENROUTER_RESPONSE_FORMAT", "")
            or DEFAULT_RESPONSE_FORMAT
        ).strip() or DEFAULT_RESPONSE_FORMAT
        # Normalize: openrouter expects "mp3" or "pcm"
        if self._response_format.lower() in {"mp3_44100_128", "mp3_22050_32", "mp3"}:
            self._response_format = "mp3"
        elif self._response_format.lower() in {"pcm", "pcm_24000", "pcm_16000", "pcm_44100"}:
            self._response_format = "pcm"

        self._http_referer = (http_referer or os.getenv("OPENROUTER_HTTP_REFERER", "") or os.getenv("OPENROUTER_REFERER", "")).strip() or None
        self._x_title = (x_title or os.getenv("OPENROUTER_X_TITLE", "")).strip() or None

        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for TTS_PROVIDER=openrouter (get one at https://openrouter.ai/settings/keys)")

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

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
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
            output_emitter.initialize(
                request_id="",
                sample_rate=self._tts.sample_rate,
                num_channels=NUM_CHANNELS,
                mime_type="audio/pcm",
                stream=False,
            )
            output_emitter.flush()
            return

        url = f"{self._tts._base_url}/audio/speech"
        payload: dict = {
            "model": self._tts._model,
            "input": text,
            "voice": self._tts._voice,
            "response_format": self._tts._response_format,
        }

        headers = {
            "Authorization": f"Bearer {self._tts._api_key}",
            "Content-Type": "application/json",
        }
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
                f"OpenRouter TTS HTTP {resp.status_code}: {body[:800]}",
                status_code=resp.status_code,
                request_id=resp.headers.get("x-request-id", "") or resp.headers.get("x-generation-id", ""),
                body=body,
            )

        # Success: raw audio bytes
        audio_bytes = resp.content
        if not audio_bytes:
            raise APIStatusError("OpenRouter TTS returned empty audio", status_code=200, request_id="", body="")

        # Infer mime from response headers or requested format
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
