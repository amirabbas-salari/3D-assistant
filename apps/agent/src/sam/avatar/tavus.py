"""Tavus avatar — LiveKit lip-sync mode (TTS پروژه → لب‌زدن Tavus).

معماری درخواستی کاربر: TTS همین پروژه (OpenRouter/Google) می‌ماند و Tavus فقط
لب می‌زند. برای این کار از LiveKit Avatar Plugin رسمی Tavus استفاده می‌کنیم:

  - Tavus AvatarSession یک participant مجازی (tavus-avatar-agent) به اتاق اضافه
    می‌کند، ویدیو + صدا را خودش publish می‌کند.
  - صدای TTS پروژه via DataStreamAudioOutput به Tavus stream می‌شود و Tavus
    با Phoenix-4.5 لب‌سینک ویدیو تولید می‌کند.

اگر افزونه نصب نباشد یا کلیدها ناقص باشد، فقط لاگ می‌دهد و بدون ویدیو ادامه
می‌دهد (fallback به صدای تنها).

envهای مربوط:
  TAVUS_API_KEY, TAVUS_REPLICA_ID/TAVUS_FACE_ID, TAVUS_PERSONA_ID/TAVUS_PAL_ID
  LIVEKIT_URL/KEY/SECRET (برای ساخت توکن آواتار)
  TAVUS_AVATAR_MODE=livekit (پیش‌فرض) | cvi (Daily iframe قدیمی)
"""
from __future__ import annotations

import logging
import os

from livekit import rtc
from livekit.agents import AgentSession


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
    # support new naming too
    if not replica_id:
        replica_id = _clean(os.getenv("TAVUS_FACE_ID", ""))
    if not persona_id:
        persona_id = _clean(os.getenv("TAVUS_PAL_ID", ""))

    if not api_key:
        job_logger.warning("TAVUS_API_KEY خالی — آواتار بدون Tavus ادامه می‌دهد (فقط صدا)")
        return None
    if not replica_id and not persona_id:
        job_logger.warning("TAVUS_REPLICA_ID/PERSONA_ID خالی — Tavus avatar ساخته نمی‌شود")
        return None

    # mode flag — فعلاً فقط livekit پیاده شده
    mode = _clean(os.getenv("TAVUS_AVATAR_MODE", "livekit")).lower()
    if mode not in {"livekit", "lipsync", "avatar", "cvi"}:
        mode = "livekit"

    # livekit mode = AvatarSession (لب‌زدن به TTS پروژه)
    # cvi mode قبلاً daily iframe بود — در این حالت Agent کاری نمی‌کند
    if mode == "cvi":
        job_logger.info("Tavus CVI mode (Daily iframe) — Agent ویدیو publish نمی‌کند، فرانت iframe می‌سازد (replica=%s persona=%s)", replica_id or "default", persona_id or "default")
        return None

    # --- LiveKit Avatar Plugin ---
    try:
        from livekit.plugins.tavus import AvatarSession as TavusAvatarSession
    except ImportError as e:
        job_logger.error("livekit-plugins-tavus نصب نیست — pip install livekit-plugins-tavus: %s", e)
        return None

    # Tavus API uses face_id/pal_id as current naming (replica_id/persona_id deprecated)
    kwargs: dict = {}
    if replica_id:
        kwargs["replica_id"] = replica_id
    if persona_id:
        kwargs["persona_id"] = persona_id
    # optional: override api url
    api_url = _clean(os.getenv("TAVUS_API_URL", ""))
    if api_url:
        kwargs["api_url"] = api_url
    if api_key:
        kwargs["api_key"] = api_key
    kwargs["avatar_participant_identity"] = _clean(os.getenv("TAVUS_AVATAR_IDENTITY", "tavus-avatar-agent")) or "tavus-avatar-agent"
    kwargs["avatar_participant_name"] = _clean(os.getenv("TAVUS_AVATAR_NAME", "سام")) or "سام"

    try:
        avatar = TavusAvatarSession(**kwargs)
        job_logger.info("Tavus AvatarSession ساخته شد (mode=%s, replica=%s persona=%s, identity=%s)", mode, replica_id or "default", persona_id or "default", kwargs["avatar_participant_identity"])
        # شروع avatar — داخلش create_conversation با livekit_ws_url+token و replace_audio_tail انجام می‌دهد
        await avatar.start(session, room)
        job_logger.info("Tavus avatar به اتاق وصل شد — صدای TTS پروژه به آواتار stream می‌شود (conversation_id=%s)", getattr(avatar, "conversation_id", "?"))
        # منتظر join شدن آواتار (اختیاری، timeout کوتاه)
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
