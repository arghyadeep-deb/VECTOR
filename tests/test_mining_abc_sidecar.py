"""Regression for core/mining/_abc.py Sidecar.write()/read():

write() wrote the tmp file via `os.fdopen(fd, "w")` with no explicit encoding
and no fsync before `os.replace()`. Sidecar.write/read back the live mining
runtime state (~/.vector/runtime/mining.json, read by `vector mine status`
while a miner process is running -- see core/mining/cpu_pearl.py and
core/mining/vllm_pearl.py). Two real risks:

1. No fsync: a crash mid-write (process kill, OOM, power loss) during an
   active mining session could leave a truncated/zero-byte tmp file that
   silently never replaces the real sidecar (so the bug was not "serves a
   truncated file" like the collections/storage.py case -- it's "the write
   step itself has no durability guarantee before the rename", the same gap
   class fixed this cycle wherever a write lacked fsync).
2. No explicit `encoding="utf-8"`: both write() and read() relied on the
   platform-default text encoding, which on Windows is the locale codepage
   (not UTF-8) unless PYTHONUTF8=1 is set -- any non-ASCII content in the
   sidecar payload (e.g. an error message from an upstream tool) could raise
   UnicodeEncodeError/UnicodeDecodeError or round-trip incorrectly.

Fixed by opening with `encoding="utf-8"` on both sides and calling
`fh.flush(); os.fsync(fh.fileno())` before `os.replace()`.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from core.mining._abc import Sidecar


def test_write_fsyncs_before_replace():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "mining.json"
        with patch("os.fsync") as mock_fsync:
            Sidecar.write(path, {"provider_id": "cpu-pearl"})
        assert mock_fsync.called, "Sidecar.write() must fsync the tmp file before os.replace()"
        assert path.exists()


def test_write_failure_mid_fsync_leaves_no_partial_sidecar():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "mining.json"
        with patch("os.fsync", side_effect=OSError("simulated crash mid-write")):
            try:
                Sidecar.write(path, {"provider_id": "cpu-pearl"})
            except OSError:
                pass
        assert not path.exists(), "a failed write must never leave a partial sidecar at the real path"
        leftovers = list(Path(root).glob(".mining-*"))
        assert leftovers == [], f"leaked temp file(s): {leftovers}"


def test_round_trip_non_ascii_payload():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "mining.json"
        payload = {"provider_id": "cpu-pearl", "last_error": "GPU 温度过高"}
        Sidecar.write(path, payload)
        assert Sidecar.read(path) == payload


def test_write_uses_explicit_utf8_encoding():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "mining.json"
        real_fdopen = __import__("os").fdopen
        captured = {}

        def spy_fdopen(fd, mode="r", *args, **kwargs):
            captured["encoding"] = kwargs.get("encoding")
            return real_fdopen(fd, mode, *args, **kwargs)

        with patch("os.fdopen", side_effect=spy_fdopen):
            Sidecar.write(path, {"provider_id": "cpu-pearl"})
        assert captured.get("encoding") == "utf-8"


if __name__ == "__main__":
    test_write_fsyncs_before_replace()
    test_write_failure_mid_fsync_leaves_no_partial_sidecar()
    test_round_trip_non_ascii_payload()
    test_write_uses_explicit_utf8_encoding()
    print("OK - test_mining_abc_sidecar.py")
