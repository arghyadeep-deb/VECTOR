"""Regression checks for LSP diagnostics under Loguru."""

from __future__ import annotations

import sys
from pathlib import Path


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


def test_lsp_sources_do_not_pass_stdlib_logging_arguments_to_loguru():
    lsp_dir = VECTORCODE_SRC / "agent" / "lsp"
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(lsp_dir.glob("*.py"))
    )

    assert "exc_info=True" not in combined
    assert 'logger.debug("[%s]' not in combined
    assert 'logger.warning("[%s]' not in combined
    assert "LSP shutdown error: %s" not in combined
