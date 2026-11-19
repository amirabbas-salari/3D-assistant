"""Millisecond turn-latency instrumentation for the voice pipeline.

The agent already knows how long every stage took, but it only puts those numbers
on ``ChatMessage.metrics`` — invisible unless you attach a debugger. This module
turns each turn into one structured log line, plus a rolling summary that names
the worst stage, so a bottleneck is obvious from the terminal or the browser
diagnostics panel instead of being guessed at.

The numbers come from the SDK, not from timestamps we invent:

* ``e2e_latency`` — user stopped speaking → agent audio started.
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
STAGES: tuple[tuple[str, str], ...] = (
    ("end_of_turn_delay", "پایان گفتار ← تشخیص پایان نوبت"),
    ("transcription_delay", "پایان گفتار ← متن نهایی STT"),
    ("llm_node_ttft", "درخواست LLM ← اولین توکن"),
    ("llm_node_ttfs", "درخواست LLM ← اولین جمله به TTS"),
    ("tts_node_ttfb", "اولین جمله ← اولین بایت صدا"),
    ("playback_latency", "اولین فریم ← شروع پخش"),
)

STAGE_LABELS = dict(STAGES)

# What actually moves each stage. A bottleneck line that names a setting is
# actionable; one that only names a duration is trivia.
STAGE_ADVICE: dict[str, str] = {
    "end_of_turn_delay":
        "انتظار سکوت است، نه مدل → AGENT_SPEED_PROFILE=fast (یا AGENT_MIN_ENDPOINTING_DELAY)",
    "transcription_delay":
        "نهایی‌شدن متن STT → مدل/زبان STT یا SPEECH_PROVIDER=direct را بررسی کنید",
    "llm_node_ttft":
        "زمان اولین توکن مدل است، نه میکروفون → مدل gpt-oss پیش از پاسخ «فکر» می‌کند؛ "
        "CLOUDFLARE_LLM_REASONING_EFFORT=low (پیش‌فرض) و با scripts/check_llm_speed.py اندازه بگیرید",
    "llm_node_ttfs":
        "مدل دیر جمله را می‌بندد → جمله‌ی اول کوتاه (AGENT_FAST_START=true) یا پاسخ کوتاه‌تر",
    "tts_node_ttfb":
        "زمان اولین بایت صدا → مسیر TTS؛ با GeminiTTS واسط جمله‌ای SDK دخیل است",
    "playback_latency":
        "تحویل صدا به خروجی → با آواتار روشن معمولاً همان مسیر آواتار است",
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
    return f"{value:.1f}ms"


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
    ) -> TurnSample | None:
        """Log one assistant turn and return its sample."""
        self._turn += 1
        assistant_stages = parse_metrics(metrics)
        # Merge the user half (endpointing, transcription) with the assistant
        # half (LLM, TTS, playback); whichever is missing stays None.
        stages = dict(self._pending_user or {})
        stages.update({k: v for k, v in assistant_stages.items() if v is not None})
        for key in assistant_stages:
            stages.setdefault(key, None)
        self._pending_user = None
        e2e = stage_ms(metrics or {}, "e2e_latency")
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
        )
        self._samples.append(sample)

        if self.enabled:
            self._log_turn(sample)
        if self.report_interval and self._turn % self.report_interval == 0:
            self.summary(prefix="میانگین")
        return sample

    def _log_turn(self, sample: TurnSample) -> None:
        stages = sample.stages
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
        return {
            "turns": self._turn,
            "averages": {key: round(value, 1) for key, value in self.averages().items()},
            "last": (
                {
                    "index": self._samples[-1].index,
                    "e2e_ms": None if self._samples[-1].e2e_ms is None else round(self._samples[-1].e2e_ms),
                    "stages": {
                        key: (None if value is None else round(value))
                        for key, value in self._samples[-1].stages.items()
                    },
                }
                if self._samples
                else None
            ),
        }

    def reset(self) -> None:
        self._samples.clear()
        self._turn = 0
