from __future__ import annotations

import hashlib

import httpx
import pytest

from core.sensing import mediapipe_tasks as models


class _Response:
    def __init__(self, body: bytes, content_length: int | None = None):
        self._body = body
        self.headers = {} if content_length is None else {"content-length": str(content_length)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield from (self._body[:7], self._body[7:])


def test_model_download_is_hash_verified_and_repairs_a_corrupt_cache(monkeypatch, tmp_path):
    body = b"verified model bytes"
    expected = hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(models, "model_dir", lambda: tmp_path)
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Response(body))
    path = models.ensure_model("model.task", "https://models.example/model", min_bytes=5, max_bytes=100,
                               expected_sha256=expected)
    assert path.read_bytes() == body
    path.write_bytes(b"tampered")
    assert models.ensure_model("model.task", "https://models.example/model", min_bytes=5, max_bytes=100,
                               expected_sha256=expected).read_bytes() == body


def test_model_download_rejects_bad_hash_and_oversize_content(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "model_dir", lambda: tmp_path)
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Response(b"wrong bytes"))
    with pytest.raises(models.ModelUnavailable, match="SHA-256"):
        models.ensure_model("bad.task", "https://models.example/bad", min_bytes=2, max_bytes=100,
                            expected_sha256=hashlib.sha256(b"expected").hexdigest())
    assert not (tmp_path / "bad.task.part").exists()

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Response(b"x", content_length=101))
    with pytest.raises(models.ModelUnavailable, match="exceeds"):
        models.ensure_model("large.task", "https://models.example/large", min_bytes=1, max_bytes=100)
    assert not (tmp_path / "large.task.part").exists()
