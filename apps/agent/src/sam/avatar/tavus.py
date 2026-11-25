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
    replica_id = os.getenv("TAVUS_REPLICA_ID", "") or os.getenv("TAVUS_FACE_ID", "")
    replica_id = replica_id.strip()
    persona_id = os.getenv("TAVUS_PERSONA_ID", "") or os.getenv("TAVUS_PAL_ID", "")
    persona_id = persona_id.strip()
    languages = (os.getenv("TAVUS_LANGUAGES") or os.getenv("TAVUS_LANGUAGE") or "").strip()
    greeting = (os.getenv("TAVUS_GREETING") or os.getenv("TAVUS_CUSTOM_GREETING") or "").strip()
    context = (os.getenv("TAVUS_CONTEXT") or os.getenv("TAVUS_CONVERSATIONAL_CONTEXT") or "").strip()

    if not api_key:
        job_logger.warning("TAVUS_API_KEY خالی — آواتار بدون Tavus ادامه می‌دهد (فقط صدا)")
        return None
    if not replica_id:
        job_logger.warning("TAVUS_REPLICA_ID خالی — آواتار Tavus بدون replica_id نمی‌سازد")

    # هشدار فارسی — اگر هیچ override نیست و persona انگلیسی باشد، Tavus انگلیسی می‌ماند
    if not languages and not greeting and not context:
        job_logger.warning(
            "Tavus: هیچ TAVUS_LANGUAGES/GREETING/CONTEXT تنظیم نشده — اگر Persona در داشبورد انگلیسی باشد، "
            "آواتار انگلیسی می‌ماند. برای فارسی: TAVUS_LANGUAGES=fa + TAVUS_GREETING فارسی، یا Persona را در maker.tavus.io فارسی کنید. docs/tavus-persian.md را ببینید"
        )

    job_logger.info(
        "Tavus avatar فعال (replica=%s, persona=%s, languages=%s, daily-embed در فرانت)",
        replica_id or "default",
        persona_id or "default",
        languages or "persona-default",
    )
    if greeting:
        job_logger.info("Tavus greeting override: %s...", greeting[:60])
    return None
