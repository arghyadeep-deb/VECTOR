"""Regression for vectorcode/src/connectors/pipeline.py:

IngestionPipeline.ingest() stored chunks for a document one at a time via
KnowledgeStore.store(), which generates a fresh UUID chunk id on every call
(no uniqueness constraint tying it to doc_id/chunk_index/content). If
storing chunk N of a multi-chunk document raised (a transient DB error),
chunks 1..N-1 were already committed, but doc.doc_id was never added to
self._seen_doc_ids (that happens after the whole per-document block). A
caller that retries the same document after the transient error clears
re-ingests it from scratch, duplicating the chunks that succeeded the
first time -- the store ends up with 2x rows for part of the document and
no way to tell.

Fixed: the whole per-document store (main chunks + attachment chunks) is
wrapped in try/except; on failure it rolls back via store.delete(doc_id)
before re-raising. This is always safe because a doc_id reaching that code
path is guaranteed to have no prior chunks (already-seen doc_ids are
skipped at the top of the loop).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from vectorcode.src.connectors._abc import Document
from vectorcode.src.connectors.pipeline import IngestionPipeline
from vectorcode.src.connectors.store import KnowledgeStore


def _make_long_document(doc_id: str) -> Document:
    # A long "message" doc_type body guarantees the chunker splits it into
    # multiple chunks (accumulate() flushes once max_tokens is exceeded).
    paragraph = "token " * 50
    content = "\n\n".join([paragraph] * 5)
    return Document(
        doc_id=doc_id,
        source="test",
        doc_type="message",
        content=content,
        title="Long doc",
    )


def test_partial_store_failure_rolls_back_already_stored_chunks(tmp_path):
    store = KnowledgeStore(db_path=str(tmp_path / "kb.db"))
    pipeline = IngestionPipeline(store, max_tokens=20)
    doc = _make_long_document("doc-1")

    real_store = store.store
    calls = {"n": 0}

    def _flaky_store(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3_error()
        return real_store(*args, **kwargs)

    def sqlite3_error():
        import sqlite3

        return sqlite3.OperationalError("database is locked")

    with patch.object(store, "store", side_effect=_flaky_store):
        with pytest.raises(Exception):
            pipeline.ingest(iter([doc]))

    # No partial rows should remain for doc-1 after the rollback.
    remaining = store._conn.execute(
        "SELECT COUNT(*) FROM knowledge_chunks WHERE doc_id = ?", ("doc-1",)
    ).fetchone()[0]
    assert remaining == 0

    # And it must not have been marked "seen" either, so a retry can
    # actually re-ingest it (this is implicitly covered by the row count
    # check, but assert directly for clarity).
    assert "doc-1" not in pipeline._seen_doc_ids

    store.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
