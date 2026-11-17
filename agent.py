"""Persian LiveKit voice agent with a Spatius-rendered avatar and text fallback."""

import asyncio
import json
import logging
import os
import re

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, RoomOutputOptions, inference
from livekit.plugins import openai, spatius
from gemini_interactions_tts import GeminiInteractionsTTS

load_dotenv()

server = agents.AgentServer()
logger = logging.getLogger("hamrah-voice-agent")
_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|secret|token)(\s*[:=]\s*)[^\s,;]+")


def _redact_log_text(value: str) -> str:
    return _SECRET_PATTERN.sub(r"\1\2[REDACTED]", value)


class RoomLogHandler(logging.Handler):
    """Forward this job's app logs to the connected browser diagnostics panel."""

    def __init__(self, publish_log) -> None:
        super().__init__(level=logging.INFO)
        self._publish_log = publish_log
        self._formatter = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            details = self._formatter.formatException(record.exc_info) if record.exc_info else ""
            payload = {
                "type": "system_log",
                "level": record.levelname.lower(),
                "message": _redact_log_text(record.getMessage())[:1600],
                "details": _redact_log_text(details)[:2600],
                "logger": record.name,
            }
            asyncio.get_running_loop().create_task(self._publish_log(payload))
        except Exception:
            self.handleError(record)


class PersianAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "تو همراه، یک دستیار صوتی فارسی‌زبان، صمیمی، باهوش و دقیق هستی. "
                "همیشه به فارسی روان و طبیعی پاسخ بده، مگر اینکه کاربر صریحاً زبان دیگری بخواهد. "
                "جواب‌ها را برای گفتار کوتاه و روشن نگه دار؛ از نشانه‌گذاری و قالب‌بندی پیچیده پرهیز کن. "
                "اگر پاسخ را نمی‌دانی، صادقانه بگو."
            ),
        )


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "hamrah-agent"))
async def entrypoint(ctx: agents.JobContext) -> None:
    # Spatius registers room RPC handlers, so connect before starting the avatar.
    # AgentSession.start() reuses this connection.
    await ctx.connect()

    async def publish_room_message(message: dict, *, topic: str = "transcript") -> None:
        if not ctx.room.isconnected():
            return
        try:
            await ctx.room.local_participant.publish_data(
                json.dumps(message, ensure_ascii=False),
                reliable=True,
                topic=topic,
            )
        except Exception:
            # Avoid recursive diagnostics if the diagnostics channel itself fails.
            logger.warning("Could not publish room data message on topic %s", topic, exc_info=True)

    job_logger = logging.getLogger(f"hamrah-voice-agent.{ctx.job.id}")
    job_logger.setLevel(logging.INFO)
    room_log_handler = RoomLogHandler(
        lambda message: publish_room_message(message, topic="diagnostics")
    )
    job_logger.addHandler(room_log_handler)

    async def detach_room_log_handler() -> None:
        job_logger.removeHandler(room_log_handler)
        room_log_handler.close()

    ctx.add_shutdown_callback(detach_room_log_handler)

    stt_model = os.getenv("LIVEKIT_STT_MODEL", "deepgram/nova-3")
    stt_language = os.getenv("LIVEKIT_STT_LANGUAGE", "fa")
    cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    llm_model = os.getenv(
        "CLOUDFLARE_LLM_MODEL",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    ).strip()
    if not cloudflare_account_id or not cloudflare_api_token:
        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required for Cloudflare Workers AI"
        )
    cloudflare_base_url = (
        f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/ai/v1"
    )

    google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    tts_model = os.getenv("GOOGLE_TTS_MODEL", "gemini-3.8-flash-lite-tts").strip()
    tts_voice = os.getenv("GOOGLE_TTS_VOICE", "Kore").strip()
    tts_instructions = os.getenv(
        "GOOGLE_TTS_INSTRUCTIONS",
        "Speak naturally in Persian with a warm, friendly, conversational tone. Preserve the exact text.",
    ).strip()
    if not google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for Gemini TTS")

    job_logger.info(
        "Voice pipeline models: STT=LiveKit Inference/%s (%s), LLM=Cloudflare Workers AI/%s, TTS=Google Gemini/%s voice=%s",
        stt_model, stt_language, llm_model, tts_model, tts_voice,
    )

    session = AgentSession(
        stt=inference.STT(model=stt_model, language=stt_language),
        llm=openai.LLM(model=llm_model, api_key=cloudflare_api_token, base_url=cloudflare_base_url),
        tts=GeminiInteractionsTTS(
            api_key=google_api_key,
            model=tts_model,
            voice_name=tts_voice,
            instructions=tts_instructions,
        ),
    )

    avatar = None
    spatius_sample_rate = int(os.getenv("SPATIUS_SAMPLE_RATE", "24000"))
    try:
        # Gemini TTS emits 24 kHz audio; keep Spatius on a supported Ogg Opus rate.
        avatar = spatius.AvatarSession(sample_rate=spatius_sample_rate)
        await avatar.start(session, room=ctx.room)
        job_logger.info(
            "Spatius avatar session started (audio sample rate: %s Hz)",
            spatius_sample_rate,
        )
    except Exception:
        # Spatius setup errors should not prevent voice/text fallback from running.
        job_logger.exception("Could not start Spatius avatar; continuing without avatar")
        avatar = None

    async def publish_user_transcript(event) -> None:
        text = (event.transcript or "").strip()
        if text:
            await publish_room_message(
                {"type": "user_transcript", "text": text, "final": event.is_final}
            )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        asyncio.create_task(publish_user_transcript(event))

    @session.on("error")
    def on_session_error(event) -> None:
        job_logger.error("AgentSession %s error: %s", event.source, event.error)

    async def publish_assistant_reply(text: str) -> None:
        await publish_room_message({"type": "assistant_reply", "text": text})

    @session.on("conversation_item_added")
    def on_conversation_item_added(event) -> None:
        item = event.item
        role = getattr(item, "role", None)
        if role == "user":
            text = (getattr(item, "text_content", "") or "").strip()
            if text:
                job_logger.info("User turn committed (%d characters)", len(text))
        elif role == "assistant":
            text = (getattr(item, "text_content", "") or "").strip()
            job_logger.info("LLM produced assistant text (%d characters)", len(text))
            if text:
                asyncio.create_task(publish_assistant_reply(text))

    @session.on("agent_state_changed")
    def on_agent_state_changed(event) -> None:
        job_logger.info("Assistant state: %s -> %s", event.old_state, event.new_state)

    async def respond_to_text(text: str, sender: str) -> None:
        job_logger.info("Text chat input received from %s (%d characters)", sender, len(text))
        try:
            session.interrupt()
            speech_handle = session.generate_reply(user_input=text)
            await speech_handle
            if speech_handle.exception():
                job_logger.error("Text chat reply failed: %s", speech_handle.exception())
        except Exception:
            job_logger.exception("Could not generate a reply to text chat input")

    def on_room_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != "chat-input":
            return
        try:
            message = json.loads(packet.data.decode("utf-8"))
            if message.get("type") != "chat_input":
                return
            text = str(message.get("text", "")).strip()[:4000]
            if not text:
                return
            sender = packet.participant.identity if packet.participant else "unknown"
            asyncio.create_task(respond_to_text(text, sender))
        except Exception:
            job_logger.exception("Invalid text chat data packet")

    ctx.room.on("data_received", on_room_data_received)

    await session.start(
        agent=PersianAssistant(),
        room=ctx.room,
        # Spatius publishes synchronized speech audio; direct LiveKit output is the fallback.
        room_output_options=RoomOutputOptions(audio_enabled=avatar is None),
    )
    job_logger.info("Agent session started and ready for voice or text input")

    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    opening_line = str(metadata.get("opening_line", "")).strip()[:300]
    if opening_line:
        greeting = f"به فارسی سلام کن و به این خواسته پاسخ بده: {opening_line}"
    else:
        greeting = "به فارسی گرم و کوتاه سلام کن و بپرس امروز چطور می‌توانی کمک کنی."
    session.generate_reply(instructions=greeting)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    agents.cli.run_app(server)
