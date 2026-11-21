"""Canonical agent entrypoint — thin facade over modular session.

Legacy: `python agent.py` at repo root still works via root shim.
Canonical: `python -m apps.agent.src.sam.agent` or `python -m sam.agent`
Keep this file tiny; all logic lives in subpackages.
"""
from .session.entrypoint import entrypoint, server
from .assistant.agent import PersianAssistant
from .config.env import PROJECT_ROOT, flag
from .config.speed import SPEED_PROFILES
from .speech import speech_provider, build_stt, build_tts
from .avatar import avatar_provider, start_avatar

__all__ = ["entrypoint", "server", "PersianAssistant", "PROJECT_ROOT", "flag", "SPEED_PROFILES", "speech_provider", "build_stt", "build_tts", "avatar_provider", "start_avatar"]

if __name__ == "__main__":
    import os, logging
    from livekit import agents
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    agents.cli.run_app(server)
