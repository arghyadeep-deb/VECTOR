"""Regression test: chunk_text() must not silently drop a whole short document.

chunk_text()'s final "flush remaining tokens" step only appended the leftover
chunk if it met ChunkConfig.min_chunk_size (default 50 whitespace tokens).
That filter makes sense for a noisy leftover fragment when earlier sibling
chunks already captured the bulk of a long document -- but when nothing has
been chunked yet (a short document under the threshold), the leftover IS the
entire document, and the old code silently returned an empty chunk list,
meaning the document was never stored anywhere with no error or warning.
"""

from __future__ import annotations

from vectorcode.src.vc_tools.storage.chunking import Chunk, ChunkConfig, chunk_text


def test_short_document_still_produces_a_chunk() -> None:
    text = "hello world, this is a normal short document."

    chunks = chunk_text(text, source="notes.txt")

    assert len(chunks) == 1
    assert chunks[0].content == text


def test_short_document_below_min_chunk_size_default() -> None:
    cfg = ChunkConfig()
    text = "short note"
    assert len(text.split()) < cfg.min_chunk_size

    chunks = chunk_text(text, source="note.txt", config=cfg)

    assert len(chunks) == 1
    assert chunks[0].content == text


def test_noisy_leftover_after_a_real_chunk_is_still_filtered() -> None:
    # A long first paragraph that fills a full chunk, then a tiny leftover
    # paragraph -- the tiny leftover should still be dropped as noise,
    # since a real chunk was already produced.
    cfg = ChunkConfig(chunk_size=20, chunk_overlap=0, min_chunk_size=10)
    long_para = " ".join(f"word{i}" for i in range(25))
    text = f"{long_para}\n\ntiny"

    chunks = chunk_text(text, source="doc.txt", config=cfg)

    assert len(chunks) >= 1
    assert all("tiny" != c.content for c in chunks)


def test_empty_text_still_returns_no_chunks() -> None:
    assert chunk_text("", source="x") == []
    assert chunk_text("   \n\n  ", source="x") == []
