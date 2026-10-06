"""Regression test: FAISSMemory.store() and ColBERTMemory.store() must copy
the caller's metadata dict instead of keeping a live reference -- otherwise
a caller mutating that dict after the call silently corrupts the already-
"stored" record.

Both backends require heavy optional dependencies (faiss-cpu, colbert-ai +
torch) that are not installed in every environment; these tests skip
gracefully when the dependency is absent rather than failing the suite.
"""

from __future__ import annotations

import pytest


def test_faiss_memory_store_copies_metadata() -> None:
    pytest.importorskip("faiss")
    from vectorcode.src.vc_tools.storage.faiss_backend import FAISSMemory
    from vectorcode.src.vc_tools.storage.embeddings import Embedder
    import numpy as np

    class _TinyEmbedder(Embedder):
        def embed(self, texts):
            return np.ones((len(texts), 4), dtype=np.float32)

        def dim(self) -> int:
            return 4

    backend = FAISSMemory(embedder=_TinyEmbedder())
    caller_metadata = {"tag": "original"}
    doc_id = backend.store("hello world", metadata=caller_metadata)

    caller_metadata["tag"] = "mutated after store"

    stored_content, stored_source, stored_meta = backend._documents[doc_id]
    assert stored_meta["tag"] == "original"


def test_colbert_memory_store_copies_metadata() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("colbert")
    from vectorcode.src.vc_tools.storage.colbert_backend import ColBERTMemory

    backend = ColBERTMemory()
    # Avoid loading a real ColBERT checkpoint -- only exercising store()'s
    # metadata handling, not the (heavy, network-dependent) encoding path.
    backend._encode = lambda text: "fake-embedding"

    caller_metadata = {"tag": "original"}
    doc_id = backend.store("hello world", metadata=caller_metadata)

    caller_metadata["tag"] = "mutated after store"

    _, _, stored_meta = backend._documents[doc_id]
    assert stored_meta["tag"] == "original"
