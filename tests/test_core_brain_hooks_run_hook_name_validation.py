"""Regression for core/brain_hooks/__init__.py's run_hook(): it built
f"{hook_name}.ts" under _HOOKS_DIR and ran it via node with zero validation
of hook_name -- a value like "../../evil" would escape _HOOKS_DIR entirely.

core/mcp_tools/expansion_modules/hooks.py's own _run_hook() wrapper already
validates with an identical allowlist regex before ever calling this
function (that wrapper is what tests/test_audit_phase3_mcp_expansion_a.py
covers), but that only protects its one current caller -- run_hook() itself
was still unguarded for any other/future caller. These tests exercise the
real, unmocked run_hook() directly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brain_hooks import run_hook


def test_path_traversal_name_rejected():
    out, code = run_hook("../../evil")
    assert code == 1
    assert "invalid hook name" in out


def test_absolute_path_name_rejected():
    out, code = run_hook("/etc/passwd")
    assert code == 1
    assert "invalid hook name" in out


def test_empty_name_rejected():
    out, code = run_hook("")
    assert code == 1
    assert "invalid hook name" in out


def test_legitimate_hook_names_pass_validation():
    # These should get past the name check and fail later only because the
    # real .ts script/node toolchain isn't present in this test environment
    # -- "invalid hook name" must never be the reported reason.
    for name in ("session-start", "classify-message", "validate-write",
                 "pre-compact", "stop-checklist", "qmd-refresh",
                 "intelligence", "session-restore"):
        out, code = run_hook(name)
        assert "invalid hook name" not in out, f"{name!r} wrongly rejected: {out}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
