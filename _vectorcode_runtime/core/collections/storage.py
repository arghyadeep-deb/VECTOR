"""Pluggable file storage for the VECTOR collections engine.

Python reimplementation of PocketBase's filesystem abstraction (tools/filesystem/,
core/field_file.go): one interface, two drivers (local disk + S3), optional image
thumbnails, path-traversal-safe keys, and per-object metadata. boto3 and Pillow are
optional — the layer degrades gracefully (local always works; S3/thumbnails skipped
with a clear log line if the dep is missing).
"""

from __future__ import annotations

import sys

__all__ = [
    "StorageError",
    "StorageDriver",
    "LocalDriver",
    "S3Driver",
    "FileStorage",
    "safe_key",
]

from pathlib import Path

import io
import json
import mimetypes
import os
import re
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from loguru import logger
from core.config import CONFIG

_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


class StorageError(Exception):
    pass


def safe_key(key: str) -> str:
    """Normalize an object key to a safe relative POSIX path.

    Rejects path traversal, absolute paths, drive letters and backslashes. The result
    can be safely joined under a storage root without escaping it.
    """
    if key is None or not str(key).strip():
        raise StorageError("empty storage key")
    k = str(key).replace("\\", "/").strip()
    if k.startswith("/") or _DRIVE_RE.match(k):
        raise StorageError(f"absolute storage key not allowed: {key!r}")
    parts = []
    for seg in k.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise StorageError(f"path traversal not allowed: {key!r}")
        parts.append(seg)
    if not parts:
        raise StorageError(f"invalid storage key: {key!r}")
    return "/".join(parts)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guess_type(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


class StorageDriver(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str | None = None) -> dict: ...
    @abstractmethod
    def get(self, key: str) -> bytes: ...
    @abstractmethod
    def delete(self, key: str) -> bool: ...
    @abstractmethod
    def exists(self, key: str) -> bool: ...
    @abstractmethod
    def list(self, prefix: str = "") -> list[str]: ...
    @abstractmethod
    def url(self, key: str) -> str: ...


class LocalDriver(StorageDriver):
    """Stores objects on local disk under `root`, with a `.meta.json` sidecar per object."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / safe_key(key)).resolve()
        # Defense in depth: ensure the resolved path is still under root.
        if self.root not in p.parents and p != self.root:
            raise StorageError(f"resolved path escapes storage root: {key!r}")
        return p

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        """Write `data` to `path` via tempfile+fsync+os.replace so a crash mid-write
        (OOM, process kill, power loss) can never leave a truncated file at `path`
        that exists()/get() would still report and serve as complete."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def put(self, key: str, data: bytes, content_type: str | None = None) -> dict:
        p = self._path(key)
        self._atomic_write(p, data)
        meta = {
            "key": safe_key(key),
            "size": len(data),
            "content_type": content_type or _guess_type(key),
            "created": _now(),
        }
        self._atomic_write(p.with_suffix(p.suffix + ".meta.json"), json.dumps(meta).encode("utf-8"))
        logger.debug(f"[VECTOR][storage] put local {meta['key']} ({meta['size']}B)")
        return meta

    def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.is_file():
            raise StorageError(f"not found: {key!r}")
        return p.read_bytes()

    def metadata(self, key: str) -> dict:
        p = self._path(key)
        sidecar = p.with_suffix(p.suffix + ".meta.json")
        if sidecar.is_file():
            return json.loads(sidecar.read_text(encoding="utf-8"))
        if p.is_file():
            return {"key": safe_key(key), "size": p.stat().st_size,
                    "content_type": _guess_type(key), "created": None}
        raise StorageError(f"not found: {key!r}")

    def delete(self, key: str) -> bool:
        p = self._path(key)
        existed = p.is_file()
        if existed:
            p.unlink()
        sidecar = p.with_suffix(p.suffix + ".meta.json")
        if sidecar.is_file():
            sidecar.unlink()
        return existed

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        out = []
        for p in self.root.rglob("*"):
            if p.is_file() and not p.name.endswith(".meta.json"):
                rel = p.relative_to(self.root).as_posix()
                if rel.startswith(prefix):
                    out.append(rel)
        return sorted(out)

    def url(self, key: str) -> str:
        return f"/api/files/{safe_key(key)}"


class S3Driver(StorageDriver):
    """S3-compatible object storage. Requires boto3 (optional dependency)."""

    def __init__(self, bucket: str, *, region: str | None = None,
                 endpoint_url: str | None = None, access_key: str | None = None,
                 secret_key: str | None = None, public_base: str | None = None):
        try:
            import boto3  # noqa
        except ImportError as e:
            raise StorageError(
                "S3 backend requires boto3 — `pip install boto3` or use the local driver"
            ) from e
        self.bucket = bucket
        self.public_base = public_base
        self._client = boto3.client(
            "s3", region_name=region, endpoint_url=endpoint_url,
            aws_access_key_id=access_key or None, aws_secret_access_key=secret_key or None,
        )

    def put(self, key: str, data: bytes, content_type: str | None = None) -> dict:
        k = safe_key(key)
        self._client.put_object(Bucket=self.bucket, Key=k, Body=data,
                                ContentType=content_type or _guess_type(key))
        return {"key": k, "size": len(data),
                "content_type": content_type or _guess_type(key), "created": _now()}

    def get(self, key: str) -> bytes:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=safe_key(key))
            return obj["Body"].read()
        except Exception as e:
            raise StorageError(f"S3 get failed for {key!r}: {e}") from e

    def delete(self, key: str) -> bool:
        self._client.delete_object(Bucket=self.bucket, Key=safe_key(key))
        return True

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=safe_key(key))
            return True
        except Exception:
            return False

    def list(self, prefix: str = "") -> list[str]:
        resp = self._client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return sorted(o["Key"] for o in resp.get("Contents", []))

    def url(self, key: str) -> str:
        k = safe_key(key)
        if self.public_base:
            return f"{self.public_base.rstrip('/')}/{k}"
        return f"s3://{self.bucket}/{k}"


class FileStorage:
    """Facade that selects a driver from CONFIG['collections']['storage'] and adds
    optional Pillow thumbnail generation on top of any driver."""

    def __init__(self, driver: StorageDriver | None = None):
        self.driver = driver or self._driver_from_config()

    @staticmethod
    def _driver_from_config() -> StorageDriver:
        cfg = (CONFIG.get("collections", {}) or {}).get("storage", {}) or {}
        backend = cfg.get("backend", "local")
        if backend == "s3":
            return S3Driver(
                bucket=cfg.get("s3_bucket", ""),
                region=cfg.get("s3_region"),
                endpoint_url=cfg.get("s3_endpoint") or None,
                access_key=cfg.get("s3_access_key") or None,
                secret_key=cfg.get("s3_secret_key") or None,
                public_base=cfg.get("s3_public_base") or None,
            )
        root = cfg.get("local_root") or str(Path(CONFIG["vector_home"]) / "collections_files")
        return LocalDriver(root)

    # delegate the core interface
    def put(self, key, data, content_type=None): return self.driver.put(key, data, content_type)
    def get(self, key): return self.driver.get(key)
    def delete(self, key): return self.driver.delete(key)
    def exists(self, key): return self.driver.exists(key)
    def list(self, prefix=""): return self.driver.list(prefix)
    def url(self, key): return self.driver.url(key)

    def thumbnail(self, key: str, width: int, height: int) -> bytes:
        """Return a resized image (JPEG/PNG preserved). Requires Pillow; raises
        StorageError if unavailable or the object is not an image."""
        try:
            from PIL import Image
        except ImportError as e:
            raise StorageError("thumbnails require Pillow — `pip install pillow`") from e
        raw = self.get(key)
        try:
            img = Image.open(io.BytesIO(raw))
            img.thumbnail((max(1, int(width)), max(1, int(height))))
            buf = io.BytesIO()
            fmt = img.format or "PNG"
            img.save(buf, format=fmt)
            return buf.getvalue()
        except Exception as e:
            raise StorageError(f"cannot thumbnail {key!r}: {e}") from e


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile
    ok = True

    root = tempfile.mkdtemp()
    fs = FileStorage(LocalDriver(root))

    meta = fs.put("docs/readme.txt", b"hello vector", content_type="text/plain")
    assert meta["size"] == 12 and meta["content_type"] == "text/plain"
    assert fs.get("docs/readme.txt") == b"hello vector"
    assert fs.exists("docs/readme.txt")
    assert "docs/readme.txt" in fs.list()
    assert fs.url("docs/readme.txt") == "/api/files/docs/readme.txt"
    assert fs.driver.metadata("docs/readme.txt")["size"] == 12
    assert fs.delete("docs/readme.txt") is True
    assert not fs.exists("docs/readme.txt")

    # path traversal / absolute / drive-letter keys rejected
    for bad in ("../escape", "/etc/passwd", "C:/windows", "a/../../b"):
        try:
            safe_key(bad); ok = False
        except StorageError:
            pass

    # nested safe key normalized
    assert safe_key("a//b/./c") == "a/b/c"

    # thumbnail path (skip cleanly if Pillow not installed)
    try:
        from PIL import Image  # noqa
        buf = io.BytesIO()
        Image.new("RGB", (200, 100), (255, 0, 0)).save(buf, format="PNG")
        fs.put("img/red.png", buf.getvalue(), content_type="image/png")
        thumb = fs.thumbnail("img/red.png", 50, 50)
        assert len(thumb) > 0
        w, h = Image.open(io.BytesIO(thumb)).size
        assert w <= 50 and h <= 50
        print("✅ storage.py OK (with thumbnails)" if ok else "❌ FAILED")
    except ImportError:
        print("✅ storage.py OK (Pillow absent — thumbnail path skipped)" if ok else "❌ FAILED")
