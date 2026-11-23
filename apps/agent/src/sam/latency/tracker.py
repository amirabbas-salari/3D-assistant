"""Millisecond turn-latency instrumentation for the voice pipeline.

The agent already knows how long every stage took, but it only puts those numbers
on ``ChatMessage.metrics`` — invisible unless you attach a debugger. This module
turns each turn into one structured log line, plus a rolling summary that names
the worst stage, so a bottleneck is obvious from the terminal or the browser
diagnostics panel instead of being guessed at.

The numbers come from the SDK, not from timestamps we invent:

* ``e2e_latency`` — user stopped speaking → agent audio started (also exposed as response_delay).
* ``response_delay`` — پایان سوال کاربر ← شروع پاسخ دستیار (highlighted; equals e2e when available, else sum of stages)
* ``transcription_delay`` — end of speech → final transcript.
* ``end_of_turn_delay`` — end of speech → the decision that the turn is over
  (this is the endpointing wait, and the usual hidden cost).
* ``llm_node_ttft`` — prompt sent → first LLM token.
* ``llm_node_ttfs`` — prompt sent → first sentence handed to TTS.
* ``tts_node_ttfb`` — first sentence → first audio byte.
* ``playback_latency`` — first audio frame → the output reports play started.

``e2e_latency`` is not the sum of the others: STT runs concurrently with
endpointing, and playback overlaps generation. That is why each turn logs both
the individual stages and where the wall-clock time actually went.

Enable with ``LATENCY_LOG=true`` (millisecond log lines) and
``LATENCY_REPORT_INTERVAL=n`` (a summary every ``n`` turns, ``0`` disables).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

# Stage order matters: it is the order a turn happens in, and the order a
# bottleneck list is easiest to read in.
# response_delay is the user-requested highlight: wall time from end-of-question to start-of-answer.
STAGES: tuple[tuple[str, str], ...] = (
    ("response_delay", "پایان سوال کاربر ← شروع پاسخ دستیار"),
    ("end_of_turn_delay", "پایان گفتار ← تشخیص پایان نوبت"),
    ("transcription_delay", "پایان گفتار ← متن نهایی STT"),
    ("llm_node_ttft", "درخواست LLM ← اولین توکن"),
    ("llm_node_ttfs", "درخواست LLM ← اولین جمله به TTS"),
    # Report-only: the SDK does not emit a tool metric, so this is measured
    # around our own search call. Appears only on turns that used the tool.
    ("knowledge_lookup", "فراخوانی ابزار پایگاه دانش"),
    ("tts_node_ttfb", "اولین جمله ← اولین بایت صدا"),
    ("playback_latency", "اولین فریم ← شروع پخش"),
    # Not a duration: how many TTS requests this turn needed. Every request is a
    # round-trip, and the wait for the next one is heard as a pause between
    # sentences. A low count with a short first sentence is the goal.
    ("tts_requests", "تعداد درخواست TTS در این نوبت"),
)

STAGE_LABELS = dict(STAGES)

# What actually moves each stage. A bottleneck line that names a setting is
# actionable; one that only names a duration is trivia.
STAGE_ADVICE: dict[str, str] = {
    "response_delay":
        "از پایان سوال تا شروع جواب → همین عدد گلوگاه اصلی تجربه‌ی کاربر است؛ مجموع endpointing + LLM + TTS است. اگر بالاست، اول پروفایل سرعت و سپس مدل LLM را چک کنید",
    "end_of_turn_delay":
        "انتظار سکوت است، نه مدل → AGENT_SPEED_PROFILE=fast (یا AGENT_MIN_ENDPOINTING_DELAY)",
    "transcription_delay":
        "نهایی‌شدن متن STT → مدل/زبان STT یا SPEECH_PROVIDER=direct را بررسی کنید",
    "llm_node_ttft":
        "زمان اولین توکن مدل است، نه میکروفون → gpt-oss-120b پیش از پاسخ «فکر» می‌کند (reasoning); "
        "TTFT اندازه‌گیری‌شده 1.0-5.4s برای سؤال‌های کوتاه؛ CLOUDFLARE_LLM_REASONING_EFFORT=low (پیش‌فرض) "
        "و با scripts/check_llm_speed.py اندازه بگیرید — اگر بی‌اثر بود، مدل را به llama-3.3-70b-fp8-fast تغییر دهید (TTFT ~150ms) ",
    "llm_node_ttfs":
        "مدل دیر جمله را می‌بندد → جمله‌ی اول کوتاه (AGENT_FAST_START=true, 5-9 کلمه)؛ LLM به‌صورت streaming token-by-token می‌آید و TTS در مرز جمله‌ی اول شروع می‌شود",
    "knowledge_lookup":
        "جست‌وجوی پایگاه دانش کند است → ایندکس بزرگ یا محل ذخیره‌سازی کند؛ "
        "RAG_TOP_K را کم کنید (BM25 خودش میلی‌ثانیه‌ای است)",
    "tts_node_ttfb":
        "زمان اولین بایت صدا → مسیر TTS؛ با GeminiTTS واسط جمله‌ای SDK دخیل است",
    "playback_latency":
        "تحویل صدا به خروجی → با آواتار روشن معمولاً همان مسیر آواتار است",
    "tts_requests":
        "هر درخواست TTS یک رفت‌وبرگشت است و بین دو درخواست، وقفه شنیده می‌شود → "
        "پاسخ تکه‌تکه است؛ جمله‌های کامل‌تر (AGENT_FAST_START) و preemptive TTS آن را کم می‌کند",
}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def fmt_ms(value: float | None) -> str:
    """Format a duration already expressed in milliseconds."""
    if value is None:
        return "—"
    if value >= 1000:
        return f"{value / 1000:.2f}s"
    if value >= 100:
        return f"{value:.0f}ms"
    if value >= 1:
        return f"{value:.1f}ms"
    # A local BM25 lookup lands here; "0.0ms" would look like a broken timer.
    return f"{value:.2f}ms"


def stage_ms(metrics: dict, key: str) -> float | None:
    """Read one stage out of a ``MetricsReport`` (which stores seconds) as ms."""
    value = metrics.get(key)
    if value is None:
        return None
    try:
        return float(value) * 1000.0
    except (TypeError, ValueError):
        return None


def bottlenecks(metrics: dict, *, limit: int = 3) -> list[tuple[str, float]]:
    """The slowest stages of one turn, slowest first."""
    found: list[tuple[str, float]] = []
    for key, _label in STAGES:
        value = stage_ms(metrics, key)
        if value is not None and value > 0:
            found.append((key, value))
    found.sort(key=lambda item: item[1], reverse=True)
    return found[:limit]


def parse_metrics(metrics: dict | None) -> dict[str, float | None]:
    """All known stages of a turn in milliseconds, ``None`` when unreported."""
    metrics = metrics or {}
    return {key: stage_ms(metrics, key) for key, _label in STAGES}


@dataclass
class TurnSample:
    """One finished turn, flattened for logging and averaging."""

    index: int
    at: float
    stages: dict[str, float | None]
    e2e_ms: float | None
    reply_chars: int = 0
    interrupted: bool = False
    extra: dict[str, object] = field(default_factory=dict)
    tokens: list[dict] = field(default_factory=list)  # LLM per-token timeline: [{idx,text,start,end,dur}]
    tts_tokens: list[dict] = field(default_factory=list)  # TTS per-chunk timeline: [{idx,text,start,end,dur}]


class LatencyTracker:
    """Turns the SDK's per-turn metrics into millisecond logs and a summary.

    One instance per job. Every method is safe to call when logging is disabled:
    the tracker still counts, so ``summary()`` works even in quiet mode.
    """

    def __init__(self, job_logger: logging.Logger, *, enabled: bool | None = None) -> None:
        self._log = job_logger
        self.enabled = _env_flag("LATENCY_LOG", True) if enabled is None else enabled
        self.report_interval = _env_int("LATENCY_REPORT_INTERVAL", 5)
        self._samples: list[TurnSample] = []
        self._turn = 0
        self._pending_user: dict[str, float | None] | None = None
        # Per-token tracking (مرحله‌ای) — LLM و TTS هر دو در یک ردیف با سگمنت‌های مرحله‌ای
        self._llm_start_ts: float | None = None
        self._llm_last_ts: float | None = None
        self._llm_tokens: list[dict] = []
        self._tts_tokens: list[dict] = []
        self._tts_pending: dict | None = None  # {text, start_ms, start_ts}
        self._turn_start_ts: float | None = None

    # ---- Token-level tracking (برای گانت مرحله‌ای) ----
    def on_llm_start(self) -> None:
        self._llm_start_ts = time.time()
        self._llm_last_ts = self._llm_start_ts
        self._llm_tokens = []
        if self._turn_start_ts is None:
            self._turn_start_ts = self._llm_start_ts

    def on_llm_token(self, text: str) -> None:
        if not text:
            return
        now = time.time()
        if self._llm_start_ts is None:
            self.on_llm_start()
            self._llm_start_ts = now
            self._llm_last_ts = now
        assert self._llm_start_ts is not None and self._llm_last_ts is not None
        start_ms = (self._llm_last_ts - self._llm_start_ts) * 1000.0
        end_ms = (now - self._llm_start_ts) * 1000.0
        dur_ms = end_ms - start_ms
        safe_text = text[:40].replace("\n", " ")
        self._llm_tokens.append({
            "idx": len(self._llm_tokens) + 1,
            "text": safe_text,
            "start": round(start_ms, 1),
            "end": round(end_ms, 1),
            "dur": round(max(0, dur_ms), 1),
        })
        self._llm_last_ts = now

    def on_llm_end(self) -> None:
        pass

    def on_tts_start(self, text: str) -> None:
        now = time.time()
        if self._llm_start_ts is None:
            # اگر LLM هنوز شروع نشده (مثلاً متن مستقیم)، Turn را به عنوان مرجع بگیر
            self._turn_start_ts = self._turn_start_ts or now
            base = self._turn_start_ts
        else:
            base = self._llm_start_ts
        start_ms = (now - base) * 1000.0
        self._tts_pending = {"text": text[:60].replace("\n", " "), "start": round(start_ms, 1), "start_ts": now, "base": base}

    def on_tts_end(self, text: str | None = None) -> None:
        if not self._tts_pending:
            return
        now = time.time()
        base = self._tts_pending.get("base")
        if base is None:
            base = self._llm_start_ts or self._turn_start_ts or now
        start_ms = self._tts_pending["start"]
        end_ms = (now - base) * 1000.0
        dur_ms = end_ms - start_ms
        safe_text = (text or self._tts_pending.get("text") or "")[:50].replace("\n", " ")
        self._tts_tokens.append({
            "idx": len(self._tts_tokens) + 1,
            "text": safe_text,
            "start": round(start_ms, 1),
            "end": round(end_ms, 1),
            "dur": round(max(0, dur_ms), 1),
        })
        self._tts_pending = None

    def on_turn_start(self) -> None:
        self._turn_start_ts = time.time()

    @property
    def turns(self) -> int:
        return self._turn

    def note_user_turn(self, metrics: dict | None) -> None:
        """Keep the user half of a turn until its reply arrives.

        The SDK reports ``transcription_delay`` and ``end_of_turn_delay`` on the
        *user* message but ``e2e_latency`` and the LLM/TTS stages on the
        *assistant* message, so a single complete picture needs both.
        """
        self._pending_user = parse_metrics(metrics)

    def record_turn(
        self,
        metrics: dict | None,
        *,
        reply_text: str = "",
        interrupted: bool = False,
        stt_model: str | None = None,
        llm_model: str | None = None,
        tts_model: str | None = None,
        tool_ms: dict[str, float] | None = None,
    ) -> TurnSample | None:
        """Log one assistant turn and return its sample.

        ``tool_ms`` carries timings we measure ourselves (the SDK emits no
        metric for tool calls), keyed by stage name.
        """
        self._turn += 1
        assistant_stages = parse_metrics(metrics)
        # Merge the user half (endpointing, transcription) with the assistant
        # half (LLM, TTS, playback); whichever is missing stays None.
        stages = dict(self._pending_user or {})
        stages.update({k: v for k, v in assistant_stages.items() if v is not None})
        for key, value in (tool_ms or {}).items():
            if value is not None:
                stages[key] = value
        for key in assistant_stages:
            stages.setdefault(key, None)
        self._pending_user = None
        e2e = stage_ms(metrics or {}, "e2e_latency")
        # response_delay: user-requested highlight — from end of question to start of answer
        # Prefer SDK's e2e_latency; fallback to sum of serial stages if e2e missing (e.g. text chat)
        response_delay = e2e
        if response_delay is None:
            serial = [stages.get("end_of_turn_delay"), stages.get("llm_node_ttft"), stages.get("tts_node_ttfb"), stages.get("playback_latency")]
            vals = [v for v in serial if v is not None]
            response_delay = sum(vals) if vals else None
        if response_delay is not None:
            stages["response_delay"] = response_delay
        # attach per-token timelines (LLM و TTS)
        tokens_snapshot = list(self._llm_tokens) if self._llm_tokens else []
        tts_snapshot = list(self._tts_tokens) if self._tts_tokens else []
        # بافرها را برای نوبت بعد خالی کن
        self._llm_tokens = []
        self._tts_tokens = []
        self._llm_start_ts = None
        self._llm_last_ts = None
        self._tts_pending = None
        # _turn_start_ts را نگه می‌داریم تا TTS بعدی هم مرجع داشته باشد، در record_turn ریست نمی‌کنیم

        sample = TurnSample(
            index=self._turn,
            at=time.time(),
            stages=stages,
            e2e_ms=e2e,
            reply_chars=len(reply_text or ""),
            interrupted=interrupted,
            extra={
                "stt": stt_model,
                "llm": llm_model,
                "tts": tts_model,
            },
            tokens=tokens_snapshot,
            tts_tokens=tts_snapshot,
        )
        self._samples.append(sample)

        if self.enabled:
            self._log_turn(sample)
            if tokens_snapshot:
                total_tok_ms = tokens_snapshot[-1]["end"] if tokens_snapshot else 0
                avg_tok = total_tok_ms / len(tokens_snapshot) if tokens_snapshot else 0
                self._log.info("⏱ نوبت #%d LLM توکن‌ها: %d توکن در %s (میانگین هر توکن %s)", sample.index, len(tokens_snapshot), fmt_ms(total_tok_ms), fmt_ms(avg_tok))
            if tts_snapshot:
                total_tts_ms = tts_snapshot[-1]["end"] if tts_snapshot else 0
                self._log.info("⏱ نوبت #%d TTS تکه‌ها: %d تکه در %s", sample.index, len(tts_snapshot), fmt_ms(total_tts_ms))
        if self.report_interval and self._turn % self.report_interval == 0:
            self.summary(prefix="میانگین")
        return sample

    def _log_turn(self, sample: TurnSample) -> None:
        stages = sample.stages
        # New highlighted log: time from end of user question to start of assistant answer
        if stages.get("response_delay") is not None:
            self._log.info(
                "⏱ نوبت #%d پاسخ‌دهی %s ← از پایان سوال کاربر تا شروع پاسخ دستیار (e2e: %s)",
                sample.index,
                fmt_ms(stages.get("response_delay")),
                fmt_ms(sample.e2e_ms),
            )
        self._log.info(
            "⏱ نوبت #%d | سراسری %s | تشخیص پایان %s · متن %s · LLM %s · TTS %s · پخش %s"
            " | %d نویسه%s",
            sample.index,
            fmt_ms(sample.e2e_ms),
            fmt_ms(stages.get("end_of_turn_delay")),
            fmt_ms(stages.get("transcription_delay")),
            fmt_ms(stages.get("llm_node_ttft")),
            fmt_ms(stages.get("tts_node_ttfb")),
            fmt_ms(stages.get("playback_latency")),
            sample.reply_chars,
            " · قطع‌شده" if sample.interrupted else "",
        )

        slow = bottlenecks({key: (value or 0) / 1000.0 for key, value in stages.items()})
        if slow:
            self._log.info(
                "⏱ نوبت #%d کندترین مراحل: %s",
                sample.index,
                " · ".join(f"{STAGE_LABELS.get(k, k)} {fmt_ms(v)}" for k, v in slow),
            )

        # e2e versus the three serial provider calls: the remainder is the part
        # spent inside the pipeline itself (scheduling, avatar handoff,
        # transport). Naming it explicitly separates "our provider is slow" from
        # "our own plumbing is slow", which no API key can fix.
        if sample.e2e_ms is not None:
            accounted = sum(
                value for value in (
                    stages.get("end_of_turn_delay"),
                    stages.get("llm_node_ttft"),
                    stages.get("tts_node_ttfb"),
                ) if value
            )
            self._log.info(
                "⏱ نوبت #%d سهم‌ها: پایان‌نوبت+LLM+TTS = %s از %s سراسری → %s جای دیگر",
                sample.index, fmt_ms(accounted), fmt_ms(sample.e2e_ms),
                fmt_ms(sample.e2e_ms - accounted),
            )

    def averages(self) -> dict[str, float]:
        """Mean milliseconds per stage across every recorded turn."""
        result: dict[str, float] = {}
        for key, _label in STAGES:
            values = [s.stages[key] for s in self._samples if s.stages.get(key)]
            if values:
                result[key] = sum(values) / len(values)
        return result

    def summary(self, *, prefix: str = "خلاصه‌ی تأخیر") -> str:
        """Log (and return) the rolling average, naming the worst stage."""
        if not self._samples:
            text = f"{prefix}: هنوز نوبتی ثبت نشده است."
            if self.enabled:
                self._log.info(text)
            return text

        averages = self.averages()
        if not averages and not any(s.e2e_ms for s in self._samples):
            text = (
                f"{prefix} ({len(self._samples)} نوبت): هیچ زمانی از SDK گزارش نشد؛ "
                "شاید نوبتی کامل نشده یا مدل‌ها metrics برنگردانده‌اند."
            )
            if self.enabled:
                self._log.info(text)
            return text

        lines = [f"{prefix} ({len(self._samples)} نوبت):"]
        for key, label in STAGES:
            values = [s.stages[key] for s in self._samples if s.stages.get(key)]
            if not values:
                continue
            lines.append(
                f"  • {label}: میانگین {fmt_ms(sum(values) / len(values))} · بدترین {fmt_ms(max(values))}"
            )
        e2e = [s.e2e_ms for s in self._samples if s.e2e_ms]
        if e2e:
            ordered = sorted(e2e)
            p50 = ordered[len(ordered) // 2]
            p95 = ordered[min(len(ordered) - 1, int(round(len(ordered) * 0.95)))]
            lines.append(
                f"  • سراسری (e2e): میانگین {fmt_ms(sum(e2e) / len(e2e))} · "
                f"میانه {fmt_ms(p50)} · p95 {fmt_ms(p95)}"
            )
        if averages:
            worst_key = max(averages, key=lambda k: averages[k])
            lines.append(
                f"  → گلوگاه: {STAGE_LABELS.get(worst_key, worst_key)} "
                f"({fmt_ms(averages[worst_key])} میانگین)"
            )
            advice_key = worst_key
            # When the first sentence follows the first token almost immediately,
            # nothing is waiting on sentence closing — the wait is the model's
            # own start-up (reasoning before the first token). Telling the user
            # to "answer in shorter sentences" would point at the wrong knob.
            ttft = averages.get("llm_node_ttft")
            ttfs = averages.get("llm_node_ttfs")
            if worst_key == "llm_node_ttfs" and ttft and ttfs and ttfs - ttft < 400:
                advice_key = "llm_node_ttft"
                lines.append(
                    f"  → نکته: اولین جمله فقط {fmt_ms(ttfs - ttft)} بعد از اولین توکن آماده شد؛ "
                    "پس انتظار مربوط به بسته‌شدن جمله نیست، به شروع پاسخ مدل است."
                )
            if advice := STAGE_ADVICE.get(advice_key):
                lines.append(f"  → کار پیشنهادی: {advice}")
        text = "\n".join(lines)
        self._log.info(text)
        return text

    def as_dict(self) -> dict[str, object]:
        """Machine-readable snapshot, published to the browser panel."""
        # Expose response_delay explicitly for the UI highlight (equals e2e when SDK provides it)
        last_e2e = self._samples[-1].e2e_ms if self._samples else None
        last_resp = self._samples[-1].stages.get("response_delay") if self._samples else None
        last_tokens = getattr(self._samples[-1], "tokens", []) if self._samples else []
        last_tts = getattr(self._samples[-1], "tts_tokens", []) if self._samples else []
        return {
            "turns": self._turn,
            "averages": {key: round(value, 1) for key, value in self.averages().items()},
            "response_delay_ms": None if last_resp is None else round(last_resp),
            "response_delay_avg_ms": round(self.averages().get("response_delay", 0), 1) if self.averages().get("response_delay") else None,
            "last": (
                {
                    "index": self._samples[-1].index,
                    "e2e_ms": None if self._samples[-1].e2e_ms is None else round(self._samples[-1].e2e_ms),
                    "response_delay_ms": None if last_resp is None else round(last_resp),
                    "stages": {
                        key: (None if value is None else round(value))
                        for key, value in self._samples[-1].stages.items()
                    },
                    "tokens": last_tokens,
                    "tts_tokens": last_tts,
                    "reply_text": getattr(self._samples[-1], "extra", {}).get("reply_preview", "") if hasattr(self._samples[-1], "extra") else "",
                }
                if self._samples
                else None
            ),
        }

    def reset(self) -> None:
        self._samples.clear()
        self._turn = 0
        self._llm_tokens = []
        self._tts_tokens = []
        self._llm_start_ts = None
        self._llm_last_ts = None
        self._tts_pending = None
        self._turn_start_ts = None

    def mark_turn_start(self) -> None:
        self._turn_start_ts = time.time()
