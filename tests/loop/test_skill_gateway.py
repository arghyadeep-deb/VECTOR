"""Regression guard: skill execution in _act_on must pass the PermissionGateway.

Security fix 2026-06-21 (audit finding): the Phase-3B skill path called
sm.execute() directly whenever a skill matched with confidence > 0.6, bypassing
the gateway entirely — FORBIDDEN/RED were never enforced, violating RULE 3
("LLM has zero direct access. EVER."). These tests fail if that gate is removed.

Source-level guard (the convention used by scripts/integration_check.py): a full
behavioral test of _act_on would have to mock red-team review, the event bus,
the governor and episodic memory — fragile, and DB-touching while the soak runs.
This asserts the security-relevant structure instead.
"""
import inspect

from core.loop.autonomous_loop import AutonomousLoop


def _skill_region(src: str) -> str:
    start = src.index("Phase 3B: check VectorCode Skills")
    end = src.index("if not _skill_executed:", start)
    return src[start:end]


def test_skill_path_consults_gateway():
    region = _skill_region(inspect.getsource(AutonomousLoop._act_on))
    assert ".classify(" in region, "skill path no longer classifies via the gateway"
    assert "FORBIDDEN" in region, "skill path no longer blocks FORBIDDEN actions"
    assert "_skill_allowed" in region, "skill path missing the _skill_allowed gate"


def test_gate_precedes_skill_execution():
    region = _skill_region(inspect.getsource(AutonomousLoop._act_on))
    assert region.index("_skill_allowed") < region.index("sm.execute(skill.name"), (
        "sm.execute runs before the gateway gate — bypass reintroduced"
    )


def test_skill_execute_guarded_by_allowed_flag():
    region = _skill_region(inspect.getsource(AutonomousLoop._act_on))
    preceding = region[: region.index("sm.execute(skill.name")]
    assert "if _skill_allowed:" in preceding, (
        "sm.execute is not guarded by the _skill_allowed gate"
    )
