"""Regression test: ingest_path() must skip sensitive files for a single-file
path, not just during a directory walk.

ingest_path()'s directory-walk branch already calls is_sensitive_file() on
every child and skips matches (secrets, credentials, private keys). The
single-file branch (``path.is_file()``) read and chunked the file directly
with no sensitive-file check at all, so calling ingest_path() (or the
memory_index tool built on it) with a path pointing straight at a ``.env``
file, an SSH private key, etc. would persist its contents into the vector
memory store forever.
"""

from __future__ import annotations

from pathlib import Path

from vectorcode.src.vc_tools.storage.ingest import ingest_path


def test_ingest_path_skips_sensitive_single_file(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("API_KEY=super-secret-value\n", encoding="utf-8")

    chunks = ingest_path(secret)

    assert chunks == []


def test_ingest_path_skips_sensitive_private_key(tmp_path: Path) -> None:
    key = tmp_path / "id_rsa"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n", encoding="utf-8")

    chunks = ingest_path(key)

    assert chunks == []


def test_ingest_path_still_ingests_normal_single_file(tmp_path: Path) -> None:
    doc = tmp_path / "notes.txt"
    doc.write_text("hello world, this is a normal document.\n", encoding="utf-8")

    chunks = ingest_path(doc)

    assert len(chunks) >= 1
    assert "hello world" in chunks[0].content
