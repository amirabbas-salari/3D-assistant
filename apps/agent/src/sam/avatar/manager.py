from .provider import avatar_provider
from .tavus import start_tavus

async def start_avatar(provider: str, session, room, job_logger):
    if provider == "tavus":
        return await start_tavus(session, room, job_logger)
    return None

# re-export
__all__ = ["avatar_provider", "start_avatar"]
