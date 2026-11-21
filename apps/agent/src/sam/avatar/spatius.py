import os, logging
from livekit import rtc
from livekit.agents import AgentSession
try:
    from livekit.plugins import spatius as spatius_plugin
    _err=None
except ImportError as exc:
    spatius_plugin=None
    _err=exc
async def start_spatius(session: AgentSession, room: rtc.Room, job_logger: logging.Logger):
    if spatius_plugin is None:
        job_logger.error("livekit-plugins-spatius missing (%s)", _err)
        return None
    sr=int(os.getenv("SPATIUS_SAMPLE_RATE","24000"))
    fmt=os.getenv("SPATIUS_AUDIO_FORMAT","pcm_s16le").strip().lower()
    try:
        av=spatius_plugin.AvatarSession(sample_rate=sr, audio_format=fmt)
        await av.start(session, room)
    except Exception:
        job_logger.exception("Could not start Spatius avatar")
        return None
    job_logger.info("Spatius avatar started (sr=%s Hz, fmt=%s)", sr, fmt)
    return av
