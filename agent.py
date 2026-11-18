"""Persian LiveKit voice agent with a pluggable avatar (D-ID or Spatius) and text fallback."""

import asyncio
import json
import logging
import os
import re

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import (
    APIConnectOptions,
    APIStatusError,
    Agent,
    AgentSession,
    RoomOutputOptions,
    SessionConnectOptions,
    inference,
)
from livekit.plugins import openai

# Avatar plugins MUST be imported here, not inside the job: every plugin registers
# itself on import and Plugin.register_plugin() insists on the main thread. On
# Windows LiveKit runs jobs in threads (JobExecutorType.THREAD), so a lazy import
# inside entrypoint raises "Plugins must be registered on the main thread" and
# kills the job. Importing at module level keeps registration on the main thread
# on every platform; a missing package is reported when an avatar is requested.
try:
    from livekit.plugins import did as did_plugin

    _did_import_error = None
except ImportError as exc:  # pragma: no cover - depends on the installed extras
    did_plugin = None
    _did_import_error = exc

try:
    from livekit.plugins import spatius as spatius_plugin

    _spatius_import_error = None
except ImportError as exc:  # pragma: no cover - depends on the installed extras
    spatius_plugin = None
    _spatius_import_error = exc

# Direct-provider speech plugins. They bypass the LiveKit Inference gateway, so
# they keep working when the project's Inference credit quota is exhausted.
try:
    from livekit.plugins import deepgram as deepgram_plugin

    _deepgram_import_error = None
except ImportError as exc:  # pragma: no cover - depends on the installed extras
    deepgram_plugin = None
    _deepgram_import_error = exc

try:
    from livekit.plugins import google as google_plugin

    _google_import_error = None
except ImportError as exc:  # pragma: no cover - depends on the installed extras
    google_plugin = None
    _google_import_error = exc

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


def _avatar_provider() -> str:
    """Which avatar backend to run, or "none" to publish plain audio.

    AVATAR_ENABLED=false always wins so the voice pipeline can be tested alone.
    AVATAR_PROVIDER picks the backend; an unset value keeps backwards
    compatibility with the Spatius-only setup that existed before D-ID.
    """
    enabled = os.getenv("AVATAR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return "none"
    provider = os.getenv("AVATAR_PROVIDER", "spatius").strip().lower()
    if provider in {"", "none", "off", "false"}:
        return "none"
    if provider not in {"did", "d-id", "didid"}:
        return "spatius"
    return "did"


async def start_avatar(provider: str, session: AgentSession, room: rtc.Room, job_logger):
    """Start the configured avatar and return it, or None to fall back to plain audio.

    Both providers replace the session's audio tail and publish the avatar's
    own audio and video tracks, so the caller only needs to keep the returned
    object alive (or aclose it).
    """
    if provider == "did":
        agent_id = os.getenv("DID_AGENT_ID", "").strip()
        if not agent_id:
            job_logger.error("D-ID avatar selected but DID_AGENT_ID is empty; continuing without avatar")
            return None
        if did_plugin is None:
            job_logger.error(
                "livekit-plugins-did could not be imported (%s); "
                "run pip install -r requirements.txt",
                _did_import_error,
            )
            return None

        sample_rate = int(os.getenv("DID_AUDIO_SAMPLE_RATE", "24000"))
        try:
            avatar = did_plugin.AvatarSession(
                agent_id=agent_id,
                audio_config=did_plugin.AudioConfig(sample_rate=sample_rate),
            )
            await avatar.start(session, room)
        except Exception:
            job_logger.exception("Could not start the D-ID avatar; continuing without avatar")
            return None
        job_logger.info(
            "D-ID avatar session started (agent=%s, session=%s, sample rate: %s Hz)",
            agent_id, getattr(avatar, "session_id", None), sample_rate,
        )
        return avatar

    if provider == "spatius":
        if spatius_plugin is None:
            job_logger.error(
                "livekit-plugins-spatius could not be imported (%s); "
                "run pip install -r requirements.txt",
                _spatius_import_error,
            )
            return None

        sample_rate = int(os.getenv("SPATIUS_SAMPLE_RATE", "24000"))
        audio_format = os.getenv("SPATIUS_AUDIO_FORMAT", "pcm_s16le").strip().lower()
        try:
            # PCM avoids requiring a system libopus DLL on Windows. Ogg Opus is optional.
            avatar = spatius_plugin.AvatarSession(sample_rate=sample_rate, audio_format=audio_format)
            await avatar.start(session, room)
        except Exception:
            job_logger.exception("Could not start the Spatius avatar; continuing without avatar")
            return None
        job_logger.info(
            "Spatius avatar session started (audio sample rate: %s Hz, format: %s)",
            sample_rate, audio_format,
        )
        return avatar

    return None


def _speech_provider() -> str:
    """Where STT and TTS come from: "inference" (LiveKit gateway) or "direct".

    The Build-plan allowance for LiveKit Inference is a hard monthly cap: once
    it is spent the gateway rejects every STT and TTS connection with
    429 "credit quota exhausted" and nothing in the SDK can recover. Pointing
    the same two models at the providers' own APIs avoids that ceiling at the
    cost of one extra key each.
    """
    provider = os.getenv("SPEECH_PROVIDER", "inference").strip().lower()
    return "direct" if provider in {"direct", "byok", "provider", "own-keys"} else "inference"


def build_stt(provider: str, *, model: str, language: str, conn_options: APIConnectOptions,
              fallback: list[str], job_logger):
    """Build the STT model for the selected speech provider."""
    if provider == "direct":
        api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "SPEECH_PROVIDER=direct needs DEEPGRAM_API_KEY (STT). "
                "Set it in .env or switch back to SPEECH_PROVIDER=inference."
            )
        if deepgram_plugin is None:
            raise RuntimeError(
                "livekit-plugins-deepgram could not be imported "
                f"({_deepgram_import_error}); run pip install -r requirements.txt"
            )
        # The Inference model name is "provider/model"; the plugin wants the bare model.
        model_name = model.split("/", 1)[-1] if "/" in model else model
        job_logger.info("STT via Deepgram API directly (model=%s, language=%s)", model_name, language)
        return deepgram_plugin.STT(model=model_name, language=language, api_key=api_key)

    return inference.STT(
        model=model,
        language=language,
        conn_options=conn_options,
        # fallback must be omitted (not None) when unused: the plugin parses
        # every given value as a model name.
        **({"fallback": fallback} if fallback else {}),
    )


def build_tts(provider: str, *, model: str, voice: str, language: str,
              conn_options: APIConnectOptions, job_logger):
    """Build the TTS model for the selected speech provider."""
    if provider == "direct":
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "SPEECH_PROVIDER=direct needs GOOGLE_API_KEY (TTS). "
                "Set it in .env or switch back to SPEECH_PROVIDER=inference."
            )
        if google_plugin is None:
            raise RuntimeError(
                "livekit-plugins-google could not be imported "
                f"({_google_import_error}); run pip install -r requirements.txt"
            )
        model_name = model.split("/", 1)[-1] if "/" in model else model
        # GeminiTTS has no language parameter: the voices are multilingual and the
        # language comes from the text, so LIVEKIT_TTS_LANGUAGE only applies to
        # the Inference path. Logged so the difference is not a surprise.
        job_logger.info(
            "TTS via Google Gemini API directly (model=%s, voice=%s); Gemini picks the "
            "language from the text, so the %s setting is not sent",
            model_name, voice, language,
        )
        return google_plugin.beta.GeminiTTS(
            model=model_name,
            voice_name=voice,
            api_key=api_key,
        )

    return inference.TTS(
        model=model,
        voice=voice,
        language=language,
        conn_options=conn_options,
    )


def _validate_speech_config() -> None:
    """Fail at worker startup, not in the middle of the first session.

    A missing key in ``direct`` mode would otherwise only surface once a user
    joins, as a dead microphone. Raising here means ``python agent.py dev``
    prints the fix before anything else happens.
    """
    if _speech_provider() != "direct":
        return
    missing = [
        name
        for name in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY")
        if not (os.getenv(name) or "").strip()
    ]
    if missing:
        raise RuntimeError(
            f"SPEECH_PROVIDER=direct requires {', '.join(missing)}. "
            "Add them to .env, or set SPEECH_PROVIDER=inference to use the "
            "LiveKit Inference gateway instead."
        )


_validate_speech_config()


class PersianAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "تو همراه، یک دستیار صوتی فارسی‌زبان با صدای مرد، صمیمی، باهوش و دقیق هستی. "
                "هرگاه درباره‌ی جنسیت یا صدای خودت پرسیدند، بگو صدای مرد داری. "
                "همیشه به فارسی روان و طبیعی پاسخ بده، مگر اینکه کاربر صریحاً زبان دیگری بخواهد. "
                "پاسخ‌های معمولی را برای گفتار کوتاه و روشن نگه دار؛ از نشانه‌گذاری و قالب‌بندی پیچیده پرهیز کن. "
                "اگر کاربر متنی را برای روخوانی، تکرار یا بازگویی می‌فرستد، متن را کامل و بدون خلاصه‌کردن یا حذف در پاسخ بیاور تا TTS آن را بخواند. "
                "در این حالت هرگز نگو امکان پخش یا خواندن صدا را نداری. "
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
    # Comma-separated Inference model names tried server-side when the primary
    # provider for the language fails, e.g. "assemblyai/universal-streaming".
    stt_fallback_models = [
        item.strip()
        for item in os.getenv("LIVEKIT_STT_FALLBACK", "").split(",")
        if item.strip()
    ]
    cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    llm_model = os.getenv(
        "CLOUDFLARE_LLM_MODEL",
    ).strip()
    try:
        llm_max_tokens = int(os.getenv("CLOUDFLARE_LLM_MAX_TOKENS", "8192"))
    except ValueError as exc:
        raise RuntimeError("CLOUDFLARE_LLM_MAX_TOKENS must be a positive integer") from exc
    if not 1 <= llm_max_tokens <= 24000:
        raise RuntimeError("CLOUDFLARE_LLM_MAX_TOKENS must be between 1 and 24000")
    if not cloudflare_account_id or not cloudflare_api_token:
        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required for Cloudflare Workers AI"
        )
    cloudflare_base_url = (
        f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/ai/v1"
    )

    tts_model = os.getenv("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-lite-tts").strip()
    # Charon is a male Gemini voice; Kore (the previous default) is female.
    tts_voice = os.getenv("LIVEKIT_TTS_VOICE", "Charon").strip() or "Charon"
    tts_language = os.getenv("LIVEKIT_TTS_LANGUAGE", "fa").strip() or "fa"

    # LiveKit Inference rejects connections with HTTP 429 once the project's
    # concurrent STT/TTS limit is reached. The SDK retries a few times with a
    # fixed short interval and then gives up for the rest of the turn, which is
    # what turns a brief burst into a dead microphone in the middle of a session.
    # Waiting longer and retrying more keeps the session alive across a burst.
    inference_conn_options = APIConnectOptions(
        max_retry=int(os.getenv("LIVEKIT_INFERENCE_MAX_RETRY", "6")),
        retry_interval=float(os.getenv("LIVEKIT_INFERENCE_RETRY_INTERVAL", "3.0")),
        timeout=float(os.getenv("LIVEKIT_INFERENCE_TIMEOUT", "15.0")),
    )
    # The retry loop a stream actually runs on is the one the session hands it,
    # not the one on the STT/TTS object (that only becomes a hint sent to the
    # gateway), so the same options must also reach AgentSession.
    session_conn_options = SessionConnectOptions(
        stt_conn_options=inference_conn_options,
        tts_conn_options=inference_conn_options,
        # A short burst used to close the whole session after three failures.
        max_unrecoverable_errors=int(os.getenv("LIVEKIT_MAX_UNRECOVERABLE_ERRORS", "8")),
    )

    speech_provider = _speech_provider()
    stt = build_stt(
        speech_provider,
        model=stt_model,
        language=stt_language,
        conn_options=inference_conn_options,
        fallback=stt_fallback_models,
        job_logger=job_logger,
    )
    tts = build_tts(
        speech_provider,
        model=tts_model,
        voice=tts_voice,
        language=tts_language,
        conn_options=inference_conn_options,
        job_logger=job_logger,
    )

    job_logger.info(
        "Voice pipeline models: STT=%s/%s (%s), LLM=Cloudflare Workers AI/%s (max_tokens=%s), TTS=%s/%s voice=%s (%s)",
        "Deepgram API" if speech_provider == "direct" else "LiveKit Inference",
        stt_model, stt_language,
        llm_model, llm_max_tokens,
        "Google API" if speech_provider == "direct" else "LiveKit Inference",
        tts_model, tts_voice, tts_language,
    )

    session = AgentSession(
        stt=stt,
        llm=openai.LLM(
            model=llm_model,
            api_key=cloudflare_api_token,
            base_url=cloudflare_base_url,
            # Workers AI otherwise defaults to 256 output tokens for this model.
            extra_body={"max_tokens": llm_max_tokens},
        ),
        tts=tts,
        conn_options=session_conn_options,
    )

    # The avatar only drives rendering; STT, LLM, and TTS run in full either way.
    # With it off, the agent's own LiveKit audio output is enabled so you can
    # focus on the voice pipeline end to end. Avatar failures are logged and
    # never block the voice/text fallback.
    avatar_provider = _avatar_provider()
    if avatar_provider == "none":
        job_logger.info(
            "Avatar disabled (AVATAR_ENABLED=%s, AVATAR_PROVIDER=%s); using direct LiveKit audio output",
            os.getenv("AVATAR_ENABLED", "false"), os.getenv("AVATAR_PROVIDER", "spatius"),
        )
    avatar = await start_avatar(avatar_provider, session, ctx.room, job_logger)

    async def publish_user_transcript(event) -> None:
        text = (event.transcript or "").strip()
        if text:
            await publish_room_message(
                {"type": "user_transcript", "text": text, "final": event.is_final}
            )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        asyncio.create_task(publish_user_transcript(event))

    rate_limit_hits = {"count": 0, "hinted": False}

    @session.on("error")
    def on_session_error(event) -> None:
        error = event.error
        status = getattr(error, "status_code", None)
        if status == 429:
            rate_limit_hits["count"] += 1
            # A burst clears by itself; retries fix it silently. A 429 that is
            # still arriving after every retry, from the very first turn, is
            # almost always an exhausted Build-plan allowance (or leftover
            # sessions holding the 5 STT / 5 TTS connections), and no amount of
            # waiting in the SDK will change that. Say so once, with the exact
            # command that reports why, instead of repeating the same line.
            if not rate_limit_hits["hinted"] and rate_limit_hits["count"] >= 4:
                rate_limit_hits["hinted"] = True
                job_logger.error(
                    "LiveKit Inference is still returning 429 after %d rejections (STT and TTS). "
                    "That is not a short burst: either the project used up its Build-plan allowance "
                    "for the month, or old agent sessions are still holding the 5 STT / 5 TTS "
                    "connections. Run `python scripts/check_inference.py` to see the gateway's own "
                    "reason (body + quota headers), and check LiveKit Cloud -> Settings -> Project. "
                    "Last error: %s",
                    rate_limit_hits["count"], error,
                )
            else:
                job_logger.warning(
                    "LiveKit Inference 429 on %s (attempt %d, retrying)",
                    event.source, rate_limit_hits["count"],
                )
            return
        job_logger.error("AgentSession %s error: %s", event.source, error)

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
        # The avatar publishes synchronized speech audio; otherwise the agent
        # publishes its own TTS audio into the room.
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