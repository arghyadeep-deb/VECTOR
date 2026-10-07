"""Regression for core/collections/storage.py LocalDriver.put():

put() used to write directly to the destination path (`p.write_bytes(data)`).
A crash mid-write (process kill, OOM, power loss) -- a real risk for the live
HTTP upload path at core/api/routers/collections.py:246 (`storage().put(key,
data, ...)`) -- left a truncated file at the real key. exists()/get() would
then report and serve that truncated file as a complete, valid object, with
no way for a caller to tell the upload didn't finish.

Fixed via tempfile+fsync+os.replace (same pattern already used by
vector_cli/vault_cmd.py and core/trading/agents/utils/memory.py this cycle):
a failure during the write never lands at the real path -- the destination
either doesn't exist yet, or still holds its old complete content.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.collections.storage import LocalDriver, StorageError


def test_put_failure_mid_write_leaves_no_partial_file():
    with tempfile.TemporaryDirectory() as root:
        driver = LocalDriver(root)

        with patch("os.fsync", side_effect=OSError("simulated crash mid-write")):
            with pytest.raises(OSError):
                driver.put("docs/readme.txt", b"hello vector")

        real_path = Path(root) / "docs" / "readme.txt"
        assert not real_path.exists(), (
            "a failed write must never leave a partial file at the real key"
        )
        # No stray .tmp files left behind inside the destination directory either.
        if real_path.parent.exists():
            leftovers = list(real_path.parent.glob("*.tmp"))
            assert leftovers == [], f"leaked temp file(s): {leftovers}"


def test_put_failure_mid_overwrite_preserves_old_content():
    with tempfile.TemporaryDirectory() as root:
        driver = LocalDriver(root)
        driver.put("docs/readme.txt", b"original content")

        with patch("os.fsync", side_effect=OSError("simulated crash mid-write")):
            with pytest.raises(OSError):
                driver.put("docs/readme.txt", b"new content that never lands")

        # The real object must still hold its last known-good content, not a
        # truncated/mixed version.
        assert driver.get("docs/readme.txt") == b"original content"


def test_put_success_round_trip():
    with tempfile.TemporaryDirectory() as root:
        driver = LocalDriver(root)
        meta = driver.put("docs/readme.txt", b"hello vector", content_type="text/plain")
        assert meta["size"] == 12
        assert driver.get("docs/readme.txt") == b"hello vector"
        assert driver.exists("docs/readme.txt")


if __name__ == "__main__":
    test_put_failure_mid_write_leaves_no_partial_file()
    test_put_failure_mid_overwrite_preserves_old_content()
    test_put_success_round_trip()
    print("OK - test_collections_storage_atomic_write.py")
