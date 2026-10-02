"""Regression: core/jcode/tools/apply_patch.py's apply_patch() wrote/deleted
files via `base / hunk.path` with zero confinement -- hunk.path/move_to are
parsed directly out of the patch TEXT (an LLM-generated patch is this tool's
whole purpose), so an absolute path or a "../" escape in a
*** Add File:/Update File:/Delete File:/Move to: directive reached real
file I/O outside base_dir (pathlib's `/` returns an absolute RHS unmodified,
discarding base entirely). Found during the Phase 3 whole-repo audit
(2026-10-02). Real caller: districts/coding/coding_tools.py's
apply_codex_patch() (gated behind an active coding grant, but the grant
authorizes editing the repo, not an arbitrary absolute/escaped path).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.jcode.tools.apply_patch import apply_patch


def test_add_file_absolute_path_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "evil.py"
    patch = f"""*** Begin Patch
*** Add File: {target}
+pwned = True
*** End Patch"""
    result = apply_patch(patch, base_dir=str(tmp_path / "work"))
    assert result["success"] is False
    assert not target.exists()


def test_add_file_dotdot_escape_rejected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    patch = """*** Begin Patch
*** Add File: ../escaped.py
+pwned = True
*** End Patch"""
    result = apply_patch(patch, base_dir=str(work))
    assert result["success"] is False
    assert not (tmp_path / "escaped.py").exists()


def test_update_file_move_to_escape_rejected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    src = work / "a.py"
    src.write_text("x = 1\n")
    patch = """*** Begin Patch
*** Update File: a.py
*** Move to: ../escaped.py
@@ x = 1
-x = 1
+x = 2
*** End Patch"""
    result = apply_patch(patch, base_dir=str(work))
    assert result["success"] is False
    assert not (tmp_path / "escaped.py").exists()
    assert src.read_text() == "x = 1\n"  # original untouched


def test_legitimate_relative_paths_still_work(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    patch = """*** Begin Patch
*** Add File: sub/dir/new.py
+hello = 1
*** End Patch"""
    result = apply_patch(patch, base_dir=str(work))
    assert result["success"] is True
    assert (work / "sub" / "dir" / "new.py").exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
