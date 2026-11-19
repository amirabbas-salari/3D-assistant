"""Build the RAG index, or query it without starting the agent.

Index everything in the knowledge folder:

    python scripts/build_rag_index.py

Then ask a question the way the agent's tool would, to see what it would read:

    python scripts/build_rag_index.py --query "مرخصی استعلاجی چند روز است؟"

The second form is the fastest way to judge retrieval quality: if the right
passage is not in the top three here, the model will not see it either.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rag  # noqa: E402  - after sys.path so the script runs from anywhere

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def cmd_build(args) -> int:
    docs_dir = rag.resolve_path(PROJECT_ROOT, args.docs)
    store_dir = rag.resolve_path(PROJECT_ROOT, args.store)

    if not docs_dir.exists():
        print(f"❌ پوشه‌ی دانش پیدا نشد: {docs_dir}")
        print("   بسازیدش و فایل‌های .md یا .txt را داخلش بگذارید، یا RAG_DOCS_DIR را تنظیم کنید.")
        return 1

    started = time.perf_counter()
    try:
        summary = rag.build_index(
            docs_dir, store_dir, collection=args.collection, max_chars=args.chunk_chars
        )
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    summary["built_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rag.write_manifest(store_dir, summary)

    print(f"\n✅ ایندکس ساخته شد در {elapsed_ms:.0f} ms")
    print(f"   پوشه‌ی دانش : {docs_dir}")
    print(f"   ذخیره‌سازی  : {store_dir}")
    print(f"   فایل‌ها     : {summary['files']}")
    print(f"   تکه‌ها      : {summary['chunks']}")
    print("\nمرحله‌ی بعد: RAG_ENABLED=true را در .env بگذارید و ایجنت را اجرا کنید.")
    print('می‌خواهید کیفیت بازیابی را ببینید؟ python scripts/build_rag_index.py --query "..."')
    return 0


def cmd_query(args) -> int:
    store_dir = rag.resolve_path(PROJECT_ROOT, args.store)
    try:
        index = rag.RagIndex.load(store_dir, collection=args.collection)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1

    print(f"ایندکس: {len(index)} تکه از {store_dir}\n")
    for query in args.query:
        started = time.perf_counter()
        hits = index.search(query, top_k=args.top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000

        print(f"❓ {query}   ({elapsed_ms:.3f} ms)")
        if not hits:
            print("   چیزی پیدا نشد — مدل هم چیزی نخواهد دید.\n")
            continue
        for position, hit in enumerate(hits, 1):
            preview = hit.chunk.text[:110].replace("\n", " ")
            print(f"   [{position}] {hit.score:5.2f}  {hit.chunk.source} › {hit.chunk.heading}")
            print(f"        {preview}…")
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or query the knowledge index used by the agent's search_knowledge tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="الگوهای متغیر محیطی: RAG_DOCS_DIR, RAG_STORE_DIR, RAG_COLLECTION, RAG_TOP_K",
    )
    parser.add_argument("--docs", default=None, help="knowledge folder (default: RAG_DOCS_DIR or ./knowledge)")
    parser.add_argument("--store", default=None, help="index folder (default: RAG_STORE_DIR or ./.rag/chroma)")
    parser.add_argument("--collection", default=None, help="Chroma collection name (default: knowledge)")
    parser.add_argument("--chunk-chars", type=int, default=rag.DEFAULT_CHUNK_CHARS,
                        help=f"target chunk size (default {rag.DEFAULT_CHUNK_CHARS})")
    parser.add_argument("--query", action="append", help="search instead of building; repeatable")
    parser.add_argument("--top-k", type=int, default=rag.DEFAULT_TOP_K,
                        help=f"how many chunks to show (default {rag.DEFAULT_TOP_K})")
    args = parser.parse_args()

    config = rag.rag_config(PROJECT_ROOT) or {}
    # Explicit flags win; otherwise the same env vars the agent uses, otherwise defaults.
    if args.docs is None:
        args.docs = str(config.get("docs_dir", "knowledge"))
    if args.store is None:
        args.store = str(config.get("store_dir", ".rag/chroma"))
    if args.collection is None:
        args.collection = config.get("collection", rag.COLLECTION_NAME)
    if config.get("top_k"):
        args.top_k = args.top_k if args.top_k != rag.DEFAULT_TOP_K else config["top_k"]

    if args.query:
        return cmd_query(args)
    return cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
