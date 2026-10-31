from __future__ import annotations

from daytoday import rag


def test_chunking_overlaps_and_covers():
    body = " ".join(f"w{i}" for i in range(200))
    chunks = rag.chunk_text(body, size=55, overlap=12)
    assert len(chunks) >= 4
    assert chunks[0].split()[0] == "w0"
    assert "w199" in chunks[-1]


def test_short_text_is_one_chunk():
    assert rag.chunk_text("a short note about dbms") == ["a short note about dbms"]


def test_stopword_only_query_returns_nothing(registry, conn):
    registry.execute("add_note", {"body": "Normalisation and BCNF notes for the exam"}, conn)
    assert rag.search_notes(conn, "what is the") == []


def test_search_finds_stemmed_term(registry, conn):
    registry.execute("add_note",
                     {"title": "DBMS", "body": "Functional dependency and normalisation to BCNF."}, conn)
    hits = rag.search_notes(conn, "normalization")
    assert hits and hits[0]["title"] == "DBMS"


def test_reindex_replaces_old_chunks(registry, conn):
    note = registry.execute("add_note", {"body": "original text about graphs"}, conn)
    rag.index_note(conn, note["note_id"], "replacement text about dynamic programming")
    count = conn.execute("SELECT COUNT(*) c FROM note_chunks WHERE note_id = ?",
                         (note["note_id"],)).fetchone()["c"]
    assert count == 1
    assert rag.search_notes(conn, "graphs") == []
