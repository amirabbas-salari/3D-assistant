"""RAG wiring: load index, tool wrapper, preload helper."""
import os, time, logging
from pathlib import Path
from livekit.agents import llm
from ..config.env import PROJECT_ROOT

def _load_knowledge(job_logger: logging.Logger):
    # lazy import to allow missing rag deps
    try:
        from . import engine as rag_module
    except ImportError:
        try:
            import rag as rag_module  # type: ignore
        except ImportError:
            job_logger.info("RAG: off (rag module missing)")
            return None, None
    config = rag_module.rag_config(PROJECT_ROOT)
    if config is None:
        job_logger.info("RAG: off (set RAG_ENABLED=true)")
        return None, None
    try:
        index = rag_module.RagIndex.load(config["store_dir"], collection=config["collection"])
    except ImportError:
        job_logger.warning("RAG: chromadb not installed. pip install chromadb && python scripts/build_rag_index.py")
        return None, None
    except FileNotFoundError as exc:
        job_logger.warning("RAG: %s — RAG بدون ایندکس ادامه می‌دهد (ساخت: python scripts/build_rag_index.py)", exc)
        return None, None
    except Exception as exc:
        job_logger.warning("RAG: could not load index (%s: %s) — بدون RAG ادامه می‌دهم", type(exc).__name__, exc)
        return None, None
    job_logger.info("%s · %s chunks", rag_module.describe_config(config), len(index))
    return index, config

def _make_knowledge_tool(index, config, job_logger: logging.Logger, timings: dict | None = None):
    top_k = config["top_k"]
    try:
        from . import engine as rag_module
    except ImportError:
        import rag as rag_module  # type: ignore

    @llm.function_tool(
        name="search_knowledge",
        description="Search the organization knowledge base (services, portfolio, FAQ). Call it when the question is about internal facts, pricing, process or past projects. Pass query in Persian keywords. Streams: tool returns fast (<5ms BM25), then LLM streams final answer.",
    )
    async def search_knowledge(query: str) -> str:
        started = time.perf_counter()
        hits = index.search(query, top_k=top_k)
        if timings is not None:
            timings["knowledge_lookup"] = (time.perf_counter() - started) * 1000
        if not hits:
            job_logger.info("RAG: no match for %r", query)
            return "چیزی در پایگاه دانش پیدا نشد. صادقانه بگو پیدا نکردی و با دانش عمومی و تجربه‌ی فروش/مارکتینگ ادامه بده؛ عدد یا نقل‌قول نساز و اگر به جزئیات کسب‌وکار نیاز داری، از کاربر بپرس."
        job_logger.info("RAG: %r → %s", query, ", ".join(f"{h.chunk.source}/{h.chunk.heading}({h.score:.2f})" for h in hits))
        return "متن‌های مرتبط از پایگاه دانش (فقط بر اساس همین‌ها پاسخ بده):\n\n" + rag_module.format_hits(hits)
    return search_knowledge

def _rag_preload(query: str, index, config, job_logger: logging.Logger, timings: dict | None = None) -> str | None:
    if not query or not query.strip():
        return None
    started = time.perf_counter()
    try:
        hits = index.search(query.strip(), top_k=config["top_k"])
    except Exception as exc:
        job_logger.warning("RAG preload search failed: %s", exc)
        return None
    if timings is not None:
        timings["knowledge_lookup"] = (time.perf_counter() - started) * 1000
    if not hits:
        job_logger.info("RAG preload: no match for %r", query[:80])
        return None
    job_logger.info("RAG preload: %r → %s", query[:80], ", ".join(f"{h.chunk.source}({h.score:.2f})" for h in hits))
    try:
        from . import engine as rag_module
    except ImportError:
        import rag as rag_module  # type: ignore
    return rag_module.format_hits(hits)
