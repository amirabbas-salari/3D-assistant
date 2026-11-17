"""LiveKit TTS adapter for Gemini's Interactions API (Gemini 3.8 TTS)."""

from __future__ import annotations

import base64

from google import genai
from google.genai.errors import APIError as GeminiAPIError
from livekit.agents import APIConnectionError, APIStatusError, tts, utils
from livekit.agents.types import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS

SAMPLE_RATE = 24000


class GeminiInteractionsTTS(tts.TTS):
    """Synthesize speech through the v1beta Interactions API, not generateContent."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voice_name: str,
        instructions: str,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=1,
        )
        self._model = model
        self._voice_name = voice_name
        self._instructions = instructions
        self._client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "Google Gemini"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _GeminiInteractionsChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
        )

    async def aclose(self) -> None:
        await self._client.aio.aclose()


class _GeminiInteractionsChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: GeminiInteractionsTTS,
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._gemini_tts = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        synth = self._gemini_tts
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=synth.sample_rate,
            num_channels=synth.num_channels,
            mime_type="audio/pcm",
        )
        try:
            events = await synth._client.aio.interactions.create(
                model=synth.model,
                input=[
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": self._input_text,
                                "annotations": [
                                    {
                                        "type": "speech_metadata",
                                        "style": synth._instructions,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                response_format={
                    "type": "audio",
                    "mime_type": "audio/l16",
                    "sample_rate": synth.sample_rate,
                },
                generation_config={
                    "speech_config": [{"voice": synth._voice_name}]
                },
                stream=True,
            )
            async for event in events:
                if event.event_type != "step.delta":
                    continue
                delta = event.delta
                if getattr(delta, "type", None) == "audio" and getattr(delta, "data", None):
                    output_emitter.push(base64.b64decode(delta.data))
        except GeminiAPIError as exc:
            code = int(exc.code or -1)
            raise APIStatusError(
                "Gemini Interactions TTS request failed",
                status_code=code,
                body=exc.message or str(exc),
                retryable=code in {429, 499} or code >= 500,
            ) from exc
        except Exception as exc:
            if isinstance(exc, (APIStatusError, APIConnectionError)):
                raise
            raise APIConnectionError(
                f"Gemini Interactions TTS connection failed: {exc}",
                retryable=True,
            ) from exc
