"""Persian LiveKit voice agent with a Tavus-rendered avatar."""

import asyncio
import json
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, inference
from livekit.plugins import openai, tavus

load_dotenv()

server = agents.AgentServer()


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

    session = AgentSession(
        stt=inference.STT(
            model=os.getenv("LIVEKIT_STT_MODEL", "xai/stt-2"),
            language=os.getenv("LIVEKIT_STT_LANGUAGE", "fa"),
        ),
        llm=openai.LLM.with_openrouter(
            model=os.getenv("OPENROUTER_MODEL", "openrouter/auto"),
            app_name="Hamrah Persian Voice Assistant",
        ),
        tts=inference.TTS(
            model=os.getenv("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-tts"),
            voice=os.getenv("LIVEKIT_TTS_VOICE", "Kore"),
            language=os.getenv("LIVEKIT_TTS_LANGUAGE", "fa"),
        ),
    )

    avatar_options = {"pal_id": os.environ["TAVUS_PAL_ID"]}
    if os.getenv("TAVUS_FACE_ID"):
        avatar_options["face_id"] = os.environ["TAVUS_FACE_ID"]
    avatar = tavus.AvatarSession(**avatar_options)
    await avatar.start(session, room=ctx.room)

    async def publish_user_transcript(event) -> None:
        text = (event.transcript or "").strip()
        if not text:
            return
        payload = json.dumps(
            {"type": "user_transcript", "text": text, "final": event.is_final},
            ensure_ascii=False,
        )
        await ctx.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic="transcript",
        )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        asyncio.create_task(publish_user_transcript(event))

    await session.start(agent=PersianAssistant(), room=ctx.room)

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
    agents.cli.run_app(server)
