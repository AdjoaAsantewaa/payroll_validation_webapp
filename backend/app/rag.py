"""Genuine retrieval-augmented generation over the markdown knowledge base in
backend/knowledge/ -- not a hardcoded FAQ lookup.

Pipeline: load documents -> chunk by heading -> index with BM25 (pure
Python, no vector DB, no embeddings API call, no new dependency) -> rank
chunks against a query -> return the top-k for the assistant to ground its
answer in.

Why BM25 instead of embeddings: the knowledge base is a few thousand words
across ten short documents. An embeddings-based vector store would add a
paid API call (or a heavy local model) and infrastructure for a corpus this
small buys nothing in retrieval quality. BM25 is the standard lexical-
retrieval baseline precisely because it performs genuine ranked retrieval
(term frequency, inverse document frequency, length normalisation) without
any of that -- and it is fully inspectable: every score in this file can be
recomputed by hand.

This module never touches application data (submissions, employees,
exceptions). Structured, per-user context is assembled separately in
assistant_service.py, directly from the database -- see that module's
docstring for why the two are kept apart.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "and", "or", "in", "on", "at", "for", "with", "as", "by",
    "this", "that", "these", "those", "it", "its", "if", "not", "no",
    "do", "does", "did", "has", "have", "had", "will", "would", "can",
    "may", "must", "should", "their", "they", "them", "your", "you",
}

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")

# BM25 parameters -- standard defaults (Robertson/Sparck-Jones).
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


@dataclass
class Chunk:
    doc_id: str          # filename without extension, e.g. "05_exited_employee_guidance"
    doc_title: str       # the document's H1, e.g. "Exited Employee Guidance"
    heading: str         # the chunk's H2, e.g. "What triggers this issue"
    text: str            # the chunk's body text
    tokens: list[str] = field(default_factory=list, repr=False)


def _chunk_markdown(path: str) -> list[Chunk]:
    doc_id = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    doc_title = doc_id
    if lines and lines[0].startswith("# "):
        doc_title = lines[0][2:].strip()
        lines = lines[1:]

    chunks: list[Chunk] = []
    heading = "Overview"
    buf: list[str] = []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            chunks.append(Chunk(doc_id=doc_id, doc_title=doc_title, heading=heading, text=text))

    for line in lines:
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    flush()
    return chunks


class _Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        for c in self.chunks:
            c.tokens = _tokenize(f"{c.doc_title} {c.heading} {c.text}")
        self.lengths = [len(c.tokens) for c in self.chunks]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.chunks else 0.0
        self.n_docs = len(self.chunks)

        self.doc_freq: Counter[str] = Counter()
        for c in self.chunks:
            for term in set(c.tokens):
                self.doc_freq[term] += 1

        self.idf: dict[str, float] = {
            term: math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)
            for term, df in self.doc_freq.items()
        }

    def score(self, query_tokens: list[str], chunk_idx: int) -> float:
        chunk = self.chunks[chunk_idx]
        freqs = Counter(chunk.tokens)
        length = self.lengths[chunk_idx]
        total = 0.0
        for term in query_tokens:
            if term not in freqs:
                continue
            idf = self.idf.get(term, 0.0)
            f = freqs[term]
            denom = f + _K1 * (1 - _B + _B * length / (self.avg_len or 1))
            total += idf * (f * (_K1 + 1)) / (denom or 1)
        return total

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        query_tokens = _tokenize(query)
        if not query_tokens or not self.chunks:
            return []
        scored = [(i, self.score(query_tokens, i)) for i in range(self.n_docs)]
        scored = [(i, s) for i, s in scored if s > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [(self.chunks[i], s) for i, s in scored[:k]]


def _build_index() -> _Index:
    chunks: list[Chunk] = []
    if os.path.isdir(KNOWLEDGE_DIR):
        for name in sorted(os.listdir(KNOWLEDGE_DIR)):
            if name.endswith(".md"):
                chunks.extend(_chunk_markdown(os.path.join(KNOWLEDGE_DIR, name)))
    return _Index(chunks)


_index = _build_index()


def reload_index() -> None:
    """Re-reads the knowledge base from disk. Not called in normal request
    handling (the index is small and loaded once at import time) -- exposed
    for tests that want to confirm the index reflects the files on disk."""
    global _index
    _index = _build_index()


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Returns up to k chunks ranked by BM25 relevance to `query`, each as
    {"doc_id", "doc_title", "heading", "text", "score"}. Empty list if the
    query has no recognised terms or the knowledge base is empty -- callers
    must treat that as "nothing relevant was found", not an error."""
    results = _index.search(query, k=k)
    return [
        {
            "doc_id": c.doc_id,
            "doc_title": c.doc_title,
            "heading": c.heading,
            "text": c.text,
            "score": round(score, 4),
        }
        for c, score in results
    ]


def chunk_count() -> int:
    return _index.n_docs
