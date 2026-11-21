"""Entry for `python -m sam.agent`."""
from .agent import server
import logging, os
from livekit import agents
if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    agents.cli.run_app(server)
