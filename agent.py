"""Persian LiveKit voice agent with a Tavus-rendered avatar and text fallback."""

import asyncio
import json
import logging
import os
import re

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, RoomOutputOptions, inference
from livekit.plugins import google, tavus

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
                "تو، یک دستیار صوتی فارسی‌زبان، صمیمی، باهوش و دقیق هستی. "
                "همیشه به فارسی روان و طبیعی پاسخ بده، مگر اینکه کاربر صریحاً زبان دیگری بخواهد. "
                "جواب‌ها را برای گفتار کوتاه و روشن نگه دار؛ از نشانه‌گذاری و قالب‌بندی پیچیده پرهیز کن. "
                "اگر پاسخ را نمی‌دانی، صادقانه بگو."
            ),
        )


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "avatar"))
async def entrypoint(ctx: agents.JobContext) -> None:
    async def publish_room_message(message: dict, *, topic: str = "transcript") -> None:
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
    google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    # Accept the former env var as a migration path, but call the Gemini Developer API
    # directly with the AI Studio key (not LiveKit Inference or Vertex AI).
    llm_model = (
        os.getenv("GOOGLE_LLM_MODEL")
        or os.getenv("LIVEKIT_LLM_MODEL")
        or "gemini-3.8-flash"
    ).strip()
    if llm_model.startswith("google/"):
        llm_model = llm_model.removeprefix("google/")
    if not google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for the Google AI Studio Gemini API")

    tts_model = os.getenv("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-tts")
    tts_voice = os.getenv("LIVEKIT_TTS_VOICE", "Kore")
    tts_language = os.getenv("LIVEKIT_TTS_LANGUAGE", "fa")
    job_logger.info(
        "Voice pipeline models: STT=LiveKit Inference/%s (%s), LLM=Google AI Studio/%s, TTS=LiveKit Inference/%s voice=%s (%s)",
        stt_model, stt_language, llm_model, tts_model, tts_voice, tts_language,
    )

    session = AgentSession(
        stt=inference.STT(model=stt_model, language=stt_language),
        llm=google.LLM(model=llm_model, api_key=google_api_key, vertexai=False),
        tts=inference.TTS(model=tts_model, voice=tts_voice, language=tts_language),
    )

    avatar = None
    try:
        avatar_options = {"pal_id": os.environ["TAVUS_PAL_ID"]}
        if os.getenv("TAVUS_FACE_ID"):
            avatar_options["face_id"] = os.environ["TAVUS_FACE_ID"]
        avatar = tavus.AvatarSession(**avatar_options)
        await avatar.start(session, room=ctx.room)
        job_logger.info("Tavus avatar session started; waiting for its participant in background")
    except Exception:
        # A Tavus outage or configuration error must not prevent the voice agent
        # from joining the room and starting STT.
        job_logger.exception("Could not start Tavus avatar; continuing without video")
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
        # Tavus owns audio when available; direct LiveKit output is a fallback.
        room_output_options=RoomOutputOptions(audio_enabled=avatar is None),
    )
    job_logger.info("Agent session started and ready for voice or text input")

    if avatar is not None:
        async def log_avatar_join() -> None:
            try:
                await avatar.wait_for_join(timeout=30)
                job_logger.info("Tavus avatar joined and published its video track")
            except Exception:
                job_logger.exception("Tavus avatar did not join; voice and text input remain active")

        asyncio.create_task(log_avatar_join())

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
