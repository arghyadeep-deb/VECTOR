"""Regression coverage for the remaining vectorcode/src round-one audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from vectorcode.src.config.theme import ColorTheme, ThemeEngine, _parse_toml_theme
from vectorcode.src.permissions import PermissionSystem
from vectorcode.src.prompt.builder import SystemPromptBuilder
from vectorcode.src.recipes.loader import Recipe


def test_permissions_fail_closed_for_unknown_risk_level() -> None:
    result = PermissionSystem(mode="autonomous").check_tool(
        "future_tool", "unrecognised"
    )

    assert not result
    assert "defaulting to deny" in result.reason


def test_permissions_respect_explicit_empty_denylists() -> None:
    permissions = PermissionSystem(
        mode="autonomous", deny_bash=[], deny_write_paths=[]
    )

    assert permissions.deny_bash == []
    assert permissions.deny_write_paths == []
    assert permissions.check_bash("rm -rf explicitly-enabled-test-path")
    assert permissions.check_write(".env")


def test_permissions_normalize_windows_case_and_separators() -> None:
    permissions = PermissionSystem(mode="standard")

    assert not permissions.check_write(r"SECRETS\api-token.txt")
    assert not permissions.check_write("project/.ENV")


def test_prompt_builder_reads_memory_files_as_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "memory.md"
    memory.write_text("₹ — café", encoding="utf-8")
    seen: list[str | None] = []
    original = Path.read_text

    def recording_read_text(path: Path, *args, **kwargs):
        seen.append(kwargs.get("encoding"))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", recording_read_text)

    assert SystemPromptBuilder("base")._load_file(str(memory), 100) == "₹ — café"
    assert seen == ["utf-8"]


def test_recipe_eval_override_preserves_explicit_zero_max_samples() -> None:
    recipe = Recipe(
        name="zero-sample",
        model="vector-focus",
        eval_benchmarks=["dummy"],
        eval_max_samples=17,
    )

    suite = recipe.to_eval_suite(max_samples=0)

    assert suite.benchmarks[0].max_samples == 0


def test_theme_save_rejects_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    engine = ThemeEngine()

    with pytest.raises(ValueError, match="Theme name"):
        engine.save_theme(ColorTheme(name="../escaped"))

    assert not (tmp_path / ".vector" / "escaped.toml").exists()


def test_theme_save_is_atomic_and_toml_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    engine = ThemeEngine()
    theme = ColorTheme(name="quoted", primary='say "hello"')

    engine.save_theme(theme)

    saved = tmp_path / ".vector" / "themes" / "quoted.toml"
    assert _parse_toml_theme(saved.read_text(encoding="utf-8"))["primary"] == theme.primary

    saved.write_text("original", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("vectorcode.src.config.theme.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        engine.save_theme(theme)

    assert saved.read_text(encoding="utf-8") == "original"
    assert list(saved.parent.glob("*.tmp")) == []


def test_cron_loguru_messages_do_not_use_printf_placeholders() -> None:
    scheduler = Path("vectorcode/src/cron/scheduler.py").read_text(encoding="utf-8")
    jobs = Path("vectorcode/src/cron/jobs.py").read_text(encoding="utf-8")

    stale_fragments = (
        "Job '%s'",
        "=%r",
        "job_id %r",
        "workdir %r",
        "provider %s",
        "%d entries",
        "%.0fs",
        "schedule %r",
    )
    for fragment in stale_fragments:
        assert fragment not in scheduler
        assert fragment not in jobs


def test_cron_output_rejects_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vectorcode.src.cron import jobs

    monkeypatch.setattr(jobs, "CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr(jobs, "OUTPUT_DIR", tmp_path / "cron" / "output")
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "cron" / "jobs.json")

    with pytest.raises(ValueError, match="only letters, numbers"):
        jobs.save_job_output("../escaped", "secret")

    assert not (tmp_path / "escaped").exists()
