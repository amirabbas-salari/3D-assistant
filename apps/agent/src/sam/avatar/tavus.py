"""Tavus avatar — render-only mode (pipeline در LiveKit می‌ماند).

معماری درخواستی: STT/LLM/TTS همین LiveKit می‌ماند، Tavus فقط برای نمایش ویدیو و لب‌سینک می‌آید.
فعلاً سمت Agent فقط لاگ + health-check می‌کنیم؛ رندر اصلی در فرانت‌اند با Daily iframe
از conversation_url که از /api/tavus/conversation می‌آید انجام می‌شود.

چرا سمت Agent چیزی publish نمی‌کند؟ Tavus CVI فول‌پایپ‌لاین خودش را دارد که با Daily کار می‌کند
و صدای LiveKit را مستقیم نمی‌گیرد. در حالت render_only ما فقط می‌خواهیم Agent را فعال نگه داریم
و ویدیو را جدا در فرانت نشان دهیم — بدون هزینه و پیچیدگی Daily↔LiveKit bridge.
"""
import logging
import os

from livekit import rtc
from livekit.agents import AgentSession


async def start_tavus(session: AgentSession, room: rtc.Room, job_logger: logging.Logger):
    api_key = os.getenv("TAVUS_API_KEY", "").strip()
    replica_id = os.getenv("TAVUS_REPLICA_ID", "").strip()
    persona_id = os.getenv("TAVUS_PERSONA_ID", "").strip()

    if not api_key:
        job_logger.warning("TAVUS_API_KEY خالی — آواتار بدون Tavus ادامه می‌دهد (فقط صدا)")
        return None
    if not replica_id:
        job_logger.warning("TAVUS_REPLICA_ID خالی — آواتار Tavus بدون replica_id نمی‌سازد")

    # Health log — ساخت conversation در فرانت انجام می‌شود تا Daily URL مستقیم در مرورگر باز شود.
    # اینجا فقط ثبت می‌کنیم که Agent آماده است و Tavus فعال است.
    job_logger.info(
        "Tavus avatar فعال (replica=%s, persona=%s, daily-embed در فرانت)",
        replica_id or "default",
        persona_id or "default",
    )
    return None
