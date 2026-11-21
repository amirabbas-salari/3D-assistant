import os, logging
from livekit import rtc
from livekit.agents import AgentSession
try:
    from livekit.plugins import did as did_plugin
    _err=None
except ImportError as exc:
    did_plugin=None
    _err=exc
async def start_did(session: AgentSession, room: rtc.Room, job_logger: logging.Logger):
    agent_id=os.getenv("DID_AGENT_ID","").strip()
    if not agent_id:
        job_logger.error("DID_AGENT_ID empty; continuing without avatar")
        return None
    if did_plugin is None:
        job_logger.error("livekit-plugins-did missing (%s)", _err)
        return None
    sr=int(os.getenv("DID_AUDIO_SAMPLE_RATE","24000"))
    try:
        av=did_plugin.AvatarSession(agent_id=agent_id, audio_config=did_plugin.AudioConfig(sample_rate=sr))
        await av.start(session, room)
    except Exception:
        job_logger.exception("Could not start D-ID avatar")
        return None
    job_logger.info("D-ID avatar started (agent=%s, session=%s, sr=%s)", agent_id, getattr(av,"session_id",None), sr)
    return av
