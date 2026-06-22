"""Regression guard: the skill-scanner gate must FAIL CLOSED on scanner error.

Cross-check fix 2026-06-22 (Opus): Codex wired core.security.skill_scanner into
vectorcode/src/skills/loader.py::load_skill, but the non-block exception path
logged a warning and loaded the skill anyway — a fail-OPEN security gate. A
malicious skill can crash the scanner to bypass it. The gate now blocks on
scanner error (operator escape hatch: VECTOR_DISABLE_SKILL_SCANNER=1).
"""
import inspect

from vectorcode.src.skills import loader


def test_scanner_error_fails_closed():
    src = inspect.getsource(loader.load_skill)
    start = src.index("skill_scanner")
    region = src[start:start + 1200]
    # the generic-exception path must RAISE (block), not warn-and-continue
    assert "raise ValueError" in region, "scanner-error path no longer blocks"
    assert "fail-closed" in region.lower(), "fail-closed intent missing"
    # and the read_text (actual load) must come AFTER the scan gate, not be
    # reachable when the scanner errored
    assert region.index("raise ValueError") < region.find("read_text") or "read_text" not in region


def test_disable_env_escape_hatch_exists():
    src = inspect.getsource(loader.load_skill)
    assert "VECTOR_DISABLE_SKILL_SCANNER" in src, "operator bypass env removed"
