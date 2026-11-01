"""Authenticated encryption for sensitive trading-analysis files."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MAGIC = b"VECTOR-TRADING-AESGCM-v1\x00"
_NONCE_SIZE = 12


def _get_shared_key() -> str:
    """Resolve VECTOR's shared at-rest encryption secret, failing closed."""
    from core.memory.episodic import _get_db_key

    key = _get_db_key()
    if not key:
        raise RuntimeError("[VECTOR][trading_storage] encryption key unavailable")
    return key


def _aes_key() -> bytes:
    return hashlib.sha256(_get_shared_key().encode("utf-8")).digest()


def _backup_plaintext(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    backup = Path(f"{path}.plaintext.bak.{stamp}")
    shutil.copy2(path, backup)
    return backup


def encrypt_text(text: str) -> bytes:
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(_aes_key()).encrypt(nonce, text.encode("utf-8"), _MAGIC)
    return _MAGIC + nonce + ciphertext


def decrypt_text(payload: bytes) -> str:
    if not payload.startswith(_MAGIC):
        raise ValueError("trading file is not an encrypted VECTOR payload")
    offset = len(_MAGIC)
    if len(payload) < offset + _NONCE_SIZE + 16:
        raise ValueError("trading file ciphertext is truncated")
    nonce = payload[offset : offset + _NONCE_SIZE]
    ciphertext = payload[offset + _NONCE_SIZE :]
    return AESGCM(_aes_key()).decrypt(nonce, ciphertext, _MAGIC).decode("utf-8")


def read_encrypted_text(path: str | Path) -> str:
    """Decrypt a file, or read a legacy plaintext file after key validation."""
    file_path = Path(path)
    payload = file_path.read_bytes()
    if payload.startswith(_MAGIC):
        text = decrypt_text(payload)
        return text.replace("\r\n", "\n").replace("\r", "\n")
    _get_shared_key()
    return payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def atomic_write_encrypted_text(path: str | Path, text: str) -> None:
    """Atomically write ciphertext, preserving legacy plaintext once."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = encrypt_text(text)
    if file_path.exists() and not file_path.read_bytes().startswith(_MAGIC):
        _backup_plaintext(file_path)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, file_path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sample = encrypt_text("VECTOR trading storage self-test")
    assert decrypt_text(sample) == "VECTOR trading storage self-test"
