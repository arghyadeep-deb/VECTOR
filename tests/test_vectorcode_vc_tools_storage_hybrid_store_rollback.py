"""Regression test: HybridMemory.store() must roll back the sparse write if
the dense write fails, so a failed dual-write doesn't leave content silently
retrievable from only one half of the index while the caller's store() call
raised and reported overall failure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from vectorcode.src.vc_tools.storage._abc import MemoryBackend, RetrievalResult
from vectorcode.src.vc_tools.storage.hybrid import HybridMemory


class _FakeSparseBackend(MemoryBackend):
    backend_id = "fake_sparse"

    def __init__(self) -> None:
        self.docs: Dict[str, str] = {}
        self._next_id = 0

    def store(self, content, *, source="", metadata=None) -> str:
        doc_id = f"sparse-{self._next_id}"
        self._next_id += 1
        self.docs[doc_id] = content
        return doc_id

    def retrieve(self, query, *, top_k=5, **kwargs) -> List[RetrievalResult]:
        return [RetrievalResult(content=c, score=1.0) for c in self.docs.values()]

    def delete(self, doc_id: str) -> bool:
        return self.docs.pop(doc_id, None) is not None

    def clear(self) -> None:
        self.docs.clear()


class _AlwaysFailingDenseBackend(MemoryBackend):
    backend_id = "fake_dense_fail"

    def store(self, content, *, source="", metadata=None) -> str:
        raise RuntimeError("dense backend unavailable")

    def retrieve(self, query, *, top_k=5, **kwargs) -> List[RetrievalResult]:
        return []

    def delete(self, doc_id: str) -> bool:
        return False

    def clear(self) -> None:
        pass


def test_failed_dense_store_rolls_back_sparse_write() -> None:
    sparse = _FakeSparseBackend()
    dense = _AlwaysFailingDenseBackend()
    hybrid = HybridMemory(sparse=sparse, dense=dense)

    try:
        hybrid.store("some content")
        assert False, "expected the dense store failure to propagate"
    except RuntimeError:
        pass

    assert sparse.docs == {}, "sparse write must be rolled back on dense failure"
