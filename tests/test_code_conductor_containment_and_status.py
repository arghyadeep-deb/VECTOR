"""Coding workflow gaps from the 2026-09-13 V1 handoff, verified open 2026-09-26 and closed here:
  * str_replace/write_file/apply_patch wrote wherever an LLM-produced path pointed (no workspace containment)
  * CodingOrchestrator reported status "ok" for zero edits (0 == 0) and "partial" when every edit failed
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.code_conductor.str_replace import apply_patch, str_replace, write_file


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    return root, outside


def test_edit_inside_the_workspace_still_works(ws):
    root, _ = ws
    r = str_replace("a.py", "x = 1", "x = 2", cwd=str(root))
    assert r["status"] == "ok" and (root / "a.py").read_text(encoding="utf-8") == "x = 2\n"


def test_dotdot_escape_is_refused(ws):
    root, outside = ws
    r = str_replace("../outside.txt", "secret", "pwned", cwd=str(root))
    assert r["status"] == "error" and "outside the workspace" in r["message"]
    assert outside.read_text(encoding="utf-8") == "secret\n"


def test_absolute_path_outside_the_workspace_is_refused(ws):
    root, outside = ws
    assert str_replace(str(outside), "secret", "pwned", cwd=str(root))["status"] == "error"
    assert write_file(str(outside), "pwned", cwd=str(root))["status"] == "error"
    assert outside.read_text(encoding="utf-8") == "secret\n"


def test_write_file_cannot_create_files_outside_the_workspace(ws):
    root, _ = ws
    r = write_file("../new_file.py", "print(1)", cwd=str(root))
    assert r["status"] == "error" and not (root.parent / "new_file.py").exists()


def test_env_and_git_internals_are_protected_even_inside_the_workspace(ws):
    root, _ = ws
    (root / ".env").write_text("KEY=1\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    assert str_replace(".env", "KEY=1", "KEY=2", cwd=str(root))["status"] == "error"
    assert write_file(".env.local", "X=1", cwd=str(root))["status"] == "error"
    assert str_replace(".git/config", "[core]", "[evil]", cwd=str(root))["status"] == "error"
    assert (root / ".env").read_text(encoding="utf-8") == "KEY=1\n"


def test_apply_patch_refuses_paths_outside_the_workspace(ws):
    root, outside = ws
    r = apply_patch("../outside.txt", "--- a\n+++ b\n@@ -1 +1 @@\n-secret\n+pwned\n", cwd=str(root))
    assert r["status"] == "error" and outside.read_text(encoding="utf-8") == "secret\n"


def test_symlink_escape_is_refused(ws):
    root, outside = ws
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert str_replace("link.txt", "secret", "pwned", cwd=str(root))["status"] == "error"
    assert outside.read_text(encoding="utf-8") == "secret\n"


def test_no_cwd_keeps_the_old_behaviour(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("a = 1\n", encoding="utf-8")
    assert str_replace(str(f), "a = 1", "a = 2")["status"] == "ok"


# ── orchestrator status honesty ────────────────────────────────────────────────

class _Rec:
    def __init__(self, status):
        self.file, self.status, self.diff = "f.py", status, ""


async def _run_with_edits(monkeypatch, tmp_path, statuses):
    from core.code_conductor import orchestrator as orch_mod
    o = orch_mod.CodingOrchestrator(cwd=str(tmp_path))

    async def _map():
        return object()

    async def _pick(_i):
        return []

    async def _plan(_i, _c):
        return "plan"

    async def _edits(_i, _p, _c):
        return [_Rec(s) for s in statuses]

    monkeypatch.setattr(o, "_build_code_map", _map)
    monkeypatch.setattr(o, "_pick_files", _pick)
    monkeypatch.setattr(o, "_plan_changes", _plan)
    monkeypatch.setattr(o, "_execute_edits", _edits)
    monkeypatch.setattr(o, "_format_context", lambda *_a, **_k: "")
    monkeypatch.setattr(orch_mod, "read_files", lambda *_a, **_k: {})
    return await o.run("do something")


@pytest.mark.asyncio
async def test_zero_edits_is_an_error_not_ok(monkeypatch, tmp_path):
    out = await _run_with_edits(monkeypatch, tmp_path, [])
    assert out["status"] == "error" and "no edits" in out["error"]


@pytest.mark.asyncio
async def test_every_edit_failing_is_an_error_not_partial(monkeypatch, tmp_path):
    out = await _run_with_edits(monkeypatch, tmp_path, ["error", "error"])
    assert out["status"] == "error"


@pytest.mark.asyncio
async def test_some_edits_applied_is_partial_and_all_is_ok(monkeypatch, tmp_path):
    assert (await _run_with_edits(monkeypatch, tmp_path, ["ok", "error"]))["status"] == "partial"
    assert (await _run_with_edits(monkeypatch, tmp_path, ["ok", "ok"]))["status"] == "ok"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


@pytest.mark.asyncio
async def test_result_says_no_tests_or_review_were_run(monkeypatch, tmp_path):
    out = await _run_with_edits(monkeypatch, tmp_path, ["ok"])
    assert out["status"] == "ok"
    assert out["verification"]["tests_run"] is False and out["verification"]["review_run"] is False
    assert "unverified" in out["verification"]["note"]
