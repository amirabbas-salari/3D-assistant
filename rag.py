# LEGACY SHIM — canonical: apps/agent/src/sam/rag/engine.py (see ARCHITECTURE.md)
"""Local retrieval over a folder of documents, ranked with BM25.

Why this shape
--------------
Chroma stores the chunks; BM25 ranks them. Chroma has no keyword/BM25 search
of its own (only vector similarity), and its default embedding function
downloads an English model on first use — bad for Persian, and a network
dependency in the middle of a conversation. So the embeddings Chroma needs are
supplied locally and deterministically, and the ranking that actually decides
what the model reads is BM25 over Persian-normalised tokens.

The result: no API keys, no model downloads, no network calls at query time.
A lookup costs single-digit milliseconds, which matters because this project's
priority is latency and a tool call already costs a full LLM round-trip.

Public API
----------
``build_index``     index a folder into Chroma (used by scripts/build_rag_index.py)
``RagIndex``        load an existing index and answer ``search`` queries
``normalize``       Persian text normalisation shared by indexing and querying
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

COLLECTION_NAME = "knowledge"

# Chunk size in characters. Persian text is compact, so ~700 characters is a
# few sentences — enough to answer from, small enough that three of them fit in
# a prompt without spending noticeable LLM time.
DEFAULT_CHUNK_CHARS = 700
DEFAULT_OVERLAP_CHARS = 120
DEFAULT_TOP_K = 3

# BM25 parameters. k1 controls term-frequency saturation, b the length penalty.
BM25_K1 = 1.5
BM25_B = 0.75

# How much a matching document title multiplies a chunk's score, per matching
# token. Large enough to put the right product on top, small enough that it
# cannot rescue a chunk with no body match at all.
TITLE_BOOST = 1.5

# Very common Persian words. Dropping them stops "و" or "که" from matching
# every chunk; this is not a full stemmer, just the noise floor.
#
# Question words belong here for a subtler reason: BM25 rewards rarity, and a
# question word is rare in a document collection precisely because it is
# something you ask rather than write down. Left in, "گارانتی چند ماهه؟"
# matched a marketing note on «چند» alone with a higher weight (3.53) than on
# «گارانتی» (1.92), and answered a warranty question with sales advice. The
# word that carries the answer is the noun, never the question word.
_STOPWORDS = frozenset(
    """
    و در به از که این آن را با برای تا هم یا اگر ولی اما چون چه چیزی
    است هست بود شد شود می ها های هایش خود ما شما او آنها ایشان من
    یک دو نه بله خیر آیا کدام کجا کی چگونه چرا بین روی زیر می نمی
    چند چقدر چنده چطور کدوم کدومه چیه باشد باشه بشه کرده کنند کنید
    """.split()
)

# Persian/Arabic characters that look different but mean the same letter, plus
# the digits that appear in real Persian text.
_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    }
)

# Unicode-aware word matcher: \w includes Persian and Latin letters and digits
# while excluding "_". Persian punctuation inside the Arabic block (comma,
# semicolon, question mark) is not a word character, so it never sticks to a
# token the way a naive [\u0600-\u06FF]+ range would let it.
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def normalize(text: str) -> str:
    """Lowercase, unify Persian letter variants, and drop diacritics."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_CHAR_MAP)
    # Arabic diacritics (fatha, kasra, ...) carry no meaning for search.
    text = re.sub("[\u064B-\u0652\u0670\u0640]", "", text)
    # ZWNJ is a "half space": it joins word parts into a single word, so it is
    # removed rather than turned into a space. Writing "mi-ravam" with a ZWNJ
    # and with no separator must produce the same token.
    text = text.replace("\u200c", "").lower()
    return re.sub(r"\s+", " ", text).strip()


# The present-tense prefix is written attached ("mi-ravam"), detached
# ("mi ravam"), or with an Arabic letter. Emitting the stem as well costs
# nothing and makes all three spellings find the same chunk, without a real
# stemmer.
_VERB_PREFIXES = ("نمی", "می")


# Persian attaches possessives and plurals directly to the noun: a customer
# asks "قیمتش چنده؟" while the document says "قیمت:". Those are different
# tokens, so the most natural way to ask a price would miss the price. The
# suffixes below are the common ones; both forms are emitted, so a document
# written in either style matches either question.
_SUFFIXES = (
    # Comparative and superlative: a customer asks "ارزان‌ترین کدام است؟"
    # while the page says "ارزان‌تر". Both reduce to "ارزان".
    "ترین", "تر",
    "هایی", "هایم", "هایت", "هایش", "های", "ها",
    # Colloquial spoken forms of the same endings ("قهوه‌سازتون").
    "تون", "مون", "شون",
    "مان", "تان", "شان", "یم", "ید", "ند", "ام", "ات", "اش",
    "ش", "م", "ت",
)


def _stem_suffixes(word: str) -> str | None:
    """The base form of a noun with a possessive/plural ending, if any."""
    for suffix in _SUFFIXES:
        if not word.endswith(suffix):
            continue
        stem = word[: -len(suffix)]
        # A single letter is often part of the word itself ("قیمت" ends in
        # "ت"), so a one-letter suffix only counts when plenty is left over.
        if len(stem) >= (4 if len(suffix) == 1 else 3):
            return stem
        return None
    return None


def tokenize(text: str) -> list[str]:
    """Tokens used by BM25: normalised, stopwords removed, length >= 2."""
    words = [t for t in _WORD_RE.findall(normalize(text)) if len(t) >= 2]
    tokens: list[str] = []
    for token in words:
        if token in _STOPWORDS:
            continue
        tokens.append(token)
        base = _stem_suffixes(token)
        if base:
            tokens.append(base)
        for prefix in _VERB_PREFIXES:
            # Emit the stem, and for "نمی" also the "می" form, so a negated verb
            # still matches documents that only use the positive one. The bare
            # prefix is never a token on its own.
            if token.startswith(prefix):
                stem = token[len(prefix):]
                if len(stem) >= 3:
                    tokens.append(stem)
                    if prefix == "نمی":
                        tokens.append("می" + stem)
                break
    # Persian compounds are written both with a half-space and with a real
    # space: "قهوه‌ساز" and "قهوه ساز" are the same product, but normalisation
    # turns the first into one token and the second into two, so neither finds
    # the other. Emitting every adjacent pair joined closes the gap in both
    # directions without a dictionary. Applied to documents and queries alike,
    # so the two spellings meet in the middle.
    bases = [_stem_suffixes(word) or word for word in words]
    for first, second in zip(bases, bases[1:]):
        tokens.append(first + second)
    return tokens


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of a source document."""

    id: str
    text: str
    source: str
    heading: str
    ordinal: int
    # The document's level-1 heading. A question naming the document should
    # prefer that document's chunks over guidance prose that merely mentions
    # the same words, which is exactly how a price question was landing on a
    # marketing note that happened to quote it.
    title: str = ""

    def as_prompt_block(self, position: int) -> str:
        """Format for the LLM, with enough provenance to be quotable."""
        where = f"{self.source} › {self.heading}" if self.heading else self.source
        return f"[{position}] ({where})\n{self.text}"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")


def split_sentences(text: str) -> list[str]:
    """Split on sentence punctuation, keeping the punctuation."""
    parts = re.split(r"(?<=[.!?؟۔])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, *, max_chars: int = DEFAULT_CHUNK_CHARS,
               overlap: int = DEFAULT_OVERLAP_CHARS) -> list[tuple[str, str, str]]:
    """Split a document into (heading, chunk) pairs.

    Headings are tracked so a chunk knows where it came from. Splitting happens
    between sentences, and the overlap carried into the next chunk is made of
    whole trailing sentences — slicing raw characters would hand the model a
    chunk that starts mid-word, which reads as corruption and can change the
    meaning of the first line it sees.
    """
    results: list[tuple[str, str, str]] = []
    heading = ""
    # The level-1 heading names the document. Without it a chunk of product
    # facts ("- قیمت: ۳٫۸۵۰٫۰۰۰ تومان") carries no product name at all, so a
    # question naming the product cannot find it — the heading tracker below
    # overwrites it with the nearest sub-heading ("قیمت و موجودی").
    doc_title = ""
    buffer: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buffer, size
        if not buffer:
            return
        body = " ".join(buffer).strip()
        if body:
            if doc_title:
                # Also what the model reads, so each chunk says what it is about.
                body = f"{doc_title} — {body}"
            results.append((heading, body, doc_title))
        # Choose whole trailing sentences for the overlap, newest-last.
        tail: list[str] = []
        tail_len = 0
        for sentence in reversed(buffer):
            if tail_len + len(sentence) > overlap or tail_len + size > max_chars:
                break
            tail.insert(0, sentence)
            tail_len += len(sentence) + 1
        buffer = tail
        size = tail_len

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = _HEADING_RE.match(line)
        if match:
            flush()
            title = match.group(2).strip()
            if len(match.group(1)) == 1 and not doc_title:
                doc_title = title
            heading = title
            # A heading is a hard boundary: carrying context across it would
            # label text from the previous section with the new section's name.
            buffer, size = [], 0
            continue
        if not line.strip():
            continue
        for sentence in split_sentences(line):
            if size + len(sentence) + 1 > max_chars and buffer:
                flush()
            buffer.append(sentence)
            size += len(sentence) + 1
    flush()
    return [(h, c, t) for h, c, t in results if len(c) >= 40]


def iter_source_files(root: Path) -> list[Path]:
    """Every indexable file under ``root``, marking unsupported types skipped."""
    suffixes = {".md", ".markdown", ".txt", ".text", ".rst"}
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1256"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Local embedding function for Chroma
# --------------------------------------------------------------------------- #


def _hashed_embedding(text: str, dims: int = 512) -> list[float]:
    """Deterministic bag-of-tokens vector.

    This is not semantic: it only exists because Chroma requires embeddings to
    store items. Ranking is BM25, which reads the stored documents. Determinism
    matters because the same text must always produce the same vector, and a
    hashed vector needs no model file, no download, and no network.
    """
    vector = [0.0] * dims
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class LocalEmbedding:
    """Chroma embedding function backed by :func:`_hashed_embedding`."""

    def __init__(self, dims: int = 512) -> None:
        self._dims = dims

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002 - Chroma's name
        return [_hashed_embedding(text, self._dims) for text in input]

    def name(self) -> str:
        return "sam-local-hash"

    def get_config(self) -> dict:
        return {"dims": self._dims}

    @staticmethod
    def build_from_config(config: dict) -> "LocalEmbedding":
        return LocalEmbedding(int(config.get("dims", 512)))

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def is_legacy(self) -> bool:
        return False


def resolve_path(root: Path, value: str) -> Path:
    """Resolve a possibly-relative configured path against the project root."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path)


# --------------------------------------------------------------------------- #
# Index building
# --------------------------------------------------------------------------- #


def build_index(
    docs_dir: Path,
    store_dir: Path,
    *,
    collection: str = COLLECTION_NAME,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
    log=print,
) -> dict:
    """Build (or rebuild) the Chroma store from every document in ``docs_dir``.

    Returns a small summary dict so the CLI can print something useful.
    """
    import chromadb

    files = iter_source_files(docs_dir)
    if not files:
        raise FileNotFoundError(
            f"No indexable files in {docs_dir} (looked for .md, .txt, .rst). "
            "Add documents or set RAG_DOCS_DIR to the right folder."
        )

    chunks: list[tuple[str, str, str, int, str]] = []
    for path in files:
        relative = str(path.relative_to(docs_dir))
        found = chunk_text(_read_text(path), max_chars=max_chars, overlap=overlap)
        for ordinal, (heading, text, title) in enumerate(found):
            chunks.append((relative, heading, text, ordinal, title))

    store_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(store_dir))
    # Rebuild rather than merge: a re-index after an edit must not leave the
    # previous version of a paragraph searchable alongside the new one.
    try:
        client.delete_collection(collection)
    except Exception:  # noqa: BLE001 - absent collection is the normal first run
        pass

    col = client.create_collection(
        collection,
        embedding_function=LocalEmbedding(),
        metadata={"hnsw:space": "cosine"},
    )

    ids, documents, metadatas = [], [], []
    seen: dict[str, int] = {}
    for source, heading, text, ordinal, title in chunks:
        digest = hashlib.blake2b(f"{source}|{ordinal}|{text}".encode(), digest_size=8).hexdigest()
        # Identical paragraphs in different files must not collapse into one id.
        count = seen.get(digest, 0)
        seen[digest] = count + 1
        chunk_id = f"{digest}-{count}"
        ids.append(chunk_id)
        documents.append(text)
        metadatas.append({"source": source, "heading": heading, "ordinal": ordinal, "title": title})

    # Batched so a large folder does not build one huge request.
    for start in range(0, len(ids), 256):
        end = start + 256
        col.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    summary = {
        "files": len(files),
        "chunks": len(ids),
        "store": str(store_dir),
        "collection": collection,
    }
    log(f"Indexed {summary['chunks']} chunks from {summary['files']} files into {store_dir}")
    return summary


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


class RagIndex:
    """BM25 ranking over the chunks stored in Chroma.

    The index is loaded once and kept in memory: reading from Chroma on each
    query would add file I/O to every tool call, and BM25 needs the term
    frequencies anyway.
    """

    def __init__(self, chunks: list[Chunk], *, k1: float = BM25_K1, b: float = BM25_B) -> None:
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._tokens: list[list[str]] = [tokenize(c.text + " " + c.heading) for c in chunks]
        # Title tokens are tracked separately: they are a strong identity signal
        # ("is the question about this product?") and should not be drowned out
        # by the body text, which in a guide-style document mentions the same
        # words dozens of times.
        self._title_tokens: list[set[str]] = [set(tokenize(c.title)) for c in chunks]
        self._lengths = [len(t) for t in self._tokens]
        self._avg_len = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0

        # term -> {chunk index: frequency}
        self._postings: dict[str, dict[int, int]] = {}
        for index, tokens in enumerate(self._tokens):
            for token in tokens:
                bucket = self._postings.setdefault(token, {})
                bucket[index] = bucket.get(index, 0) + 1

        self._idf = {
            term: math.log(1 + (len(chunks) - len(postings) + 0.5) / (len(postings) + 0.5))
            for term, postings in self._postings.items()
        }

    def __len__(self) -> int:
        return len(self._chunks)

    @classmethod
    def load(cls, store_dir: Path, *, collection: str = COLLECTION_NAME) -> "RagIndex":
        """Read every chunk back out of Chroma."""
        import chromadb

        if not store_dir.exists():
            raise FileNotFoundError(
                f"No index at {store_dir}. Build it first: python scripts/build_rag_index.py"
            )
        client = chromadb.PersistentClient(path=str(store_dir))
        try:
            col = client.get_collection(collection, embedding_function=LocalEmbedding())
        except Exception as exc:  # noqa: BLE001 - surface a readable message
            raise FileNotFoundError(
                f"Collection {collection!r} not found in {store_dir}. "
                "Build it with: python scripts/build_rag_index.py"
            ) from exc

        raw = col.get(include=["documents", "metadatas"])
        chunks = [
            Chunk(
                id=chunk_id,
                text=document or "",
                source=(meta or {}).get("source", "?"),
                heading=(meta or {}).get("heading", ""),
                ordinal=int((meta or {}).get("ordinal", 0)),
                title=(meta or {}).get("title", ""),
            )
            for chunk_id, document, meta in zip(raw["ids"], raw["documents"], raw["metadatas"])
        ]
        return cls(chunks)

    def search(self, query: str, top_k: int = DEFAULT_TOP_K, *, min_score: float = 0.0) -> list[Hit]:
        """Rank chunks for ``query`` with BM25."""
        terms = tokenize(query)
        if not terms or not self._chunks:
            return []

        scores = [0.0] * len(self._chunks)
        for term in set(terms):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf[term]
            for index, frequency in postings.items():
                length = self._lengths[index] or 1
                denominator = frequency + self._k1 * (1 - self._b + self._b * length / self._avg_len)
                scores[index] += idf * (frequency * (self._k1 + 1)) / denominator

        # A question that names the product must prefer that product's own
        # page. Without this, "قهوه‌ساز A1 قیمتش چنده؟" ranked a sales-training
        # note above the price page, because the note happens to quote the
        # phrase "قیمتش چنده؟" while the price page says "قیمت:".
        query_terms = set(terms)
        for index, scored in enumerate(scores):
            if not scored:
                continue
            title_overlap = len(query_terms & self._title_tokens[index])
            if title_overlap:
                scores[index] = scored * (1 + TITLE_BOOST * title_overlap)

        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits = [
            Hit(self._chunks[i], scores[i])
            for i in ranked[: top_k * 3]
            if scores[i] > min_score
        ]
        return hits[:top_k]


def format_hits(hits: list[Hit]) -> str:
    """Render hits for the model: numbered, with source, capped in length."""
    return "\n\n".join(hit.chunk.as_prompt_block(i + 1) for i, hit in enumerate(hits))


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def rag_config(root: Path) -> dict | None:
    """Settings from the environment, or ``None`` when RAG is switched off."""
    if not _flag("RAG_ENABLED", False):
        return None
    docs_dir = resolve_path(root, os.getenv("RAG_DOCS_DIR", "knowledge"))
    store_dir = resolve_path(root, os.getenv("RAG_STORE_DIR", ".rag/chroma"))
    try:
        top_k = int(os.getenv("RAG_TOP_K", str(DEFAULT_TOP_K)))
    except ValueError:
        top_k = DEFAULT_TOP_K
    try:
        max_chars = int(os.getenv("RAG_CHUNK_CHARS", str(DEFAULT_CHUNK_CHARS)))
    except ValueError:
        max_chars = DEFAULT_CHUNK_CHARS
    return {
        "docs_dir": docs_dir,
        "store_dir": store_dir,
        "collection": os.getenv("RAG_COLLECTION", COLLECTION_NAME),
        "top_k": max(1, top_k),
        "max_chars": max(200, max_chars),
    }


def describe_config(config: dict) -> str:
    """One startup line saying exactly what will be searched."""
    return (
        f"RAG: {config['docs_dir']} › {config['store_dir']} "
        f"(top_k={config['top_k']}, ranker=BM25, storage=chroma)"
    )


def write_manifest(store_dir: Path, summary: dict) -> None:
    """Persist a small manifest so the CLI can report index freshness."""
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def read_manifest(store_dir: Path) -> dict | None:
    path = store_dir / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
