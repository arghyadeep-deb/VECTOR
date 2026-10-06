"""Regression test for atomic gateway coordination metadata writes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway import status


def test_interrupted_status_write_preserves_previous_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "gateway-status.json"
    original = '{"pid": 123, "state": "healthy"}'
    path.write_text(original, encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(status.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        status._write_json_file(path, {"pid": 456, "state": "starting"})

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.tmp")) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
