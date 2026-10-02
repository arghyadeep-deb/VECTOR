"""Regression: lint_project() computed is_sub_composition (whether a file
lives under a compositions/ directory) but discarded it -- lint_file() had
no parameter to receive it at all, so every file linted via lint_project()
always got the top-level "split into separate .html files" hint instead of
the sub-composition-specific "split further" hint, even for files genuinely
under compositions/. No real caller of lint_project()/lint_file() exists in
production today (only lint_composition() is called directly, from
studio_server.py/vector_composer.py) -- fixed anyway, same bar as other
dormant-code narrow fixes this cycle.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video.composition_linter import lint_composition, lint_file, lint_project

_OVERSIZED_HTML = (
    '<!DOCTYPE html>\n<html>\n<body>\n'
    + '<div data-composition-id="x" data-width="100" data-height="100">\n'
    + "<p>line</p>\n" * 310
    + "</div>\n</body>\n</html>"
)


def test_lint_composition_default_is_not_sub_composition():
    result = lint_composition(_OVERSIZED_HTML, file_path="scene.html")
    hint = next(f.fix_hint for f in result.findings if f.code == "composition_file_too_large")
    assert "Split coherent scenes/layers" in hint
    assert "sub-composition" not in hint


def test_lint_composition_explicit_sub_composition_true():
    result = lint_composition(_OVERSIZED_HTML, file_path="scene.html", is_sub_composition=True)
    hint = next(f.fix_hint for f in result.findings if f.code == "composition_file_too_large")
    assert "Split this sub-composition further" in hint


def test_lint_file_propagates_is_sub_composition(tmp_path):
    p = tmp_path / "scene.html"
    p.write_text(_OVERSIZED_HTML, encoding="utf-8")
    default_result = lint_file(str(p))
    sub_result = lint_file(str(p), is_sub_composition=True)
    default_hint = next(f.fix_hint for f in default_result.findings if f.code == "composition_file_too_large")
    sub_hint = next(f.fix_hint for f in sub_result.findings if f.code == "composition_file_too_large")
    assert "sub-composition" not in default_hint
    assert "sub-composition" in sub_hint


def test_lint_project_detects_compositions_subdir_and_uses_sub_hint(tmp_path):
    (tmp_path / "compositions").mkdir()
    sub_file = tmp_path / "compositions" / "scene.html"
    sub_file.write_text(_OVERSIZED_HTML, encoding="utf-8")
    top_file = tmp_path / "root.html"
    top_file.write_text(_OVERSIZED_HTML, encoding="utf-8")

    results = lint_project(str(tmp_path))

    sub_result = results[str(sub_file)]
    top_result = results[str(top_file)]
    sub_hint = next(f.fix_hint for f in sub_result.findings if f.code == "composition_file_too_large")
    top_hint = next(f.fix_hint for f in top_result.findings if f.code == "composition_file_too_large")

    # This is the regression: before the fix, both got the same (top-level) hint
    # because lint_project() computed is_sub but never passed it anywhere.
    assert "sub-composition" in sub_hint
    assert "sub-composition" not in top_hint


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
