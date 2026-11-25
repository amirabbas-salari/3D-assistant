"""Tavus avatar — LiveKit lip-sync mode (TTS پروژه → لب‌زدن Tavus)."""

from __future__ import annotations

import logging
import os

from livekit import rtc
from livekit.agents import AgentSession

# ── Tavus plugin must be imported on the main thread ──
# LiveKit requires Plugin.register_plugin() on main thread, so we import here
# at module load (prewarm/main), not inside the job entrypoint.
try:
    from livekit.plugins.tavus import AvatarSession as TavusAvatarSession  # type: ignore
    _TAVUS_AVAILABLE = True
except Exception as _e:  # ImportError or missing dep
    TavusAvatarSession = None  # type: ignore
    _TAVUS_AVAILABLE = False
    _TAVUS_IMPORT_ERROR = _e
else:
    _TAVUS_IMPORT_ERROR = None


def _clean(v: str | None) -> str:
    s = (v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    if s.startswith(('"', "'")) and len(s) > 1 and not s.endswith(('"', "'")):
        s = s[1:].strip()
    return s


async def start_tavus(session: AgentSession, room: rtc.Room, job_logger: logging.Logger):
    api_key = _clean(os.getenv("TAVUS_API_KEY", ""))
    replica_id = _clean(os.getenv("TAVUS_REPLICA_ID", "") or os.getenv("TAVUS_FACE_ID", ""))
    persona_id = _clean(os.getenv("TAVUS_PERSONA_ID", "") or os.getenv("TAVUS_PAL_ID", ""))

    if not api_key:
        job_logger.warning("TAVUS_API_KEY خالی — آواتار بدون Tavus ادامه می‌دهد (فقط صدا)")
        return None
    if not replica_id and not persona_id:
        job_logger.warning("TAVUS_REPLICA_ID/PERSONA_ID خالی — Tavus avatar ساخته نمی‌شود")
        return None

    mode = _clean(os.getenv("TAVUS_AVATAR_MODE", "livekit")).lower()
    if mode not in {"livekit", "lipsync", "avatar", "cvi"}:
        mode = "livekit"

    if mode == "cvi":
        job_logger.info("Tavus CVI mode (Daily iframe) — Agent ویدیو publish نمی‌کند، فرانت iframe می‌سازد (replica=%s persona=%s)", replica_id or "default", persona_id or "default")
        return None

    if not _TAVUS_AVAILABLE:
        job_logger.error("livekit-plugins-tavus نصب نیست — pip install livekit-plugins-tavus: %s", _TAVUS_IMPORT_ERROR)
        return None

    kwargs: dict = {}
    if replica_id:
        kwargs["replica_id"] = replica_id
    if persona_id:
        kwargs["persona_id"] = persona_id
    api_url = _clean(os.getenv("TAVUS_API_URL", ""))
    if api_url:
        kwargs["api_url"] = api_url
    if api_key:
        kwargs["api_key"] = api_key
    kwargs["avatar_participant_identity"] = _clean(os.getenv("TAVUS_AVATAR_IDENTITY", "tavus-avatar-agent")) or "tavus-avatar-agent"
    kwargs["avatar_participant_name"] = _clean(os.getenv("TAVUS_AVATAR_NAME", "سام")) or "سام"

    try:
        avatar = TavusAvatarSession(**kwargs)  # type: ignore
        job_logger.info("Tavus AvatarSession ساخته شد (mode=%s, replica=%s persona=%s, identity=%s)", mode, replica_id or "default", persona_id or "default", kwargs["avatar_participant_identity"])
        await avatar.start(session, room)
        job_logger.info("Tavus avatar به اتاق وصل شد — صدای TTS پروژه به آواتار stream می‌شود (conversation_id=%s)", getattr(avatar, "conversation_id", "?"))
        try:
            await avatar.wait_for_join(timeout=15)
            job_logger.info("Tavus avatar join شد — ویدیو در فرانت به زودی می‌آید")
        except Exception as e:
            job_logger.warning("Tavus avatar wait_for_join timeout: %s — ادامه می‌دهیم", e)
        return avatar
    except Exception as e:
        job_logger.exception("ساخت/شروع Tavus avatar ناموفق بود: %s", e)
        job_logger.info("ادامه بدون ویدیو — فقط صدا فعال است. Tavus API key / replica / persona را چک کنید")
        return None
