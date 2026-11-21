from .provider import avatar_provider
from .spatius import start_spatius
from .did import start_did
async def start_avatar(provider: str, session, room, job_logger):
    if provider=="did": return await start_did(session, room, job_logger)
    if provider=="spatius": return await start_spatius(session, room, job_logger)
    return None
# re-export
__all__=["avatar_provider","start_avatar"]
