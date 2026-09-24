"""vector_finagent headers claimed 'Copyright VECTOR / MIT' for code derived from Fincept Terminal.
They now credit the origin; the normalizer is idempotent and never changes compiled code."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

ROOT = Path(__file__).resolve().parents[1]
FINAGENT = ROOT / "districts" / "investment" / "vector_finagent"


def _load():
    spec = importlib.util.spec_from_file_location("nfh", ROOT / "scripts" / "normalize_finagent_headers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_file_still_claims_vector_copyright():
    offenders = [str(p) for p in FINAGENT.rglob("*.py")
                 if "Copyright (c) 2024-2026 VECTOR" in p.read_text(encoding="utf-8", errors="ignore")]
    assert offenders == []


def test_normalizer_is_idempotent_and_preserves_line_endings():
    m = _load()
    old = m.OLD + "import os\n"
    once = m.normalize(old)
    assert once == m.NEW + "import os\n"
    assert m.normalize(once) == once
    crlf = old.replace("\n", "\r\n")
    assert m.normalize(crlf) == (m.NEW + "import os\n").replace("\n", "\r\n")
    assert m.normalize("# nothing to do\n") == "# nothing to do\n"


def test_replacement_never_changes_compiled_code():
    m = _load()
    src = m.OLD + "def f():\n    return 1\n"
    assert m._same_code(src, m.normalize(src), "x.py")


def test_running_the_script_again_changes_nothing():
    assert _load().main(dry_run=True) == (0, 0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
