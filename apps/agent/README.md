# Agent — Python LiveKit Voice Agent

Canonical source is `src/sam/`:

```
src/sam/
├── agent.py        # entrypoint, AgentServer, turn-handling
├── assistant.py    # PersianAssistant prompt (future split)
├── avatar.py       # avatar providers
├── speech.py       # STT/TTS builders
├── latency/        # per-turn millisecond instrumentation
│   └── tracker.py
└── rag/            # BM25 + Chroma retrieval
    └── engine.py
```

Legacy flat files at repo root (`agent.py`, `rag.py`, `latency.py`) are shims that
re-export this package for backward compatibility.

```bash
# from repo root
python agent.py dev
# or from this folder
pip install -e .
python -m sam.agent dev
```
