"""Regression test for districts/coding/coding_tools.py::load_skill()/list_skills().

Documents and proves the fix for a real, verified 2026-09-30 bug: load_skill()
called SkillManager(skills_dirs=[...]) -- a constructor that has never existed
(the real signature is SkillManager(config_getter)) -- imported a
core.coding_assistant.core.paths module that does not exist, and read a
skill.content attribute SkillInfo has never had (the real field is `prompt`).
Even a corrected constructor call would have then crashed on
HarnessFilesManager's own "not initialized" RuntimeError, since VECTOR's
runtime never calls init_harness_files_manager(). All three were silently
swallowed by a broad except Exception, so load_skill() has returned None on
every single call since it was wired in. The fix bypasses the heavy
SkillManager/VectorCAConfig/HarnessFilesManager chain entirely and reuses only
the lightweight, dependency-free parser/models directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from districts.coding import coding_tools


def _write_skill(base: Path, name: str, description: str, body: str) -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_load_skill_returns_real_parsed_content(tmp_path, monkeypatch):
    _write_skill(tmp_path, "rebuild-vault-index", "Rebuild the LightRAG vault index.", "1. Quarantine.\n2. Re-ingest.")
    monkeypatch.setattr(coding_tools, "_vector_skills_dir", lambda: tmp_path)

    result = coding_tools.load_skill("rebuild-vault-index")
    assert result is not None
    assert result["name"] == "rebuild-vault-index"
    assert result["description"] == "Rebuild the LightRAG vault index."
    assert "Quarantine" in result["prompt"]
    assert "Re-ingest" in result["prompt"]
    # The old, broken implementation returned a "content" key that does not
    # exist on SkillInfo at all; the real field is "prompt".
    assert "content" not in result


def test_load_skill_returns_none_for_missing_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(coding_tools, "_vector_skills_dir", lambda: tmp_path)
    assert coding_tools.load_skill("does-not-exist") is None


def test_load_skill_returns_none_gracefully_when_directory_absent(tmp_path, monkeypatch):
    missing = tmp_path / "never_created"
    monkeypatch.setattr(coding_tools, "_vector_skills_dir", lambda: missing)
    assert coding_tools.load_skill("anything") is None


def test_load_skill_returns_none_for_malformed_frontmatter(tmp_path, monkeypatch):
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("no frontmatter here, just text", encoding="utf-8")
    monkeypatch.setattr(coding_tools, "_vector_skills_dir", lambda: tmp_path)

    assert coding_tools.load_skill("broken-skill") is None


def test_list_skills_enumerates_every_valid_skill_and_skips_broken_ones(tmp_path, monkeypatch):
    _write_skill(tmp_path, "skill-a", "First skill.", "body a")
    _write_skill(tmp_path, "skill-b", "Second skill.", "body b")
    broken_dir = tmp_path / "skill-c-broken"
    broken_dir.mkdir()
    (broken_dir / "SKILL.md").write_text("not valid frontmatter", encoding="utf-8")
    (tmp_path / "not_a_skill_dir.txt").write_text("ignored", encoding="utf-8")

    monkeypatch.setattr(coding_tools, "_vector_skills_dir", lambda: tmp_path)

    result = coding_tools.list_skills()
    names = {s["name"] for s in result}
    assert names == {"skill-a", "skill-b"}
    assert all("description" in s for s in result)


def test_list_skills_returns_empty_list_when_directory_absent(tmp_path, monkeypatch):
    missing = tmp_path / "never_created"
    monkeypatch.setattr(coding_tools, "_vector_skills_dir", lambda: missing)
    assert coding_tools.list_skills() == []


def test_load_skill_is_wired_to_the_real_vector_skills_dir_by_default():
    # No monkeypatch here: confirms the real, un-patched default points at
    # data/vector_skills under the repo, matching the owner's explicit
    # choice of a VECTOR-only directory (never Claude's .claude/skills/).
    from core.runtime_paths import data_path

    assert coding_tools._vector_skills_dir() == data_path("vector_skills")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
