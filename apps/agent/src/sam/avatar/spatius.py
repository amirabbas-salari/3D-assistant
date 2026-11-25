"""Spatiaus avatar — LiveKit Agents integration (TTS پروژه → لب‌زدن Spatius).

Spatiaus رندر را روی کلاینت انجام می‌دهد: ویدیو ترک حاوی motion data است و باید
با @spatius/avatarkit در فرانت رندر شود. بک‌اند فقط صدا را به سرویس Spatius
می‌فرستد و Spatius یک participant ثانویه با ویدیو+صدای همگام به room اضافه می‌کند.
"""

from __future__ import annotations

import logging
import os

from livekit import rtc
from livekit.agents import AgentSession

# ── Spatius plugin must be imported on the main thread ──
try:
    from livekit.plugins import spatius as spatius_plugin  # type: ignore
    _SPATIUS_AVAILABLE = True
    _SPATIUS_IMPORT_ERROR = None
except Exception as _e:  # ImportError or missing dep
    spatius_plugin = None  # type: ignore
    _SPATIUS_AVAILABLE = False
    _SPATIUS_IMPORT_ERROR = _e


def _clean(v: str | None) -> str:
    s = (v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    if s.startswith(('"', "'")) and len(s) > 1 and not s.endswith(('"', "'")):
        s = s[1:].strip()
    return s


async def start_spatius(session: AgentSession, room: rtc.Room, job_logger: logging.Logger):
    api_key = _clean(os.getenv("SPATIUS_API_KEY", ""))
    app_id = _clean(os.getenv("SPATIUS_APP_ID", ""))
    avatar_id = _clean(os.getenv("SPATIUS_AVATAR_ID", ""))

    if not _SPATIUS_AVAILABLE:
        job_logger.error("livekit-plugins-spatius نصب نیست — pip install livekit-plugins-spatius: %s", _SPATIUS_IMPORT_ERROR)
        return None

    if not api_key or not app_id or not avatar_id:
        job_logger.warning(
            "SPATIUS_* ناقص — SPATIUS_API_KEY / SPATIUS_APP_ID / SPATIUS_AVATAR_ID را در .env پر کنید "
            "(api_key=%s app_id=%s avatar_id=%s)",
            "✓" if api_key else "✗",
            "✓" if app_id else "✗",
            "✓" if avatar_id else "✗",
        )
        return None

    sample_rate = int((_clean(os.getenv("SPATIUS_SAMPLE_RATE", "24000")) or "24000"))
    audio_format = _clean(os.getenv("SPATIUS_AUDIO_FORMAT", "pcm_s16le")) or "pcm_s16le"
    # spatius supports pcm_s16le (any rate) and ogg_opus (only 8000,12000,16000,24000,48000)
    # default to pcm_s16le to avoid native libopus requirement
    if audio_format not in {"pcm_s16le", "ogg_opus"}:
        job_logger.warning("SPATIUS_AUDIO_FORMAT=%s نامعتبر — fallback به pcm_s16le", audio_format)
        audio_format = "pcm_s16le"

    region = _clean(os.getenv("SPATIUS_REGION", "")) or "auto"

    kwargs: dict = {}
    # plugin reads from env if not passed, but we pass explicitly for clarity
    if avatar_id:
        kwargs["avatar_id"] = avatar_id
    if api_key:
        kwargs["api_key"] = api_key
    if app_id:
        kwargs["app_id"] = app_id
    if region:
        kwargs["region"] = region
    kwargs["sample_rate"] = sample_rate
    kwargs["audio_format"] = audio_format

    # optional participant identity/name
    kwargs["avatar_participant_identity"] = _clean(os.getenv("SPATIUS_AVATAR_IDENTITY", "spatius-avatar-agent")) or "spatius-avatar-agent"
    kwargs["avatar_participant_name"] = _clean(os.getenv("SPATIUS_AVATAR_NAME", "سام")) or "سام"

    job_logger.info(
        "Spatius AvatarSession در حال ساخت (avatar_id=%s app_id=%s region=%s sr=%s fmt=%s identity=%s)",
        avatar_id[:12] + "…" if len(avatar_id) > 12 else avatar_id,
        app_id[:8] + "…" if len(app_id) > 8 else app_id,
        region,
        sample_rate,
        audio_format,
        kwargs["avatar_participant_identity"],
    )

    try:
        # AvatarSession reads env but we pass kwargs explicitly
        avatar = spatius_plugin.AvatarSession(**kwargs)  # type: ignore
        await avatar.start(session, room)
        job_logger.info("Spatius avatar به اتاق وصل شد — صدای TTS پروژه به Spatius stream می‌شود")
        # Spatius joins as secondary participant; wait a bit for video track
        try:
            await avatar.wait_for_join(timeout=15)
            job_logger.info("Spatius avatar join شد — ویدیو motion در فرانت به زودی می‌آید (نیاز به @spatius/avatarkit-rtc)")
        except Exception as e:
            job_logger.warning("Spatius avatar wait_for_join timeout: %s — ادامه می‌دهیم (ممکن است فرانت هنوز ویدیو نگیرد)", e)
        return avatar
    except Exception as e:
        # handle sample_rate mismatch for ogg_opus
        msg = str(e)
        if "sample_rate" in msg.lower() or "SpatiusException" in type(e).__name__:
            job_logger.exception("ساخت/شروع Spatius avatar ناموفق — احتمالاً sample_rate با ogg_opus ناسازگار است: %s", e)
            job_logger.info("راه‌حل: SPATIUS_AUDIO_FORMAT=pcm_s16le بگذارید (هر نرخ را می‌پذیرد) یا SPATIUS_SAMPLE_RATE را به یکی از 8000,12000,16000,24000,48000 تغییر دهید")
        else:
            job_logger.exception("ساخت/شروع Spatius avatar ناموفق بود: %s", e)
        job_logger.info("ادامه بدون ویدیو Spatius — فقط صدا فعال است. SPATIUS_* را چک کنید یا AVATAR_PROVIDER=tavus کنید")
        return None
