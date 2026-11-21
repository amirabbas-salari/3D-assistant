"""Persian LiveKit voice agent with a pluggable avatar (D-ID or Spatius) and text fallback."""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

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
    llm,
)
from livekit.plugins import openai

# --- package-aware imports ---
import sys as _sys
def _add_to_path(p: Path):
    s = str(p)
    if s not in _sys.path:
        _sys.path.insert(0, s)

if __package__ in (None, ""):
    # apps/agent/src
    _cand = Path(__file__).resolve().parents[2]
    _add_to_path(_cand)
    # repo root (parents may be <4 when run via ROOT/agent.py shim)
    _parents = Path(__file__).resolve().parents
    _root_candidate = _parents[4] if len(_parents) > 4 else _parents[-1]
    _add_to_path(_root_candidate)
    try:
        from sam.rag.engine import rag_config as _rag_config  # noqa: F401
        from sam.rag.engine import RagIndex as _RagIndex  # noqa: F401
        from sam.rag import engine as rag_module
        from sam.latency.tracker import LatencyTracker
    except ImportError:
        import rag as rag_module  # type: ignore
        from latency import LatencyTracker  # type: ignore
else:
    try:
        from .rag.engine import rag_config as _rag_config  # noqa: F401
        from .rag.engine import RagIndex as _RagIndex  # noqa: F401
        from .rag import engine as rag_module
        from .latency.tracker import LatencyTracker
    except ImportError:
        import rag as rag_module  # type: ignore
        from latency import LatencyTracker  # type: ignore

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

_par = Path(__file__).resolve().parents
PROJECT_ROOT = _par[4] if len(_par) > 4 and _par[3].name == "apps" else _par[3] if len(_par) > 3 and _par[2].name == "apps" else Path(__file__).resolve().parent
# fallback: walk to find repo root via knowledge/ or .env.example
if not (PROJECT_ROOT / ".env.example").exists():
    for _anc in _par:
        if (_anc / ".env.example").exists():
            PROJECT_ROOT = _anc
            break

# Project .env first (works no matter which directory you launch from), then the
# usual upward search as a fallback. load_dotenv never overrides existing values.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "apps/agent/.env")
load_dotenv()

server = agents.AgentServer()
logger = logging.getLogger("sam-voice-agent")
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


def _flag(name: str, default: bool) -> bool:
    """Read a boolean env var, where an empty value means "use the default"."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _llm_request_body(max_tokens: int, job_logger=None) -> dict:
    """Build the Workers AI request body, including the reasoning-depth control.

    gpt-oss reasons before it emits its first token, and every reasoning token
    delays the first word the user hears. Measured on this pipeline, TTFT ranged
    from 1.0 s to 5.4 s for the same short questions — that spread is the
    thinking, not the network. Workers AI accepts the OpenAI-style
    ``reasoning_effort``; "low" keeps short conversational answers fast. The
    plugin only auto-fills this for OpenAI model names, so ``@cf/...`` models
    must set it explicitly or thinking stays at the provider default depth.
    """
    fields: dict = {"max_tokens": max_tokens}
    raw = os.getenv("CLOUDFLARE_LLM_REASONING_EFFORT", "low").strip().lower()
    effort = "" if raw in {"", "default", "unset", "none"} else raw
    if effort in {"low", "medium", "high"}:
        fields["reasoning_effort"] = effort
    elif effort:
        if job_logger is not None:
            job_logger.warning(
                "Unknown CLOUDFLARE_LLM_REASONING_EFFORT=%r; not sent. "
                "Valid values: low, medium, high, default",
                raw,
            )
        effort = ""
    # Some Workers AI endpoints want the nested Responses-API shape instead of
    # the flat field. Off by default: an unknown field can turn a working
    # request into a 400, so this is opt-in for after the flat one proves ignored.
    if effort and os.getenv("CLOUDFLARE_LLM_REASONING_NESTED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        fields["reasoning"] = {"effort": effort}
    if job_logger is not None:
        job_logger.info(
            "LLM speed: reasoning_effort=%s, max_tokens=%s",
            effort or "provider default",
            max_tokens,
        )
    return fields


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


# Latency profiles, applied with AGENT_SPEED_PROFILE. Every value is a knob the
# latency log (latency.py) can show the effect of.
#
# Why each one matters, in the order a turn hits it:
#   endpointing            silent wait after the user stops before the LLM is asked
#   preemptive_generation  start the LLM — and optionally TTS — on the interim
#                          transcript instead of waiting for the turn to be committed
_SPEED_PROFILES: dict[str, dict] = {
    # Preemptive generation has no audible cost: it starts the LLM — and the TTS
    # after it — on the interim transcript while the turn is still being decided.
    # If the transcript changes, the work is thrown away and the confirmed turn
    # runs normally, so the worst case is a few wasted tokens, not a wrong
    # answer. Because the next sentence's audio is then already in hand when the
    # previous one finishes, it also removes the pause between sentences — which
    # is why it is on in every profile, including "balanced".
    #
    # What it cannot fix is a TTS that splits the reply into many requests: the
    # framework's own sentence tokenizer emits per sentence and is not
    # configurable. That is why the instructions also ask for full sentences
    # instead of fragments (see PersianAssistant below); the two together are
    # what actually removes the stutter.
    "balanced": {
        "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 20.0},
    },
    "fast": {
        # 200 ms of silence instead of 300: ~100 ms off every turn. The turn
        # detector can still end the turn earlier when the text is clearly final.
        "endpointing": {"min_delay": 0.2, "max_delay": 2.0},
        "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 20.0},
    },
    "fastest": {
        # Only for headsets or quiet rooms: pause mid-sentence and it will answer.
        "endpointing": {"min_delay": 0.12, "max_delay": 1.5},
        "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 30.0},
    },
}


def _speed_profile(job_logger) -> dict:
    """Turn-handling overrides for the selected latency profile.

    Explicit AGENT_* variables win over the profile, so a single knob can be
    tuned without abandoning the profile.
    """
    profile = os.getenv("AGENT_SPEED_PROFILE", "balanced").strip().lower() or "balanced"
    if profile not in _SPEED_PROFILES:
        job_logger.warning(
            "Unknown AGENT_SPEED_PROFILE=%r; using 'balanced'. Valid: %s",
            profile, ", ".join(_SPEED_PROFILES),
        )
        profile = "balanced"

    turn_handling: dict = json.loads(json.dumps(_SPEED_PROFILES[profile]))  # deep copy

    min_endpointing = os.getenv("AGENT_MIN_ENDPOINTING_DELAY", "").strip()
    max_endpointing = os.getenv("AGENT_MAX_ENDPOINTING_DELAY", "").strip()
    if min_endpointing or max_endpointing:
        endpointing = turn_handling.setdefault("endpointing", {})
        if min_endpointing:
            endpointing["min_delay"] = float(min_endpointing)
        if max_endpointing:
            endpointing["max_delay"] = float(max_endpointing)

    # A reply that gets cut off by a cough or a door and then resumed is heard as
    # a pause in the middle of a thought. The SDK resumes after a false
    # interruption by default, but only after ``false_interruption_timeout``
    # seconds of silence — that wait *is* the pause. Raising the minimum speech
    # length makes short noises less likely to count at all, and shortening the
    # timeout makes a genuine false positive recover faster.
    min_duration = os.getenv("AGENT_INTERRUPTION_MIN_DURATION", "").strip()
    if min_duration:
        try:
            turn_handling.setdefault("interruption", {})["min_duration"] = float(min_duration)
        except ValueError:
            job_logger.warning("AGENT_INTERRUPTION_MIN_DURATION=%r is not a number; ignored", min_duration)
    false_timeout = os.getenv("AGENT_FALSE_INTERRUPTION_TIMEOUT", "").strip()
    if false_timeout:
        try:
            turn_handling.setdefault("interruption", {})["false_interruption_timeout"] = float(false_timeout)
        except ValueError:
            job_logger.warning("AGENT_FALSE_INTERRUPTION_TIMEOUT=%r is not a number; ignored", false_timeout)

    preemptive_tts = os.getenv("AGENT_PREEMPTIVE_TTS", "").strip().lower()
    if preemptive_tts in {"1", "true", "yes", "on"}:
        turn_handling.setdefault("preemptive_generation", {})["preemptive_tts"] = True
    elif preemptive_tts in {"0", "false", "no", "off"}:
        turn_handling.setdefault("preemptive_generation", {})["preemptive_tts"] = False

    job_logger.info(
        "Speed profile=%s → %s", profile, json.dumps(turn_handling, ensure_ascii=False)
    )
    return turn_handling


def _load_knowledge(job_logger):
    """Load the retrieval index once per session, or explain why it is off.

    Returned separately from the tool so a missing index degrades to a plain
    assistant instead of breaking the call to the LLM.
    """
    config = rag_module.rag_config(PROJECT_ROOT)
    if config is None:
        job_logger.info("RAG: off (set RAG_ENABLED=true to add a knowledge tool)")
        return None, None

    try:
        index = rag_module.RagIndex.load(config["store_dir"], collection=config["collection"])
    except ImportError:
        # Only happens with RAG_ENABLED=true and chromadb never installed.
        job_logger.warning(
            "RAG: RAG_ENABLED is true but chromadb is not installed. "
            "Run: pip install chromadb, then: python scripts/build_rag_index.py"
        )
        return None, None
    except FileNotFoundError as exc:
        job_logger.warning("RAG: %s", exc)
        return None, None
    except Exception as exc:  # noqa: BLE001 - never let retrieval setup kill a session
        job_logger.warning("RAG: could not load the index (%s: %s)", type(exc).__name__, exc)
        return None, None

    job_logger.info("%s · %s chunks", rag_module.describe_config(config), len(index))
    return index, config


def _make_knowledge_tool(index, config, job_logger, timings: dict | None = None):
    """Wrap ``index.search`` in a tool the LLM can call.

    ``timings`` is the shared per-turn dict the latency report reads; the SDK
    reports no metric for tool calls, so the only way to see this cost is to
    measure it here.
    """
    top_k = config["top_k"]

    @llm.function_tool(
        name="search_knowledge",
        description=(
            "Search the organization's knowledge base (brand guide, FAQ, internal docs). "
            "Call it when the question is about internal facts that may be in the docs. "
            "If nothing is found, answer from general sales/marketing expertise and ask for details. "
            "Pass the user's question in Persian, as keywords or a short phrase."
        ),
    )
    async def search_knowledge(query: str) -> str:
        started = time.perf_counter()
        hits = index.search(query, top_k=top_k)
        if timings is not None:
            timings["knowledge_lookup"] = (time.perf_counter() - started) * 1000
        if not hits:
            job_logger.info("RAG: no match for %r", query)
            return (
                "چیزی در پایگاه دانش پیدا نشد. صادقانه بگو پیدا نکردی و با دانش عمومی و تجربه‌ی فروش/مارکتینگ ادامه بده؛ "
                "عدد یا نقل‌قول نساز و اگر به جزئیات کسب‌وکار نیاز داری، از کاربر بپرس."
            )
        job_logger.info(
            "RAG: %r → %s",
            query,
            ", ".join(f"{h.chunk.source}/{h.chunk.heading}({h.score:.2f})" for h in hits),
        )
        return (
            "متن‌های مرتبط از پایگاه دانش (فقط بر اساس همین‌ها پاسخ بده):\n\n"
            + rag_module.format_hits(hits)
        )

    return search_knowledge


def _assistant_name() -> str:
    """The name the user hears, kept separate from the dispatch name."""
    return (os.getenv("ASSISTANT_NAME") or "سام").strip()


def _sales_prompt() -> str:
    """The seller/marketer playbook, loaded from knowledge/sales_playbook.md.

    It is a file rather than a string so the sales team can edit the way the
    assistant sells without a code change or a redeploy. It deliberately lives
    in prompts/ and not in knowledge/: behaviour belongs in every prompt, and
    indexing it would let a product question retrieve sales coaching instead of
    a product.
    """
    configured = (os.getenv("SALES_PLAYBOOK") or "prompts/sales_playbook.md").strip()
    path = configured if os.path.isabs(configured) else PROJECT_ROOT / configured
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    # A playbook that has been accidentally emptied must not add an empty line
    # to every prompt.
    return text if len(text) >= 200 else ""


class PersianAssistant(Agent):
    def __init__(self, knowledge_tool=None) -> None:
        fast_start = _flag("AGENT_FAST_START", True)
        name = _assistant_name()
        instructions = (
            f"تو {name}، یک دستیار صوتی فارسی‌زبان با صدای مرد، صمیمی، باهوش و دقیق هستی. "
            f"نام تو {name} است؛ اگر کسی اسمت را پرسید همین را بگو. "
            "هرگاه درباره‌ی جنسیت یا صدای خودت پرسیدند، بگو صدای مرد داری. "
            "همیشه به فارسی روان و طبیعی پاسخ بده، مگر اینکه کاربر صریحاً زبان دیگری بخواهد. "
            "پاسخ‌های معمولی را برای گفتار کوتاه و روشن نگه دار؛ از نشانه‌گذاری و قالب‌بندی پیچیده پرهیز کن. "
            "اگر کاربر متنی را برای روخوانی، تکرار یا بازگویی می‌فرستد، متن را کامل و بدون خلاصه‌کردن یا حذف در پاسخ بیاور تا TTS آن را بخواند. "
            "در این حالت هرگز نگو امکان پخش یا خواندن صدا را نداری. "
            "اگر پاسخ را نمی‌دانی، صادقانه بگو."
        )
        if fast_start:
            # One sentence, not several short ones. The first sentence is kept to
            # 5-9 words so TTS starts immediately (first-sentence boundary), but it
            # must already contain the answer — not a filler like "حتما" / "بذارید چک کنم".
            # Each sentence is its own TTS request; tiny fragments cause audible pauses.
            instructions += (
                " پاسخ را با یک جمله‌ی کامل شروع کن که خودِ جواب (یا کار اصلی) در آن باشد؛ "
                "نه یک کلمه‌ی تأیید و نه جمله‌ی تشریفاتی مثل «حتماً» یا «بذارید چک کنم». "
                "این جمله‌ی اول را حدود پنج تا نه کلمه نگه دار: خیلی کوتاه بماند تا TTS بی‌درنگ شروع شود، "
                "ولی جواب اصلی را همان‌جا بگو؛ جمله‌ی دوم فقط جزئیات باشد. "
                "هرگز با عبارت‌های مقدمه‌چینی مثل «بگذار فکر کنم» یا «سوال خوبی است» شروع نکن."
            )
            instructions += (
                " جمله‌ها را نشکن: هر جمله باید یک فکر کامل باشد و دست‌کم حدود شش تا ده کلمه داشته باشد. "
                "به‌جای چند جمله‌ی خیلی کوتاه و تکه‌تکه، دو یا سه جمله‌ی روان بنویس. "
                "این برای صدا مهم است: جمله‌های ریز، گفتار را بریده‌بریده و پر از مکث می‌کند."
            )
        if knowledge_tool is not None:
            instructions += (
                " اگر پایگاه دانش سازمان فعال است و سؤال به اسناد داخلی مربوط است، "
                "اول ابزار search_knowledge را صدا بزن و بر اساس نتیجه پاسخ بده. "
                "اگر چیزی پیدا نشد، صادقانه بگو و با دانش عمومی ادامه بده — عدد یا نقل‌قول نساز."
            )
        selling = _sales_prompt()
        if selling:
            instructions += (
                "\n\nمهارت‌های فروش و مارکتینگ (در همه‌ی گفتگوها رعایت کن):\n" + selling
            )
        super().__init__(instructions=instructions, tools=[knowledge_tool] if knowledge_tool else [])


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "sam-voice-agent"))
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

    job_logger = logging.getLogger(f"sam-voice-agent.{ctx.job.id}")
    job_logger.setLevel(logging.INFO)
    room_log_handler = RoomLogHandler(
        lambda message: publish_room_message(message, topic="diagnostics")
    )
    job_logger.addHandler(room_log_handler)

    async def detach_room_log_handler() -> None:
        job_logger.removeHandler(room_log_handler)
        room_log_handler.close()

    ctx.add_shutdown_callback(detach_room_log_handler)

    fast_start_enabled = _flag("AGENT_FAST_START", True)
    # Says both names on one line: the dispatch name is what the browser's
    # status panel compares against, and the assistant name is what the user
    # hears, so a mismatch between the two is the usual "wrong name" bug.
    job_logger.info(
        "Assistant: name=%s (dispatch=%s) · answer style fast_start=%s (first sentence kept short so TTS starts sooner)",
        _assistant_name(),
        os.getenv("LIVEKIT_AGENT_NAME", "sam-voice-agent"),
        fast_start_enabled,
    )
    if _sales_prompt():
        job_logger.info(
            "Sales playbook loaded from %s — the assistant sells, it does not just answer",
            os.getenv("SALES_PLAYBOOK", "prompts/sales_playbook.md"),
        )

    latency = LatencyTracker(job_logger)
    if latency.enabled:
        job_logger.info(
            "Latency instrumentation on: per-turn millisecond stages, summary every %s turns "
            "(LATENCY_LOG, LATENCY_REPORT_INTERVAL)",
            latency.report_interval or "∞",
        )

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

    turn_handling = _speed_profile(job_logger)
    # Report what the pipeline actually does, so a slow turn can be traced to the
    # stage that is not streaming. All three are streaming here:
    #   STT: Deepgram nova-3 streams interim transcripts (streaming=True)
    #   LLM: Cloudflare Workers AI via openai.LLM with chat.completions.create(stream=True) —
    #        tokens flow token-by-token through livekit.agents.inference.llm.LLMStream;
    #        TTS starts at first sentence boundary, not after full reply.
    #   TTS: Inference TTS streams natively; GeminiTTS is wrapped by SDK StreamAdapter
    #        (sentence-level) so speech still starts after first sentence.
    job_logger.info(
        "Streaming: STT=%s (streaming=%s) · LLM=Cloudflare Workers AI streaming (openai.LLM stream=True, %s) · TTS=%s (%s) · turn_handling=%s · AGENT_FAST_START=%s (first sentence 5-9 words → TTS starts at sentence boundary)",
        stt_model, getattr(stt.capabilities, "streaming", "?"),
        llm_model,
        tts_model,
        "GeminiTTS via SDK StreamAdapter (sentence-level, TTS starts after first sentence)" if not tts.capabilities.streaming
        else "native streaming (sentence tokenizer → per-sentence TTS requests)",
        json.dumps(turn_handling, ensure_ascii=False) if turn_handling else "SDK defaults",
        fast_start_enabled,
    )

    extra_body = _llm_request_body(llm_max_tokens, job_logger)

    session = AgentSession(
        stt=stt,
        llm=openai.LLM(
            model=llm_model,
            api_key=cloudflare_api_token,
            base_url=cloudflare_base_url,
            # Workers AI otherwise defaults to 256 output tokens for this model.
            extra_body=extra_body,
        ),
        tts=tts,
        conn_options=session_conn_options,
        **({"turn_handling": turn_handling} if turn_handling else {}),
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

    # One metrics event per TTS request. Counting them is the only way to see
    # whether a reply was spoken as one piece or as a dozen round-trips, which
    # is what a listener hears as pausing.
    tts_requests = {"turn": 0}

    @session.on("metrics_collected")
    def on_metrics_collected(event) -> None:
        if getattr(event.metrics, "type", "") == "tts_metrics":
            tts_requests["turn"] += 1

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

    async def publish_latency() -> None:
        await publish_room_message(
            {"type": "latency", **latency.as_dict()}, topic="diagnostics"
        )

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
            # Endpointing and transcription timing live on the user message;
            # hold them until the assistant message closes the same turn.
            latency.note_user_turn(getattr(item, "metrics", None))
        elif role == "assistant":
            text = (getattr(item, "text_content", "") or "").strip()
            job_logger.info("LLM produced assistant text (%d characters)", len(text))
            if tts_requests["turn"]:
                # Reported alongside the tool timing, which is measured the same
                # way (in this process, not by the SDK).
                tool_timings["tts_requests"] = float(tts_requests["turn"])
            latency.record_turn(
                getattr(item, "metrics", None),
                reply_text=text,
                interrupted=bool(getattr(item, "interrupted", False)),
                stt_model=stt_model,
                llm_model=llm_model,
                tts_model=tts_model,
                tool_ms=dict(tool_timings),
            )
            tool_timings.clear()
            tts_requests["turn"] = 0
            # Publish after recording, not when speech starts: the metrics for a
            # turn only exist once its assistant message is complete.
            asyncio.create_task(publish_latency())
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

    # Retrieval is loaded before the session starts so a broken index shows up
    # in the log at startup rather than mid-conversation.
    knowledge_index, knowledge_config = _load_knowledge(job_logger)
    # The tool writes its own duration here; the report reads it. One dict for
    # the session, reset after each recorded turn, so a turn without a lookup
    # is not credited with the previous turn's time.
    tool_timings: dict[str, float] = {}
    knowledge_tool = (
        _make_knowledge_tool(knowledge_index, knowledge_config, job_logger, tool_timings)
        if knowledge_index is not None
        else None
    )

    await session.start(
        agent=PersianAssistant(knowledge_tool=knowledge_tool),
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
