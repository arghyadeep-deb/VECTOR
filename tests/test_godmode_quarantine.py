"""Regression tests for the quarantined Godmode/jailbreak skill."""

from __future__ import annotations

import asyncio

import pytest


def test_execute_code_rejects_quarantined_godmode_paths():
    from core.loop.permission_gateway import Action, PermissionGateway

    result = asyncio.run(
        PermissionGateway()._execute_action(
            Action(
                "execute_code",
                {
                    "code": "exec(open('skills/red-teaming/godmode/scripts/godmode_race.py').read())",
                    "language": "python",
                },
                "test",
            )
        )
    )

    assert result["status"] == "rejected"
    assert result["quarantine"] == "godmode"
    assert "quarantined" in result["reason"].lower()


def test_godmode_loader_does_not_load_quarantined_scripts():
    from pathlib import Path

    loader = Path(
        "vectorcode/src/skills/red-teaming/godmode/scripts/load_godmode.py"
    ).read_text(encoding="utf-8")

    assert "godmode_race.py" not in loader.split("_QUARANTINED_SCRIPTS", 1)[0]
    assert "_QUARANTINED_SCRIPTS" in loader
    assert "quarantined" in loader.lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
