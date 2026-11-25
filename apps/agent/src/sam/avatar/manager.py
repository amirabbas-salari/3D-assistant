from .provider import avatar_provider
from .tavus import start_tavus
from .spatius import start_spatius

async def start_avatar(provider: str, session, room, job_logger):
    if provider == "tavus":
        return await start_tavus(session, room, job_logger)
    if provider == "spatius":
        return await start_spatius(session, room, job_logger)
    if provider not in {"none"}:
        job_logger.warning("AVATAR_PROVIDER=%s ناشناس — پشتیبانی‌شده: tavus, spatius — ادامه بدون آواتار (فقط صدا)", provider)
    return None

# re-export
__all__ = ["avatar_provider", "start_avatar"]
