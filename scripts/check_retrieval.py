"""Does retrieval actually put the answer where the model can read it?

Green build means the agent can answer without inventing anything. Run this
after editing anything in knowledge/ — a reworded product page can silently
stop being findable, and the failure shows up as the agent confidently making
up a price instead of as an error.

    python scripts/check_retrieval.py

Each case is a question a real customer would ask plus a string that must
appear in the retrieved context. The string is the actual answer, so a pass
means the model has the fact in front of it, not that the ranking "looks
reasonable".
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/agent/src"))
sys.path.insert(0, str(ROOT))

try:
    import sam.rag.engine as rag  # new package layout
    # shim: expose same names as legacy rag module
    rag.resolve_path = rag.resolve_path
    rag.build_index = rag.build_index
except ImportError:
    import rag  # noqa: E402  - legacy flat layout

# (question, a string that must be in the context, a label). The label exists
# so a failure says what capability broke, not just "a test failed".
CASES: list[tuple[str, str, str]] = [
    # Products: the price and stock questions are the ones that hurt most when
    # they fail, because the model will invent a number rather than go quiet.
    ("قهوه ساز A1 قیمتش چنده؟", "۳٫۸۵۰٫۰۰۰", "قیمت محصول A1"),
    ("موجودی A2 چقدره؟", "۶ عدد", "موجودی محصول A2"),
    ("گارانتی A1 چند ماهه؟", "۲۴ ماه", "گارانتی محصول A1"),
    ("آسیاب G2 چند درجه داره؟", "۴۵ درجه", "مشخصات آسیاب G2"),
    ("ارزان‌ترین قهوه‌ساز کدومه؟", "۳٫۸۵۰٫۰۰۰", "مقایسه‌ی قیمت دو مدل"),
    ("برای اسپرسو کدوم آسیاب؟", "G2", "تطبیق محصول با نیاز"),
    ("G1 با G2 چه فرقی داره؟", "سنگ‌آسیاب", "مقایسه‌ی دو آسیاب"),
    ("A1 اسپرسو درست می‌کنه؟", "اسپرسو", "محدودیت محصول"),
    ("برای چهار نفر چی مناسبه؟", "۱.۸ لیتر", "انتخاب بر اساس ظرفیت"),
    # Policies: a wrong answer here costs money or trust.
    ("ارسال به شیراز چند روزه؟", "۲ تا ۳ روز", "زمان ارسال"),
    ("مرجوعی چند روز مهلت داره؟", "۷ روز", "مهلت بازگشت"),
    ("با کارت اعتباری می‌شه قسطی خرید؟", "اقساط", "شرایط پرداخت"),
    # Marketing: what the assistant may honestly offer.
    ("کد تخفیف چیه؟", "COFFEE10", "کد تخفیف فعال"),
    ("بسته شروع شامل چیه؟", "بسته‌ی شروع", "بسته‌ی پیشنهادی"),
    ("برای هدیه چی پیشنهاد می‌دی؟", "هدیه", "پیشنهاد بر اساس موقعیت"),
]

# Questions about a specific product's facts must be answered by that product's
# page. If marketing guidance outranks the real page, the agent is quoting
# sales coaching as if it were a product fact — a pass at top_k=3 would be luck.
PRODUCT_FACTS = {
    "قیمت محصول A1",
    "موجودی محصول A2",
    "گارانتی محصول A1",
    "مشخصات آسیاب G2",
    "مقایسه‌ی قیمت دو مدل",
    "مقایسه‌ی دو آسیاب",
    "محدودیت محصول",
}
COACHING = ("customer-segments", "offers-and-campaigns")


def main() -> int:
    store = rag.resolve_path(ROOT, __import__("os").getenv("RAG_STORE_DIR", ".rag/chroma"))
    try:
        index = rag.RagIndex.load(store)
    except FileNotFoundError:
        print(f"no index at {store}\nbuild it first: python scripts/build_rag_index.py")
        return 2

    top_k = 3
    failures = 0
    print(f"{len(index)} chunks, top_k={top_k}\n")
    for question, expected, label in CASES:
        hits = index.search(question, top_k=top_k)
        context = "\n".join(h.chunk.text for h in hits)
        found = expected in context
        best = hits[0].chunk.source if hits else "—"
        weak = found and label in PRODUCT_FACTS and any(c in best for c in COACHING)
        failures += not found
        mark = "FAIL" if not found else ("WEAK" if weak else "ok  ")
        print(f"{mark}  {question}")
        print(f"        want {expected!r}  ·  best: {best}")
        for hit in hits:
            print(f"          {hit.score:5.2f}  {hit.chunk.source} › {hit.chunk.heading}")

    print()
    if failures:
        print(f"{failures} of {len(CASES)} questions cannot be answered from the index.")
        return 1
    print(f"all {len(CASES)} questions are answerable from the retrieved context.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
