"""Regression tests for SkillManageTool path confinement and TOML escaping.

Pre-fix, ``name`` flowed into ``self._skills_dir / f"{name}.toml"`` with no
validation, letting a ".." segment or an absolute path escape the configured
skills directory entirely (CWE-22) -- including via the delete action, which
could remove an arbitrary ``.toml`` file the process can reach. Pre-fix,
``description``/``tool_name``/``arguments_template``/``output_key`` were also
interpolated into the generated TOML as raw, unescaped string literals.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vectorcode.src.vc_tools.skill_manage import SkillManageTool


def _make_tool(tmp_path: Path) -> tuple[SkillManageTool, Path]:
    skills_dir = tmp_path / "skills"
    return SkillManageTool(skills_dir=skills_dir), skills_dir


def test_create_rejects_parent_traversal(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    escape_target = tmp_path / "evil.toml"
    result = tool.execute(action="create", name="../evil", description="x")
    assert result.success is False
    assert not escape_target.exists()


def test_create_rejects_nested_separator(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    result = tool.execute(action="create", name="sub/evil", description="x")
    assert result.success is False
    assert not (skills_dir.parent / "sub").exists()


def test_create_rejects_absolute_override(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    absolute_name = str(outside / "evil")
    result = tool.execute(action="create", name=absolute_name, description="x")
    assert result.success is False
    assert not (outside / "evil.toml").exists()


def test_delete_cannot_escape_skills_dir(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    skills_dir.mkdir(parents=True)
    victim = tmp_path / "victim.toml"
    victim.write_text("[skill]\nname = \"victim\"\n", encoding="utf-8")

    result = tool.execute(action="delete", name="../victim")

    assert result.success is False
    assert victim.exists()


def test_load_cannot_escape_skills_dir(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    skills_dir.mkdir(parents=True)
    secret = tmp_path / "secret.toml"
    secret.write_text("TOP SECRET", encoding="utf-8")

    result = tool.execute(action="load", name="../secret")

    assert result.success is False
    assert "TOP SECRET" not in result.content


def test_create_round_trip_within_skills_dir(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    result = tool.execute(action="create", name="my_skill", description="does a thing")
    assert result.success is True
    assert (skills_dir / "my_skill.toml").exists()

    loaded = tool.execute(action="load", name="my_skill")
    assert loaded.success is True
    assert 'name = "my_skill"' in loaded.content
    assert 'description = "does a thing"' in loaded.content


def test_create_escapes_quotes_in_description(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    malicious_description = '"\n[malicious]\ninjected = true\n'
    result = tool.execute(
        action="create", name="injector", description=malicious_description
    )
    assert result.success is True

    content = (skills_dir / "injector.toml").read_text(encoding="utf-8")
    # The injected content must stay inside the quoted description value,
    # not break out into its own TOML table/key.
    assert "[malicious]" not in content.splitlines()[0:2]
    import tomllib

    parsed = tomllib.loads(content)
    assert parsed["skill"]["description"] == malicious_description
    assert "malicious" not in parsed


def test_create_escapes_single_quote_in_arguments_template(tmp_path: Path) -> None:
    tool, skills_dir = _make_tool(tmp_path)
    result = tool.execute(
        action="create",
        name="quoter",
        description="d",
        steps=[
            {
                "tool_name": "file_read",
                "arguments_template": "it's a test",
            }
        ],
    )
    assert result.success is True

    content = (skills_dir / "quoter.toml").read_text(encoding="utf-8")
    import tomllib

    parsed = tomllib.loads(content)
    assert parsed["skill"]["steps"][0]["arguments_template"] == "it's a test"
