"""Main LiveKit entrypoint — wired from modular config/speech/avatar/rag.

نسخهٔ بازنویسی‌شده با تمرکز روی کمترین تأخیر:
  * RAG: لود در prewarm (قبل از اختصاص job)، جستجو در thread، شروع زودهنگام روی
    final transcript (هم‌زمان با endpointing) و تزریق در on_user_turn_completed (قبل از LLM)
  * ساخت هم‌زمان STT/TTS/LLM/RAG (به‌جای ترتیبی)
  * کلاینت LLM اختصاصی: max_retries=0، connection pool گرم، timeout قابل تنظیم
  * TrackedTTS درست: forward رویدادهای metrics/error، prewarm، aclose، model/provider
  * توکنایزر فارسی مستقل (بدون وابستگی به توکنایزر انگلیسی SDK)
  * برش تاریخچه به‌صورت دسته‌ای و از مسیر درست (agent.update_chat_ctx)
  * greeting ثابت بدون LLM (session.say)
  * throttle انتشار transcriptهای interim
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
import openai as openai_sdk
from livekit import agents, rtc
from livekit.agents import APIConnectOptions, AgentSession, RoomOutputOptions, SessionConnectOptions
from livekit.agents import tts as tts_api
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins import openai as lk_openai

from ..config.env import flag
from ..config.llm import (
    llm_request_body,
    llm_api_key as resolve_llm_api_key,
    llm_max_tokens as resolve_llm_max_tokens,
    llm_extra_headers,
    validate_llm_config,
)
from ..config.speed import speed_profile
from ..speech.providers import stt_provider, tts_provider
from ..speech.stt import build_stt, build_tts
from ..avatar.provider import avatar_provider
from ..avatar.manager import start_avatar
from ..assistant.agent import PersianAssistant
from ..assistant.prompt import assistant_name, sales_prompt
from ..rag.tools import _load_knowledge, _make_knowledge_tool, _rag_preload
from ..utils.logging import RoomLogHandler
from .publish import publish_room_message

try:
    from ..latency.tracker import LatencyTracker
except ImportError:
    from latency import LatencyTracker  # type: ignore

try:  # توکنایزر استریم SDK — اگر در این نسخه نبود، StreamAdapter فارسی غیرفعال می‌شود
    from livekit.agents.tokenize.token_stream import BufferedSentenceStream
    from livekit.agents.tokenize import SentenceTokenizer as _SentenceTokenizerBase
except Exception:  # pragma: no cover
    BufferedSentenceStream = None  # type: ignore
    _SentenceTokenizerBase = object  # type: ignore

logger = logging.getLogger("sam.session.entrypoint")

# Prewarm heavy imports — avoids 1s+ SSL blocks on first use
try:
    import click.types  # noqa: F401
except Exception:
    pass
for _n in ("chromadb", "chromadb.config", "chromadb.telemetry.posthog"):
    try:
        logging.getLogger(_n).setLevel(logging.WARNING)
    except Exception:
        pass


# ───────────────────────────── env / settings ─────────────────────────────

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _env_str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in _TRUE


def _env_not_off(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() not in _FALSE


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """همهٔ env ها یک بار در شروع job خوانده می‌شوند (نه در مسیر داغ هر نوبت)."""
    stt_model: str
    stt_language: str
    stt_fallback: tuple
    tts_model: str
    tts_voice: str
    tts_language: str
    rag_preload: bool
    rag_timeout: float
    max_history: int
    history_slack: int
    interim_publish_s: float
    greeting_mode: str          # "say" (بدون LLM) | "llm"
    greeting_text: str
    room_log_level: int
    llm_read_timeout: float
    inf_retry: int
    inf_interval: float
    inf_timeout: float
    llm_retry: int
    llm_interval: float
    llm_timeout: float
    max_unrecoverable: int

    @classmethod
    def from_env(cls) -> "Settings":
        voice = _env_str("LIVEKIT_TTS_VOICE", "Charon") or "Charon"
        return cls(
            stt_model=_env_str("LIVEKIT_STT_MODEL", "deepgram/nova-3"),
            stt_language=_env_str("LIVEKIT_STT_LANGUAGE", "fa"),
            stt_fallback=tuple(i.strip() for i in os.getenv("LIVEKIT_STT_FALLBACK", "").split(",") if i.strip()),
            tts_model=_env_str("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-lite-tts"),
            tts_voice=voice,
            tts_language=_env_str("LIVEKIT_TTS_LANGUAGE", "fa") or "fa",
            rag_preload=_env_bool("RAG_PRELOAD") or not _env_bool("RAG_TOOL_ENABLED"),
            rag_timeout=_env_float("RAG_PRELOAD_TIMEOUT", 0.8),
            max_history=_env_int("AGENT_MAX_HISTORY_ITEMS", 12),
            history_slack=_env_int("AGENT_HISTORY_TRIM_SLACK", 6),
            interim_publish_s=_env_float("INTERIM_PUBLISH_INTERVAL", 0.15),
            greeting_mode=_env_str("AGENT_GREETING_MODE", "say").lower(),
            greeting_text=_env_str("AGENT_GREETING_TEXT", "سلام! امروز چطور می‌تونم کمکتون کنم؟"),
            room_log_level=getattr(logging, _env_str("ROOM_LOG_LEVEL", "INFO").upper(), logging.INFO),
            llm_read_timeout=_env_float("LLM_READ_TIMEOUT", 8.0),
            inf_retry=_env_int("LIVEKIT_INFERENCE_MAX_RETRY", 3),
            inf_interval=_env_float("LIVEKIT_INFERENCE_RETRY_INTERVAL", 1.0),
            inf_timeout=_env_float("LIVEKIT_INFERENCE_TIMEOUT", 8.0),
            llm_retry=_env_int("LIVEKIT_LLM_MAX_RETRY", 2),
            llm_interval=_env_float("LIVEKIT_LLM_RETRY_INTERVAL", 0.8),
            llm_timeout=_env_float("LIVEKIT_LLM_TIMEOUT", 10.0),
            max_unrecoverable=_env_int("LIVEKIT_MAX_UNRECOVERABLE_ERRORS", 8),
        )


# ───────────────────────────── RAG ─────────────────────────────

def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _consume_task_result(t: "asyncio.Future") -> None:
    # جلوگیری از هشدار "Task exception was never retrieved"
    if not t.cancelled():
        t.exception()


class RagPrefetcher:
    """جستجوی RAG در thread، با شروع زودهنگام روی final transcript.

    زمان بین «final transcript» و «تأیید پایان نوبت» (endpointing) معمولاً صدها میلی‌ثانیه است؛
    جستجو در همین بازه اجرا می‌شود و وقتی hook قبل از LLM صدا زده می‌شود نتیجه آماده است.
    """

    def __init__(self, index: Any, config: Any, log: logging.Logger, timings: dict, *, enabled: bool, timeout: float):
        self._index, self._config, self._log, self._timings = index, config, log, timings
        self.enabled = bool(enabled and index is not None)
        self._timeout = timeout
        self._lock = threading.Lock()          # Chroma/BM25 را هم‌زمان صدا نزن
        self._task: asyncio.Task | None = None
        self._query = ""
        self._acc = ""

    def _search(self, query: str):
        with self._lock:
            return _rag_preload(query, self._index, self._config, self._log, self._timings)

    def _start(self, query: str) -> asyncio.Task:
        task = asyncio.create_task(asyncio.to_thread(self._search, query))
        task.add_done_callback(_consume_task_result)
        self._task, self._query = task, query
        return task

    def reset(self) -> None:
        self._task, self._query, self._acc = None, "", ""

    def on_final_transcript(self, text: str) -> None:
        if not self.enabled:
            return
        self._acc = _norm(f"{self._acc} {text}")
        if self._acc and self._acc != self._query:
            self._start(self._acc)

    async def get(self, text: str) -> str | None:
        if not self.enabled:
            return None
        q = _norm(text)
        if not q:
            return None
        task = self._task if (self._task is not None and self._query == q) else None
        prefetched = task is not None
        if task is None:
            task = self._start(q)
        self.reset()
        t0 = time.perf_counter()
        try:
            res = await asyncio.wait_for(asyncio.shield(task), timeout=self._timeout)
            self._log.info("RAG ready (prefetched=%s, waited=%dms, %d chars)", prefetched,
                           (time.perf_counter() - t0) * 1000, len(res or ""))
            return res or None
        except asyncio.TimeoutError:
            self._log.warning("RAG timeout (%.2fs) — answering without knowledge", self._timeout)
        except Exception as e:
            self._log.warning("RAG preload failed: %s", e)
        return None


# ───────────────────────────── Persian TTS tokenizer ─────────────────────────────

_HARD_END = frozenset(".!?؟…\n")
_SOFT_END = frozenset("،؛:;,")


def _split_persian(text: str, min_hard: int = 4, min_soft: int = 10) -> list[str]:
    """متن را به تکه‌های قابل‌پخش می‌شکند؛ concat تکه‌ها دقیقاً برابر ورودی است.

    * پایان قطعی: . ! ? ؟ … و newline  (حداقل min_hard کاراکتر — کوتاه برای TTFS سریع)
    * پایان نرم: ، ؛ : ; ,           (حداقل min_soft کاراکتر — 10 به جای 24 تا اولین «،» زود بسته شود)
    * علامت فقط وقتی مرز حساب می‌شود که بعدش فاصله بیاید (3.5 و 10:30 نشکند)
    * بهینه برای voice: اولین جمله 5-9 کلمه‌ای باید در 80-120ms بعد از TTFT بسته شود تا TTS فورا شروع کند
    """
    n = len(text)
    tokens: list[str] = []
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        hard = ch in _HARD_END
        if hard or ch in _SOFT_END:
            nxt = text[i + 1] if i + 1 < n else " "
            if ch == "\n" or nxt.isspace():
                j = i + 1
                while j < n and text[j].isspace():
                    j += 1
                if len(text[start:i + 1].strip()) >= (min_hard if hard else min_soft):
                    tokens.append(text[start:j])
                    start = j
                i = j
                continue
        i += 1
    if start < n:
        tokens.append(text[start:])
    return tokens


class FastPersianTokenizer(_SentenceTokenizerBase):  # type: ignore[misc,valid-type]
    def __init__(self, *, min_hard: int = 3, min_soft: int = 8, min_token_len: int = 2, min_ctx_len: int = 2):
        super().__init__()
        self._min_hard, self._min_soft = min_hard, min_soft
        self._min_token_len, self._min_ctx_len = min_token_len, min_ctx_len

    def _fn(self, text: str) -> list[str]:
        return _split_persian(text, self._min_hard, self._min_soft)

    def tokenize(self, text: str, *, language: str | None = None) -> list[str]:  # type: ignore[override]
        return self._fn(text)

    def stream(self, *, language: str | None = None):  # type: ignore[override]
        return BufferedSentenceStream(tokenizer=self._fn, min_token_len=self._min_token_len, min_ctx_len=self._min_ctx_len)


# ───────────────────────────── TTS tracking wrapper ─────────────────────────────

class TrackedTTS(tts_api.TTS):
    """Wrapper برای ثبت سگمنت‌های TTS در گانت.

    نکات مهم نسبت به نسخهٔ قبل: رویدادهای metrics/error داخلی به wrapper forward می‌شوند
    (وگرنه session هرگز خطای TTS و tts_metrics نمی‌بیند)، prewarm/aclose به inner می‌رسد.
    """

    def __init__(self, inner: tts_api.TTS, tracker: Any, log: logging.Logger):
        super().__init__(capabilities=inner.capabilities, sample_rate=inner.sample_rate, num_channels=inner.num_channels)
        self._inner = inner
        self._tracker = tracker
        self._log = log
        inner.on("metrics_collected", self._fwd_metrics)
        inner.on("error", self._fwd_error)

    # ---- forwarding ----
    def _fwd_metrics(self, m: Any) -> None:
        self.emit("metrics_collected", m)

    def _fwd_error(self, e: Any) -> None:
        self.emit("error", e)

    @property
    def label(self) -> str:  # type: ignore[override]
        return getattr(self._inner, "label", super().label)

    @property
    def model(self) -> str:  # type: ignore[override]
        return getattr(self._inner, "model", "unknown")

    @property
    def provider(self) -> str:  # type: ignore[override]
        return getattr(self._inner, "provider", "unknown")

    def prewarm(self) -> None:
        self._inner.prewarm()

    async def aclose(self) -> None:
        try:
            self._inner.off("metrics_collected", self._fwd_metrics)
            self._inner.off("error", self._fwd_error)
        except Exception:
            pass
        await self._inner.aclose()

    def _safe(self, fn: Callable[[str], Any], arg: str) -> None:
        try:
            fn(arg)
        except Exception:
            pass

    # ---- tracked paths ----
    def synthesize(self, text: str, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):  # type: ignore[override]
        self._safe(self._tracker.on_tts_start, text)
        stream = self._inner.synthesize(text, conn_options=conn_options)
        orig_run = getattr(stream, "_run", None)
        if callable(orig_run):
            async def wrapped_run(output_emitter):
                try:
                    return await orig_run(output_emitter)
                finally:
                    self._safe(self._tracker.on_tts_end, text)
            stream._run = wrapped_run  # type: ignore[attr-defined]
        else:
            orig_aclose = getattr(stream, "aclose", None)
            if callable(orig_aclose):
                async def wrapped_close(*a, **kw):
                    try:
                        return await orig_aclose(*a, **kw)
                    finally:
                        self._safe(self._tracker.on_tts_end, text)
                stream.aclose = wrapped_close  # type: ignore[attr-defined]
        return stream

    def stream(self, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):  # type: ignore[override]
        inner_stream = self._inner.stream(conn_options=conn_options)
        orig_push = getattr(inner_stream, "push_text", None)
        orig_flush = getattr(inner_stream, "flush", None)
        orig_end = getattr(inner_stream, "end_input", None)
        if not (callable(orig_push) and callable(orig_flush)):
            return inner_stream

        buf = {"text": "", "started": False}

        def _close_segment() -> None:
            txt = buf["text"].strip()
            if txt and buf["started"]:
                self._safe(self._tracker.on_tts_end, txt)
            buf["text"], buf["started"] = "", False

        def tracked_push(token: str, *a, **kw):
            if token:
                if not buf["started"]:
                    self._safe(self._tracker.on_tts_start, token)
                    buf["started"] = True
                buf["text"] += token
            return orig_push(token, *a, **kw)

        def tracked_flush(*a, **kw):
            _close_segment()
            return orig_flush(*a, **kw)

        def tracked_end(*a, **kw):
            _close_segment()
            return orig_end(*a, **kw) if callable(orig_end) else None

        inner_stream.push_text = tracked_push  # type: ignore[method-assign]
        inner_stream.flush = tracked_flush  # type: ignore[method-assign]
        if callable(orig_end):
            inner_stream.end_input = tracked_end  # type: ignore[method-assign]
        return inner_stream


# ───────────────────────────── helpers ─────────────────────────────

def _label(p: str) -> str:
    return {"openrouter": "OpenRouter", "elevenlabs": "ElevenLabs", "direct": "Direct", "inference": "Inference"}.get(p, p)


def _effective_tts(tts_prov: str, cfg: Settings) -> tuple[str, str]:
    """مدل/صدای مؤثر TTS برای لاگ و متریک."""
    if tts_prov == "openrouter":
        model = _env_str("OPENROUTER_TTS_MODEL") or "elevenlabs/eleven-v3-conversational"  # پیش‌فرض OpenRouterTTS
        voice = (_env_str("OPENROUTER_TTS_VOICE") or _env_str("OPENROUTER_VOICE")
                 or _env_str("ELEVENLABS_VOICE_ID") or cfg.tts_voice) or "george"
        return model, voice
    if tts_prov == "elevenlabs":
        model = _env_str("ELEVENLABS_MODEL") or _env_str("ELEVENLABS_TTS_MODEL") or "eleven_flash_v2_5"
        voice = (_env_str("ELEVENLABS_VOICE_ID") or _env_str("ELEVEN_VOICE_ID") or cfg.tts_voice) or "JBFqnCBsd6RMkjVDRZzb"
        return model, voice
    return cfg.tts_model, cfg.tts_voice


def _handle_exception(handle: Any) -> BaseException | None:
    """SpeechHandle در همهٔ نسخه‌ها exception() ندارد؛ امن بخوان."""
    fn = getattr(handle, "exception", None)
    if not callable(fn):
        return None
    try:
        return fn()
    except (Exception, asyncio.CancelledError):
        return None


async def _trim_history(agent: Any, keep: int, slack: int, log: logging.Logger) -> None:
    """تاریخچه را دسته‌ای کوتاه می‌کند.

    * فقط وقتی طول > keep+slack شد، تا keep کوتاه می‌شود (هر نوبت کوتاه‌کردن = prefix عوض می‌شود
      و prompt-cache ارائه‌دهندهٔ LLM بی‌اثر می‌شود).
    * از مسیر agent.update_chat_ctx اعمال می‌شود؛ تغییر روی agent.chat_ctx (کپی) اثری ندارد.
    * copy → truncate → update بدون await میانی است تا آیتم جدیدی گم نشود.
    """
    try:
        ctx = agent.chat_ctx.copy()
        n = len(ctx.items)
        if n <= keep + slack:
            return
        if hasattr(ctx, "truncate"):
            ctx.truncate(max_items=keep)
        else:
            ctx.items[:] = ctx.items[-keep:]
        await agent.update_chat_ctx(ctx)
        log.info("chat history trimmed %s → %s items", n, len(ctx.items))
    except Exception as e:
        log.warning("history trim failed: %s", e)


# ───────────────────────────── prewarm (قبل از اختصاص job) ─────────────────────────────

def prewarm(proc: agents.JobProcess) -> None:
    """ایندکس دانش (Chroma+BM25) یک بار در prewarm لود می‌شود، نه روی مسیر شروع جلسه."""
    try:
        proc.userdata["knowledge"] = _load_knowledge(logger)
        logger.info("knowledge prewarmed")
    except Exception as e:
        logger.warning("knowledge prewarm failed (%s) — will load in job", e)


# ───────────────────────────── entrypoint ─────────────────────────────

async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()
    cfg = Settings.from_env()

    job_logger = logging.getLogger(f"sam-voice-agent.{ctx.job.id}")
    job_logger.setLevel(logging.INFO)
    room_log_handler = RoomLogHandler(lambda message: publish_room_message(ctx, message, topic="diagnostics"))
    try:
        room_log_handler.setLevel(cfg.room_log_level)
    except Exception:
        pass
    job_logger.addHandler(room_log_handler)

    # تسک‌های پس‌زمینه با reference نگه داشته می‌شوند تا GC وسط کار نابودشان نکند
    bg_tasks: set[asyncio.Task] = set()

    def spawn(coro: Awaitable[Any]) -> asyncio.Task:
        t = asyncio.ensure_future(coro)
        bg_tasks.add(t)
        t.add_done_callback(bg_tasks.discard)
        t.add_done_callback(_consume_task_result)
        return t

    closers: list[Callable[[], Awaitable[None]]] = []

    async def _shutdown() -> None:
        job_logger.removeHandler(room_log_handler)
        room_log_handler.close()
        for t in list(bg_tasks):
            t.cancel()
        for c in closers:
            try:
                await c()
            except Exception:
                pass

    ctx.add_shutdown_callback(_shutdown)

    fast_start_enabled = flag("AGENT_FAST_START", True)
    job_logger.info("Assistant: name=%s (dispatch=%s) · fast_start=%s", assistant_name(),
                    os.getenv("LIVEKIT_AGENT_NAME", "sam-voice-agent"), fast_start_enabled)
    if sales_prompt():
        job_logger.info("Sales playbook loaded — the assistant sells, it does not just answer")

    latency = LatencyTracker(job_logger)
    if latency.enabled:
        job_logger.info("Latency instrumentation on: summary every %s turns", latency.report_interval or "∞")

    # ── LLM config (LiveKit/OpenRouter/Cloudflare) ──
    try:
        llm_prov, llm_model, llm_base_url = validate_llm_config(job_logger)
    except RuntimeError as exc:
        hint = " — برای LiveKit: LLM_PROVIDER=livekit (نیازی به کلید اضافی نیست، فقط LIVEKIT_* کافیست)."
        if "openrouter" in str(exc).lower():
            hint = " — برای OpenRouter: OPENROUTER_API_KEY را از https://openrouter.ai/settings/keys بگیرید و در .env بگذارید."
        raise RuntimeError(str(exc) + hint) from exc
    llm_api_key = resolve_llm_api_key()
    llm_max_tokens = resolve_llm_max_tokens()
    if not 1 <= llm_max_tokens <= 24000:
        raise RuntimeError("LLM_MAX_TOKENS must be between 1 and 24000")
    llm_headers = llm_extra_headers()
    job_logger.info("LLM resolved: provider=%s model=%s max_tokens=%s base=%s", llm_prov, llm_model, llm_max_tokens, llm_base_url)
    extra_body = llm_request_body(llm_max_tokens, job_logger, model=llm_model)

    if any(k in llm_model.lower() for k in ("gpt-oss", "deepseek-r1", "o1", "o3", "qwen3", "qwq", "r1-distill")):
        job_logger.warning("LLM=%s کند است (TTFT 1-5s, reasoning). برای <1s از openai/gpt-4o-mini یا google/gemini-2.0-flash-001 یا meta-llama/llama-3.3-70b-instruct استفاده کنید", llm_model)
    if llm_max_tokens > 200:
        job_logger.info("LLM max_tokens=%s بالا است؛ برای voice کمتر از 150 توصیه می‌شود", llm_max_tokens)

    # ── conn options ──
    inference_conn_options = APIConnectOptions(max_retry=cfg.inf_retry, retry_interval=cfg.inf_interval, timeout=cfg.inf_timeout)
    llm_conn_options = APIConnectOptions(max_retry=cfg.llm_retry, retry_interval=cfg.llm_interval, timeout=cfg.llm_timeout)
    session_conn_options = SessionConnectOptions(
        stt_conn_options=inference_conn_options,
        llm_conn_options=llm_conn_options,
        tts_conn_options=inference_conn_options,
        max_unrecoverable_errors=cfg.max_unrecoverable,
    )

    stt_prov = stt_provider()
    tts_prov = tts_provider()
    eff_tts_model, eff_tts_voice = _effective_tts(tts_prov, cfg)
    tts_model, tts_voice = eff_tts_model, eff_tts_voice

    # ── builders (همه در thread؛ SSL context و import سنگین event loop را بلوکه نمی‌کند) ──
    def _build_stt_sync():
        return build_stt(stt_prov, model=cfg.stt_model, language=cfg.stt_language, conn_options=inference_conn_options,
                         fallback=list(cfg.stt_fallback), job_logger=job_logger)

    def _build_tts_sync():
        return build_tts(tts_prov, model=cfg.tts_model, voice=cfg.tts_voice, language=cfg.tts_language,
                         conn_options=inference_conn_options, job_logger=job_logger)

    def _build_fallback_tts_sync():
        return build_tts("inference", model=cfg.tts_model, voice=cfg.tts_voice, language=cfg.tts_language,
                         conn_options=inference_conn_options, job_logger=job_logger)

    want_tts_fallback = tts_prov == "openrouter" and _env_not_off("OPENROUTER_TTS_FALLBACK", True)

    async def _build_speech():
        async def _fb():
            if not want_tts_fallback:
                return None
            try:
                return await asyncio.to_thread(_build_fallback_tts_sync)
            except Exception as e:
                job_logger.warning("Could not build TTS fallback: %s (continuing without fallback)", e)
                return None
        try:
            stt_, tts_, fb_ = await asyncio.gather(asyncio.to_thread(_build_stt_sync), asyncio.to_thread(_build_tts_sync), _fb())
            job_logger.info("STT/TTS built via threads")
            return stt_, tts_, fb_
        except Exception as e:
            job_logger.warning("STT/TTS thread build failed (%s) — fallback to sync", e)
            return _build_stt_sync(), _build_tts_sync(), None

    def _make_llm_legacy():
        # LiveKit Inference — no API key/base_url needed, goes via LiveKit gateway
        if llm_prov == "livekit":
            from livekit.agents import inference as lk_inference
            job_logger.info("LLM via LiveKit Inference (model=%s, no extra API key)", llm_model)
            # extra_kwargs carries max_tokens; LiveKit gateway forwards it
            extra = dict(extra_body) if extra_body else {}
            # LiveKit inference expects max_tokens via extra_kwargs if provided
            if "max_tokens" not in extra:
                extra["max_tokens"] = llm_max_tokens
            try:
                return lk_inference.LLM(model=llm_model, extra_kwargs=extra if extra else None)
            except TypeError:
                # fallback for older SDK without extra_kwargs
                return lk_inference.LLM(model=llm_model)
        kwargs = dict(model=llm_model, api_key=llm_api_key, base_url=llm_base_url, extra_body=extra_body)
        if llm_headers:
            for hk in ("extra_headers", "default_headers", "headers"):
                try:
                    return lk_openai.LLM(**{**kwargs, hk: llm_headers})
                except TypeError:
                    continue
        return lk_openai.LLM(**kwargs)

    def _make_llm_sync():
        """کلاینت اختصاصی: max_retries=0 (retry را LiveKit مدیریت می‌کند)، pool گرم، timeout مشخص."""
        if llm_prov == "livekit":
            # LiveKit Inference needs no custom httpx client — it uses LiveKit gateway
            return _make_llm_legacy(), None
        try:
            http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=cfg.llm_read_timeout, write=5.0, pool=5.0),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=20, keepalive_expiry=120),
            )
            client = openai_sdk.AsyncClient(api_key=llm_api_key, base_url=llm_base_url, max_retries=0,
                                            http_client=http_client, default_headers=llm_headers or None)
            return lk_openai.LLM(model=llm_model, client=client, extra_body=extra_body), http_client
        except Exception as e:
            job_logger.warning("custom LLM client failed (%s) — legacy construction", e)
            return _make_llm_legacy(), None

    async def _build_llm():
        try:
            return await asyncio.to_thread(_make_llm_sync)
        except Exception as e:
            job_logger.warning("LLM init thread failed (%s) — direct build", e)
            return _make_llm_sync()

    async def _build_rag():
        pre = None
        try:
            pre = ctx.proc.userdata.get("knowledge")
        except Exception:
            pass
        if pre is not None:
            job_logger.info("RAG: using prewarmed index")
            return pre
        try:
            return await asyncio.to_thread(_load_knowledge, job_logger)
        except Exception as e:
            job_logger.error("RAG load failed (%s) — continuing without knowledge", e)
            return None, None

    # همه هم‌زمان: زمان شروع = کندترین بخش، نه مجموع
    (stt, tts, fallback_tts), (_llm, llm_http), (knowledge_index, knowledge_config) = await asyncio.gather(
        _build_speech(), _build_llm(), _build_rag()
    )
    if llm_http is not None:
        closers.append(llm_http.aclose)

        async def _warm_llm_connection() -> None:  # TLS handshake را قبل از اولین نوبت انجام بده
            try:
                await llm_http.head(llm_base_url, timeout=3.0)
            except Exception:
                pass
        spawn(_warm_llm_connection())

    # ── TTS wrapping: streaming → fallback → tracking ──
    native_streaming = bool(getattr(tts.capabilities, "streaming", False))
    # برای فارسی: حتی اگر TTS قبلاً streaming باشد، توکنایزر پیش‌فرض انگلیسی‌محور است و «،» فارسی را مرز نمی‌شناسد → TTFS بالا
    needs_persian = (cfg.tts_language or "").strip().lower().startswith("fa")
    should_wrap = BufferedSentenceStream is not None and (not native_streaming or needs_persian)
    if should_wrap:
        try:
            from livekit.agents.tts import StreamAdapter
            tts = StreamAdapter(tts=tts, sentence_tokenizer=FastPersianTokenizer())  # type: ignore[arg-type]
            job_logger.info("TTS streaming تضمین شد: FastPersianTokenizer (3/8, جمله‌ای + بندی روی ،؛:) native=%s→True", native_streaming)
        except Exception as e:
            job_logger.warning("StreamAdapter فعال‌سازی نشد: %s", e)

    if fallback_tts is not None:
        try:
            from livekit.agents.tts import FallbackAdapter
            # FallbackAdapter به TTS فرزند conn_options خودش را می‌دهد (پیش‌فرض ~۱۰ثانیه timeout)؛
            # برای صدا، فیل‌اور سریع‌تر بهتر از ۱۰ ثانیه سکوت است.
            try:
                tts = FallbackAdapter([tts, fallback_tts],  # type: ignore[arg-type]
                                      attempt_timeout=_env_float("TTS_FALLBACK_ATTEMPT_TIMEOUT", 3.0),
                                      max_retry_per_tts=_env_int("TTS_FALLBACK_MAX_RETRY", 1))
            except TypeError:
                tts = FallbackAdapter([tts, fallback_tts])  # type: ignore[arg-type]
            job_logger.info("OpenRouter TTS fallback enabled: primary=openrouter/%s → fallback=inference/%s", eff_tts_model, cfg.tts_model)
        except Exception as e:
            job_logger.warning("Could not enable TTS fallback: %s (continuing without fallback)", e)

    if latency.enabled:  # wrapper فقط وقتی گانت فعال است (کمتر لایه = کمتر overhead)
        try:
            tts = TrackedTTS(tts, latency, job_logger)
            job_logger.info("TTS tracking enabled: هر تکه صدا یک سگمنت در گانت")
        except Exception as e:
            job_logger.warning("TTS tracking wrap failed: %s", e)

    job_logger.info("Voice pipeline: STT=%s/%s/%s, LLM=%s (max_tokens=%s), TTS=%s/%s voice=%s lang=%s",
                    _label(stt_prov), cfg.stt_model, cfg.stt_language, llm_model, llm_max_tokens,
                    _label(tts_prov), eff_tts_model, eff_tts_voice, cfg.tts_language)

    turn_handling = speed_profile(job_logger)
    if tts_prov == "openrouter":
        streaming_desc = f"OpenRouter {eff_tts_model} (via StreamAdapter, mp3)"
    elif tts_prov == "elevenlabs":
        streaming_desc = f"ElevenLabs {eff_tts_model} (native streaming)"
    else:
        streaming_desc = "native streaming" if native_streaming else "SDK StreamAdapter (sentence-level)"
    job_logger.info("Streaming: STT=%s (streaming=%s) · LLM=%s streaming · TTS=%s (%s) · turn_handling=%s · FAST_START=%s",
                    cfg.stt_model, getattr(stt.capabilities, "streaming", "?"), llm_model, eff_tts_model, streaming_desc,
                    json.dumps(turn_handling, ensure_ascii=False, default=str) if turn_handling else "SDK defaults",
                    fast_start_enabled)

    # turn_detection: برای فارسی threshold پیش‌فرض 0.3568 خیلی محافظه‌کار است → جملات کوتاه مثل "سلام" با 0.07 رد می‌شوند و max_delay می‌خورند
    # کاهش threshold به 0.2 باعث می‌شود حتی با 0.3 هم زودتر پایان تشخیص داده شود (بدون دست زدن به min/max)
    # این تنظیم در کنار max_delay کمتر، میانگین 940ms را به ~300ms می‌رساند
    turn_detection_kwargs = {}
    # اگر کاربر override نکرده، برای فارسی/عمومی threshold پایین‌تر بگذار
    _td_thresh = os.getenv("LIVEKIT_TURN_DETECTOR_THRESHOLD", "").strip()
    if _td_thresh:
        try:
            turn_detection_kwargs["unlikely_threshold"] = float(_td_thresh)
        except ValueError:
            pass
    else:
        # پیش‌فرض بهینه برای فارسی: 0.2 به جای 0.3568 — در لاگ دیدیم "سلام" با 0.07 هنوز کم است ولی "میخام سایت طراحی کنم" با 0.63 قبول شد
        # با 0.2 حداقل جملات متوسط سریع‌تر رد می‌شوند؛ جملات خیلی کوتاه اگر باز هم کم بود، max_delay کوتاه (0.6) نجات می‌دهد
        turn_detection_kwargs["unlikely_threshold"] = 0.2

    session_kwargs = {
        "stt": stt,
        "llm": _llm,
        "tts": tts,
        "conn_options": session_conn_options,
    }
    if turn_handling:
        session_kwargs["turn_handling"] = turn_handling
    # turn_detection را فقط اگر SDK پشتیبانی کند اضافه کن (سازگاری با نسخه‌های قدیمی)
    if turn_detection_kwargs:
        try:
            # تست سازگاری: آیا AgentSession turn_detection می‌پذیرد؟
            import inspect as _inspect
            if "turn_detection" in _inspect.signature(AgentSession.__init__).parameters:
                session_kwargs["turn_detection"] = turn_detection_kwargs
                job_logger.info("Turn detection tuned: %s", turn_detection_kwargs)
        except Exception:
            pass

    session = AgentSession(**session_kwargs)

    # Prewarm TTS (wrapperها prewarm را به inner می‌رسانند؛ در نسخهٔ قبل هرگز به inner نمی‌رسید)
    try:
        tts.prewarm()
        job_logger.info("TTS prewarm فراخوانی شد (%s)", type(tts).__name__)
    except Exception as e:
        job_logger.warning("TTS prewarm شکست: %s", e)

    av_provider = avatar_provider()
    if av_provider == "none":
        job_logger.info("Avatar disabled (AVATAR_ENABLED=%s, AVATAR_PROVIDER=%s); using direct audio",
                        os.getenv("AVATAR_ENABLED", "false"), os.getenv("AVATAR_PROVIDER", "spatius"))
    avatar = await start_avatar(av_provider, session, ctx.room, job_logger)

    # ── RAG objects ──
    tool_timings: dict[str, float] = {}
    knowledge_tool = _make_knowledge_tool(knowledge_index, knowledge_config, job_logger, tool_timings) if knowledge_index is not None else None
    rag = RagPrefetcher(knowledge_index, knowledge_config, job_logger, tool_timings, enabled=cfg.rag_preload, timeout=cfg.rag_timeout)
    assistant = PersianAssistant(knowledge_tool=knowledge_tool, latency_tracker=latency, rag=rag)

    # ── publishers ──
    async def publish_latency_msg() -> None:
        await publish_room_message(ctx, {"type": "latency", **latency.as_dict()}, topic="diagnostics")

    async def publish_assistant_reply_msg(text: str) -> None:
        await publish_room_message(ctx, {"type": "assistant_reply", "text": text})

    last_pub = {"t": 0.0, "text": ""}

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        text = (getattr(event, "transcript", "") or "").strip()
        if not text:
            return
        is_final = bool(getattr(event, "is_final", False))
        now = time.monotonic()
        # interim ها throttle می‌شوند؛ final همیشه منتشر می‌شود
        if is_final or (text != last_pub["text"] and now - last_pub["t"] >= cfg.interim_publish_s):
            last_pub["t"], last_pub["text"] = now, text
            spawn(publish_room_message(ctx, {"type": "user_transcript", "text": text, "final": is_final}))
        if is_final:
            rag.on_final_transcript(text)   # جستجوی RAG هم‌زمان با endpointing شروع شود
        try:
            if latency._turn_start_ts is None or (latency._stt_last_ts is None and not latency._stt_tokens):
                try:
                    latency.mark_turn_start()
                except Exception:
                    pass
            latency.on_stt_token(text, is_final=is_final)
        except Exception:
            pass

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
        body_str = str(getattr(error, "body", "") or str(error))
        if status == 400 and "array not in string" in body_str:
            job_logger.error("LLM 400: Cloudflare gpt-oss-120b ابزار را نمی‌پذیرد (array not in string). فیکس: .env → RAG_PRELOAD=true و RAG_TOOL_ENABLED=false و ری‌استارت.")
            return
        if status == 429:
            rate_limit_hits["count"] += 1
            if not rate_limit_hits["hinted"] and rate_limit_hits["count"] >= 4:
                rate_limit_hits["hinted"] = True
                job_logger.error("LiveKit Inference still 429 after %d rejections. Run python scripts/check_inference.py", rate_limit_hits["count"])
            else:
                job_logger.warning("LiveKit Inference 429 on %s (attempt %d, retrying)", event.source, rate_limit_hits["count"])
            return
        if status == 402:
            if tts_prov == "openrouter":
                job_logger.error("OpenRouter TTS 402: %s — credits exhausted. Add credits at https://openrouter.ai/settings/credits or set TTS_PROVIDER=inference (OPENROUTER_TTS_FALLBACK=true = auto fallback)", error)
            else:
                job_logger.error("TTS 402: %s — credits exhausted. Set TTS_PROVIDER=inference to fallback.", error)
            return
        if status in (401, 402, 403, 429, 500, 502, 503):
            job_logger.error("LLM %s error %s: %s — کلید OPENROUTER_API_KEY و اعتبار و مدل (%s) را چک کنید", event.source, status, body_str[:600], llm_model)
            return
        job_logger.error("AgentSession %s error: %s (body=%s)", event.source, error, body_str[:800])

    trim_state = {"running": False}

    def maybe_trim_history() -> None:
        if cfg.max_history <= 0 or trim_state["running"]:
            return
        trim_state["running"] = True

        async def _run() -> None:
            try:
                await _trim_history(assistant, cfg.max_history, cfg.history_slack, job_logger)
            finally:
                trim_state["running"] = False
        spawn(_run())

    @session.on("conversation_item_added")
    def on_conversation_item_added(event) -> None:
        item = event.item
        role = getattr(item, "role", None)
        if role == "user":
            text = (getattr(item, "text_content", "") or "").strip()
            if text:
                job_logger.info("User turn committed (%d chars)", len(text))
            # اگر interim قبلاً جمع شده، turn_start را ریست نکن
            if latency._turn_start_ts is None:
                try:
                    latency.mark_turn_start()
                except Exception:
                    pass
            latency.note_user_turn(getattr(item, "metrics", None))
        elif role == "assistant":
            text = (getattr(item, "text_content", "") or "").strip()
            job_logger.info("LLM produced assistant text (%d chars)", len(text))
            if tts_requests["turn"]:
                tool_timings["tts_requests"] = float(tts_requests["turn"])
            try:
                latency.record_turn(getattr(item, "metrics", None), reply_text=text,
                                    interrupted=bool(getattr(item, "interrupted", False)),
                                    stt_model=cfg.stt_model, llm_model=llm_model, tts_model=tts_model,
                                    tool_ms=dict(tool_timings))
            except Exception:
                job_logger.exception("latency.record_turn failed")
            tool_timings.clear()
            tts_requests["turn"] = 0
            maybe_trim_history()
            spawn(publish_latency_msg())
            if text:
                spawn(publish_assistant_reply_msg(text))

    @session.on("agent_state_changed")
    def on_agent_state_changed(event) -> None:
        job_logger.info("Assistant state: %s -> %s", event.old_state, event.new_state)

    # ── text chat ──
    async def respond_to_text(text: str, sender: str) -> None:
        job_logger.info("Text chat input from %s (%d chars)", sender, len(text))
        try:
            latency.mark_turn_start()
        except Exception:
            pass
        try:
            session.interrupt()
            kwargs: dict[str, Any] = {"user_input": text}
            handle = session.generate_reply(**kwargs)
            await handle
            exc = _handle_exception(handle)
            if exc:
                body = str(getattr(exc, "body", "") or str(exc))
                if "array not in string" in body:
                    job_logger.warning("Text reply با ابزار شکست خورد — یک بار بدون ابزار تلاش می‌کنم")
                    try:
                        retry = session.generate_reply(user_input=text, tool_choice="none")
                    except TypeError:
                        retry = session.generate_reply(user_input=text)
                    await retry
                    r_exc = _handle_exception(retry)
                    if r_exc:
                        job_logger.error("Text chat retry هم شکست: %s", r_exc)
                    return
                job_logger.error("Text chat reply failed: %s", exc)
        except Exception:
            job_logger.exception("Could not generate reply to text chat")

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
            spawn(respond_to_text(text, sender))
        except Exception:
            job_logger.exception("Invalid text chat data packet")

    ctx.room.on("data_received", on_room_data_received)

    await session.start(agent=assistant, room=ctx.room,
                        room_output_options=RoomOutputOptions(audio_enabled=avatar is None))
    job_logger.info("Agent session started and ready for voice or text input")

    # ── greeting ──
    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    opening_line = str(metadata.get("opening_line", "")).strip()[:300]

    if opening_line:
        # متن متغیر → به LLM نیاز دارد
        greeting_handle = session.generate_reply(user_input=opening_line,
                                                 instructions="به فارسی گرم و کوتاه سلام کن و به خواسته کاربر پاسخ بده.")
    elif cfg.greeting_mode == "llm":
        greeting_handle = session.generate_reply(user_input="سلام",
                                                 instructions="به فارسی گرم و کوتاه سلام کن و بپرس امروز چطور می‌توانی کمک کنی.")
    else:
        # greeting ثابت: بدون رفت‌وبرگشت LLM، فقط TTS
        greeting_handle = session.say(cfg.greeting_text, allow_interruptions=True)

    def _log_greeting_error(handle: Any) -> None:
        exc = _handle_exception(handle)
        if exc:
            job_logger.error("Greeting failed (%s): %s — مدل را به gpt-4o-mini عوض کنید", type(exc).__name__, exc)

    try:
        greeting_handle.add_done_callback(_log_greeting_error)
    except Exception:
        pass


# export server — SDK expects entrypoint_fnc (LiveKit Agents >=1.0)
_agent_name = os.getenv("LIVEKIT_AGENT_NAME", "sam-voice-agent")
try:
    # initialize_process_timeout پیش‌فرض ۱۰ ثانیه است؛ لود Chroma/BM25 در prewarm (مخصوصاً روی Windows)
    # می‌تواند از آن بیشتر شود و process کشته شود.
    server = agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        agent_name=_agent_name,
        initialize_process_timeout=_env_float("LIVEKIT_INIT_PROCESS_TIMEOUT", 60.0),
    )
except TypeError:
    try:
        server = agents.WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=_agent_name)
    except TypeError:
        # fallback for very old SDK that used `entrypoint`
        server = agents.WorkerOptions(entrypoint=entrypoint, agent_name=_agent_name)  # type: ignore[arg-type]