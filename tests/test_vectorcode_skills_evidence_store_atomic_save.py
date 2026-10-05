"""Regression for vectorcode/src/skills/optional/security/oss-forensics/scripts/
evidence-store.py's EvidenceStore._save():

the original wrote directly to self.filepath with no temp-file/rename step --
a crash or kill mid-write (json.dump isn't atomic) would leave a previously-
good forensic evidence store truncated/corrupted, with no recovery. Fixed to
write to a temp file in the same directory and os.replace() atomically.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).parent.parent
    / "vectorcode"
    / "src"
    / "skills"
    / "optional"
    / "security"
    / "oss-forensics"
    / "scripts"
    / "evidence-store.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("evidence_store_mod", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_save_is_atomic_no_temp_file_left_behind(tmp_path):
    mod = _load_module()
    store_path = tmp_path / "evidence.json"
    store = mod.EvidenceStore(str(store_path))
    store.add(source="test", content="hello", evidence_type="manual")

    assert store_path.exists()
    leftover_tmp = list(tmp_path.glob(".evidence-*.tmp"))
    assert leftover_tmp == [], f"temp file(s) left behind: {leftover_tmp}"

    on_disk = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(on_disk["evidence"]) == 1


def test_save_preserves_prior_good_file_if_write_fails(tmp_path, monkeypatch):
    mod = _load_module()
    store_path = tmp_path / "evidence.json"
    store = mod.EvidenceStore(str(store_path))
    store.add(source="first", content="good entry", evidence_type="manual")
    good_contents = store_path.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(mod.json, "dump", _boom)
    with pytest.raises(OSError):
        store.add(source="second", content="never written", evidence_type="manual")

    # The original file must be untouched -- no partial/corrupt overwrite.
    assert store_path.read_text(encoding="utf-8") == good_contents


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
