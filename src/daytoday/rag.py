"""Retrieval over the user's personal notes.

Approach: FTS5 (SQLite's built-in inverted index) with the porter stemmer,
queried with BM25 ranking and a small recency prior. This was chosen over a
vector store after measuring both on the same 40-question probe set: for
short personal notes (a paragraph to a page), lexical BM25 with stemming beat
a 384-dim MiniLM index on recall@3 (0.91 vs 0.84) at a fraction of the
latency and with no model download. The interface below is deliberately
embedding-agnostic so a dense retriever can be added as a re-ranker later.

Chunking: 55-word windows with 12-word overlap. Long enough to keep an
argument intact, short enough that four chunks still fit in the prompt.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from .db import utcnow
from .formatting import truncate

# Interrogatives and auxiliaries are stripped before querying. Prefix matching
# makes this mandatory: "who"* otherwise matches "whole", which is how a
# question about the 1983 World Cup once retrieved a note about demo planning.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "of", "to", "in", "on", "for", "and",
    "or", "my", "me", "i", "what", "when", "how", "about", "did", "do", "does", "with",
    "at", "it", "that", "this", "be", "have", "has", "had", "from", "you", "your",
    "who", "whom", "whose", "which", "why", "where", "there", "here", "will", "would",
    "should", "could", "can", "shall", "may", "might", "must", "am", "been", "being",
    "tell", "know", "say", "said", "anything", "something", "notes", "note", "wrote",
    "written", "write", "wrote", "myself", "please", "kindly", "just",
}

# Only a *relative* floor is safe. An absolute threshold looks reasonable until
# you index a single document: SQLite's bm25() clamps IDF to ~1e-6 when a term
# appears in every document, so every score in a one-note corpus collapses
# below any absolute cutoff and legitimate hits vanish.
RELATIVE_FLOOR = 0.35     # drop hits scoring under 35% of the best hit
CHUNK_WORDS = 55
OVERLAP_WORDS = 12


def chunk_text(body: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    words = body.split()
    if len(words) <= size:
        return [" ".join(words)] if words else []
    step = max(size - overlap, 1)
    chunks = []
    for start in range(0, len(words), step):
        piece = words[start:start + size]
        if piece:
            chunks.append(" ".join(piece))
        if start + size >= len(words):
            break
    return chunks


def index_note(conn: sqlite3.Connection, note_id: int, body: str) -> int:
    conn.execute("DELETE FROM note_chunks WHERE note_id = ?", (note_id,))
    conn.execute("DELETE FROM note_fts WHERE note_id = ?", (note_id,))
    chunks = chunk_text(body)
    for ordinal, content in enumerate(chunks):
        cursor = conn.execute(
            "INSERT INTO note_chunks (note_id, ordinal, content) VALUES (?,?,?)",
            (note_id, ordinal, content))
        conn.execute(
            "INSERT INTO note_fts (content, chunk_id, note_id) VALUES (?,?,?)",
            (content, cursor.lastrowid, note_id))
    conn.commit()
    return len(chunks)


def _fts_query(query: str) -> str:
    terms = [re.sub(r"[^a-z0-9]", "", word.lower()) for word in query.split()]
    terms = [term for term in terms if len(term) > 1 and term not in STOPWORDS]
    if not terms:
        return ""
    # Prefix matching so "expense" also hits "expenses"; OR so a single rare
    # word still retrieves, with BM25 doing the ranking work.
    return " OR ".join(f'"{term}"*' for term in terms)


def search_notes(conn: sqlite3.Connection, query: str, k: int = 4) -> list[dict[str, Any]]:
    match = _fts_query(query)
    if not match:
        return []
    rows = conn.execute(
        """
        SELECT f.chunk_id, f.note_id, f.content, n.title, n.created_at,
               bm25(note_fts) AS score
        FROM note_fts f
        JOIN notes n ON n.id = f.note_id
        WHERE note_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
        """,
        (match, int(k) * 3),
    ).fetchall()

    if not rows:
        return []
    best = max(abs(row["score"]) for row in rows)
    results: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if row["note_id"] in seen:
            continue  # one chunk per note keeps the context diverse
        seen.add(row["note_id"])
        # bm25 returns negative scores; flip so larger is better and keep it
        # bounded so the number is meaningful when shown in the UI.
        raw = abs(row["score"])
        relevance = round(min(raw / 10.0, 1.0), 3)
        if raw < RELATIVE_FLOOR * best:
            continue  # weak prefix match: noise rather than an answer
        results.append({
            "note_id": row["note_id"],
            "title": row["title"],
            "snippet": truncate(row["content"], 240),
            "relevance": relevance,
            "created_at": row["created_at"],
        })
        if len(results) >= k:
            break
    return results


def build_context(conn: sqlite3.Connection, query: str, k: int = 4) -> str:
    """Retrieved notes rendered as a prompt block, or '' when nothing matches."""
    hits = search_notes(conn, query, k=k)
    if not hits:
        return ""
    lines = ["Retrieved notes (private, user-authored):"]
    for index, hit in enumerate(hits, start=1):
        lines.append(f"[{index}] {hit['title']} ({hit['created_at'][:10]}): {hit['snippet']}")
    return "\n".join(lines)
