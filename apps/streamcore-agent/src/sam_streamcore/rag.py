"""
RAG نازک — از apps/agent بازاستفاده، ولی بدون وابستگی LiveKit
اگر knowledge/index نبود، خاموش می‌مونه
"""
import os
from pathlib import Path

_par = Path(__file__).resolve().parents
PROJECT_ROOT = _par[4] if len(_par) > 4 else _par[-1]
if not (PROJECT_ROOT / ".env.example").exists():
    for anc in _par:
        if (anc / ".env.example").exists():
            PROJECT_ROOT = anc
            break
    else:
        PROJECT_ROOT = Path("/app") if Path("/app/prompts").exists() else Path.cwd()

def _try_load_rag():
    try:
        import sys
        # اضافه کردن apps/agent به sys.path تا از همون engine استفاده کنیم
        agent_src = PROJECT_ROOT / "apps" / "agent" / "src"
        if str(agent_src) not in sys.path:
            sys.path.insert(0, str(agent_src))
        from sam.rag.tools import _load_knowledge
        import logging
        logger = logging.getLogger("sam-streamcore.rag")
        idx, cfg = _load_knowledge(logger)
        return idx, cfg
    except Exception as e:
        import logging
        logging.getLogger("sam-streamcore.rag").warning("RAG load failed, disabled: %s", e)
        return None, None

_rag_index, _rag_config = None, None
_rag_ready = False

def ensure_rag():
    global _rag_index, _rag_config, _rag_ready
    if _rag_ready:
        return _rag_index, _rag_config
    _rag_ready = True
    if os.getenv("RAG_ENABLED", "false").strip().lower() not in {"1","true","yes","on"}:
        return None, None
    _rag_index, _rag_config = _try_load_rag()
    return _rag_index, _rag_config

def rag_query(query: str) -> str | None:
    idx, cfg = ensure_rag()
    if not idx or not query:
        return None
    try:
        from sam.rag.tools import _rag_preload
        import logging
        logger = logging.getLogger("sam-streamcore.rag")
        # timings dict خالی
        return _rag_preload(query, idx, cfg, logger, {})
    except Exception:
        return None
