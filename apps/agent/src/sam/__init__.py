"""سام — Persian voice agent package.

This is the new canonical location for the agent. The flat files at the
repository root (`agent.py`, `rag.py`, `latency.py`) are kept as shims for
backward compatibility and will emit a deprecation warning.

Canonical imports:
    from sam.agent import entrypoint
    from sam.rag.engine import RagIndex
    from sam.latency.tracker import LatencyTracker
"""
__all__ = ["agent", "rag", "latency"]
__version__ = "1.0.0"
