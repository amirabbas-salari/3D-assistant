"""Entry for `python -m sam.agent` — delegates to agent.py's CLI."""
from .agent import *  # noqa: F403
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from sam.agent import server as _server  # noqa: E402
import logging, os
from livekit import agents as _agents

if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    _agents.cli.run_app(_server)
