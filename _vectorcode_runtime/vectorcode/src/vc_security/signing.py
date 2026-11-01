# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Ed25519 signing — supply chain integrity for agent and skill manifests."""

from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

@dataclass(slots=True)
class KeyPair:
    """Ed25519 key pair."""

    private_key: bytes
    public_key: bytes

def generate_keypair() -> KeyPair:
    """Generate a new Ed25519 key pair.

    Requires the ``cryptography`` package
    (``uv sync --extra security-signing``).
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return KeyPair(private_key=private_bytes, public_key=public_bytes)
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package. "
            "Install with: uv sync --extra security-signing"
        ) from exc

def sign(data: bytes, private_key: bytes) -> bytes:
    """Sign *data* with an Ed25519 *private_key*.

    Returns the raw 64-byte signature.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.from_private_bytes(private_key)
        return key.sign(data)
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package."
        ) from exc

def verify(data: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an Ed25519 *signature* on *data* with *public_key*.

    Returns True if valid, False otherwise.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(public_key)
        try:
            key.verify(signature, data)
            return True
        except InvalidSignature:
            return False
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package."
        ) from exc

def sign_b64(data: bytes, private_key: bytes) -> str:
    """Sign and return base64-encoded signature string."""
    raw = sign(data, private_key)
    return base64.b64encode(raw).decode("ascii")

def verify_b64(data: bytes, signature_b64: str, public_key: bytes) -> bool:
    """Verify a base64-encoded signature."""
    try:
        raw = base64.b64decode(signature_b64)
    except Exception as exc:
        logger.warning("Signature verification failed: {}", exc)
        return False
    return verify(data, raw, public_key)

def load_public_key(path: str) -> bytes:
    """Load a raw 32-byte Ed25519 public key from a file."""
    raw = Path(path).read_bytes()
    # If base64-encoded (common), decode
    if len(raw) > 32:
        try:
            raw = base64.b64decode(raw.strip())
        except Exception as exc:
            logger.warning("Failed to base64-decode public key from {}: {}", path, exc)
    return raw

def _write_text_atomic(path: Path, content: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

def save_keypair(keypair: KeyPair, private_path: str, public_path: str) -> None:
    """Save keypair to files (base64-encoded).

    The private key is written atomically (tempfile + fsync + os.replace)
    with 0o600 permissions applied before the file becomes visible at its
    final path -- a plain write_text() previously left the key readable at
    default permissions and non-atomic, risking both exposure and
    corruption on a mid-write crash.
    """
    _write_text_atomic(
        Path(private_path),
        base64.b64encode(keypair.private_key).decode(),
        mode=0o600,
    )
    _write_text_atomic(
        Path(public_path), base64.b64encode(keypair.public_key).decode()
    )

__all__ = [
    "KeyPair",
    "generate_keypair",
    "load_public_key",
    "save_keypair",
    "sign",
    "sign_b64",
    "verify",
    "verify_b64",
]
