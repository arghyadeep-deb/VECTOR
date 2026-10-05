"""Regression for a CWE-22 path-traversal + arbitrary-directory-wipe bug in
vectorcode/src/skills/importer.py's SkillImporter.import_skill().

target_dir was built as `self._target_root / resolved.source / resolved.name`
with zero validation. resolved.name comes from a skill's own SKILL.md YAML
frontmatter (parsed via yaml.safe_load() of a cloned, potentially
attacker-controlled git repo for the "github" source -- see
sources/github.py's _read_preview()), so a malicious
`name: "../../../../somewhere"` in that frontmatter let target_dir escape
self._target_root entirely. import_skill() then does
`shutil.rmtree(target_dir)` (if it exists) followed by `target_dir.mkdir()`
-- an attacker-controlled arbitrary-directory wipe, driven entirely by
installing an untrusted skill.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest

from skills.importer import SkillImporter
from skills.sources.base import ResolvedSkill


def _make_source_skill(tmp_path: Path, name: str, source: str = "github") -> ResolvedSkill:
    skill_dir = tmp_path / "upstream_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: whatever\n---\n\nbody text", encoding="utf-8"
    )
    return ResolvedSkill(
        name=name,
        source=source,
        path=skill_dir,
        category="",
        description="",
        commit="",
    )


def test_malicious_name_is_rejected_not_installed(tmp_path):
    target_root = tmp_path / "target_root"
    importer = SkillImporter(
        parser=MagicMock(), tool_translator=MagicMock(_table={}),
        target_root=target_root,
    )
    resolved = _make_source_skill(tmp_path, name="../../../escape-attempt")

    result = importer.import_skill(resolved)

    assert result.success is False
    assert not (target_root.parent / "escape-attempt").exists()


def test_malicious_source_is_rejected(tmp_path):
    target_root = tmp_path / "target_root"
    importer = SkillImporter(
        parser=MagicMock(), tool_translator=MagicMock(_table={}),
        target_root=target_root,
    )
    resolved = _make_source_skill(tmp_path, name="ok-name", source="../escape")

    result = importer.import_skill(resolved)

    assert result.success is False


def test_normal_name_still_installs_successfully(tmp_path):
    target_root = tmp_path / "target_root"
    translator = MagicMock(_table={})
    translator.translate_markdown.return_value = ("body text", [])
    importer = SkillImporter(
        parser=MagicMock(), tool_translator=translator,
        target_root=target_root,
    )
    resolved = _make_source_skill(tmp_path, name="my-cool-skill")

    result = importer.import_skill(resolved)

    assert result.success is True
    assert result.target_path == target_root / "github" / "my-cool-skill"
    assert (target_root / "github" / "my-cool-skill" / "SKILL.md").exists()


def test_existing_directory_outside_target_root_is_not_wiped(tmp_path):
    # Simulate the real attack: a sibling directory of target_root that
    # a ".." name could have reached and rmtree()'d.
    victim = tmp_path / "victim_dir"
    victim.mkdir()
    (victim / "important.txt").write_text("do not delete", encoding="utf-8")

    target_root = tmp_path / "target_root"
    importer = SkillImporter(
        parser=MagicMock(), tool_translator=MagicMock(_table={}),
        target_root=target_root,
    )
    resolved = _make_source_skill(tmp_path, name="../victim_dir")

    importer.import_skill(resolved)

    assert victim.exists()
    assert (victim / "important.txt").read_text(encoding="utf-8") == "do not delete"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
