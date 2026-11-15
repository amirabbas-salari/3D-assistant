"""Persian LiveKit voice agent with a Tavus-rendered avatar."""

import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomOutputOptions, inference
from livekit.plugins import openai, tavus

load_dotenv()

server = agents.AgentServer()
logger = logging.getLogger("hamrah-voice-agent")


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
    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is required to run the assistant LLM")

    stt_model = os.getenv("LIVEKIT_STT_MODEL", "deepgram/nova-3")
    stt_language = os.getenv("LIVEKIT_STT_LANGUAGE", "fa")
    llm_model = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
    tts_model = os.getenv("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-tts")
    tts_voice = os.getenv("LIVEKIT_TTS_VOICE", "Kore")
    tts_language = os.getenv("LIVEKIT_TTS_LANGUAGE", "fa")
    logger.info(
        "Voice pipeline models: STT=%s (%s), LLM=OpenRouter/%s, TTS=%s voice=%s (%s)",
        stt_model, stt_language, llm_model, tts_model, tts_voice, tts_language,
    )

    session = AgentSession(
        stt=inference.STT(model=stt_model, language=stt_language),
        llm=openai.LLM.with_openrouter(
            model=llm_model,
            app_name="Hamrah Persian Voice Assistant",
        ),
        tts=inference.TTS(
            model=tts_model,
            voice=tts_voice,
            language=tts_language,
        ),
    )

    avatar = None
    avatar_ready = False
    try:
        avatar_options = {"pal_id": os.environ["TAVUS_PAL_ID"]}
        if os.getenv("TAVUS_FACE_ID"):
            avatar_options["face_id"] = os.environ["TAVUS_FACE_ID"]
        avatar = tavus.AvatarSession(**avatar_options)
        await avatar.start(session, room=ctx.room)
        logger.info("Tavus avatar session started")
        # Keep the known-good ordering: let Tavus join and publish video before
        # AgentSession starts routing the first response through the avatar.
        await avatar.wait_for_join(timeout=30)
        avatar_ready = True
        logger.info("Tavus avatar joined and published its video track")
    except Exception:
        # A Tavus outage or configuration error must not permanently block STT.
        # The bounded wait falls back to the normal LiveKit audio output.
        logger.exception("Tavus avatar failed to start or join; continuing without video")
        avatar = None

    async def publish_room_message(message: dict) -> None:
        try:
            await ctx.room.local_participant.publish_data(
                json.dumps(message, ensure_ascii=False),
                reliable=True,
                topic="transcript",
            )
        except Exception:
            logger.warning("Could not publish conversation text to the browser", exc_info=True)

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
        # Identifies whether a failed turn came from the LLM, STT, or TTS.
        logger.error("AgentSession %s error: %s", event.source, event.error)

    async def publish_assistant_reply(text: str) -> None:
        await publish_room_message({"type": "assistant_reply", "text": text})

    @session.on("conversation_item_added")
    def on_conversation_item_added(event) -> None:
        item = event.item
        if getattr(item, "role", None) == "assistant":
            text = (getattr(item, "text_content", "") or "").strip()
            logger.info("LLM produced assistant text (%d chars)", len(text))
            if text:
                asyncio.create_task(publish_assistant_reply(text))

    @session.on("agent_state_changed")
    def on_agent_state_changed(event) -> None:
        logger.info("Assistant state: %s -> %s", event.old_state, event.new_state)

    await session.start(
        agent=PersianAssistant(),
        room=ctx.room,
        # Tavus owns audio only once its participant/video track is ready; if it
        # failed or timed out, use direct LiveKit audio as a fallback.
        room_output_options=RoomOutputOptions(audio_enabled=not avatar_ready),
    )

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
