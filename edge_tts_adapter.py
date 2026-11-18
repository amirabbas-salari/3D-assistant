"""LiveKit TTS adapter for Microsoft Edge's neural speech service."""

from __future__ import annotations

from typing import Any

import av
import edge_tts
from livekit.agents import APIConnectionError, tts, utils
from livekit.agents.types import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS

SAMPLE_RATE = 24000


class EdgeNeuralTTS(tts.TTS):
    """Synthesize speech with edge-tts and decode its MP3 stream to LiveKit PCM."""

    def __init__(
        self,
        *,
        voice: str = "fa-IR-DilaraNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=1,
        )
        self._voice = voice
        self._rate = rate
        self._pitch = pitch

    @property
    def model(self) -> str:
        return "Microsoft Edge Neural TTS"

    @property
    def provider(self) -> str:
        return "Microsoft Edge TTS"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _EdgeTTSChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
        )


class _EdgeTTSChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: EdgeNeuralTTS,
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._edge_tts = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        tts_config = self._edge_tts
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=tts_config.sample_rate,
            num_channels=tts_config.num_channels,
            mime_type="audio/pcm",
        )

        decoder = av.CodecContext.create("mp3", "r")
        resampler = av.AudioResampler(
            format="s16",
            layout="mono",
            rate=tts_config.sample_rate,
        )

        def emit_frame(frame: Any) -> None:
            for pcm_frame in resampler.resample(frame):
                output_emitter.push(pcm_frame.to_ndarray().tobytes())

        def decode_mp3(data: bytes) -> None:
            for packet in decoder.parse(data):
                for frame in decoder.decode(packet):
                    emit_frame(frame)

        try:
            communicate = edge_tts.Communicate(
                text=self._input_text,
                voice=tts_config._voice,
                rate=tts_config._rate,
                pitch=tts_config._pitch,
            )
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    decode_mp3(chunk["data"])

            # Flush any final parser, decoder, and resampler data.
            decode_mp3(b"")
            for frame in decoder.decode(None):
                emit_frame(frame)
            for pcm_frame in resampler.resample(None):
                output_emitter.push(pcm_frame.to_ndarray().tobytes())
        except Exception as exc:
            if isinstance(exc, (APIConnectionError,)):
                raise
            raise APIConnectionError(
                f"Microsoft Edge TTS request failed: {exc}",
                retryable=True,
            ) from exc
