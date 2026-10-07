"""Regression for the 2026-10-07 core/resilience audit.

ProcessKillInjector._targets used to map "voice_ws" to the bare image name
"python" (no .exe). voice_ws is an in-process FastAPI WebSocket route
(core/api/routers/voice_ws.py), not a separate OS process, so there was
nothing safe to scope a kill to -- and "python"/"python.exe" is not specific
to any one VECTOR process: the autonomous loop and the API server (which may
be the very process running this injector) all share that image name. The
only reason this never did real damage is that Windows' `taskkill /IM`
requires an exact image-name match including the extension, so the missing
".exe" happened to make every real invocation silently match nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.resilience.injectors.process_kill import ProcessKillInjector

_GENERIC_INTERPRETER_NAMES = {"python", "python.exe", "pythonw.exe", "node", "node.exe"}


def test_no_target_is_a_bare_or_generic_interpreter_image_name():
    injector = ProcessKillInjector()

    for label, image_name in injector._targets.items():
        assert image_name.lower() not in _GENERIC_INTERPRETER_NAMES, (
            f"target {label!r} -> {image_name!r} would taskkill every process sharing that "
            "generic interpreter image name, including VECTOR's own loop/API process"
        )


def test_every_target_is_a_fully_qualified_exe_name():
    injector = ProcessKillInjector()

    assert injector._targets, "expected at least one real target (e.g. ollama.exe)"
    for label, image_name in injector._targets.items():
        assert image_name.lower().endswith(".exe"), (
            f"target {label!r} -> {image_name!r} is missing the .exe suffix Windows taskkill "
            "requires for an exact match -- without it the experiment silently no-ops"
        )


if __name__ == "__main__":
    import subprocess

    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
    print("✅ test_core_resilience_process_kill_safety OK" if result.returncode == 0 else "❌ FAILED")
