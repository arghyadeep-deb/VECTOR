"""vectorcode's tool registry.

2026-09-24 findings: `video_generation_tool` and `kanban_tools` imported the registry as
`vectorcode.src.tools.registry` while every other tool (and the agent loop) uses the bare `tools.registry`, so
Python created a SECOND registry object and those tools registered into a copy nobody reads; in addition
`ToolRegistry.register()` had no `dynamic_schema_overrides` parameter, so `video_generate` raised on import;
and `computer_use_tool` logged an import error on every run for a backend that is not in this tree.
Child process: vectorcode's bare imports need `vectorcode/src` on sys.path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_CHILD = r"""
import json, os, sys, io, contextlib
sys.path.insert(0, os.path.join(sys.argv[1], "vectorcode", "src"))
sys.path.insert(0, sys.argv[1])
from loguru import logger
buf = io.StringIO(); logger.remove(); logger.add(buf, level="WARNING")
from tools.registry import registry
import model_tools
out = {"names": registry.get_all_tool_names()}
out["one_registry"] = registry is sys.modules["tools.registry"].registry
out["shadow_copy_loaded"] = "vectorcode.src.tools.registry" in sys.modules

# dynamic_schema_overrides overlays the description at definition time and never breaks the tool
registry.register(name="probe_dyn", toolset="probe", schema={"name": "probe_dyn", "description": "static", "parameters": {"type": "object", "properties": {}}},
                  handler=lambda a, **k: "{}", dynamic_schema_overrides=lambda: {"description": "dynamic"})
registry.register(name="probe_bad", toolset="probe", schema={"name": "probe_bad", "description": "static", "parameters": {"type": "object", "properties": {}}},
                  handler=lambda a, **k: "{}", dynamic_schema_overrides=lambda: 1 / 0)
defs = {d["function"]["name"]: d["function"]["description"] for d in registry.get_definitions({"probe_dyn", "probe_bad"}, quiet=True)}
out["defs"] = defs
out["warnings"] = buf.getvalue()
print("RESULT:" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    work = Path(tempfile.mkdtemp(prefix="vc_reg_"))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VECTOR_HOME")}  # model_tools exports VECTOR_HOME into the parent; never let a child inherit the real one
    env.update(HOME=str(work / "home"), USERPROFILE=str(work / "home"), VECTOR_DB_PATH=str(work / "vm.db"), VECTOR_TEST_DATA_DIR=str(work / "data"), VECTOR_DB_KEY="vc-reg-test")
    r = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT)], capture_output=True, text=True, timeout=200, env=env, cwd=str(work))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert lines, f"child produced no result:\n{r.stderr[-900:]}"
    return json.loads(lines[-1][len("RESULT:"):])


def test_video_and_kanban_tools_register_into_the_shared_registry(result):
    names = set(result["names"])
    assert "video_generate" in names
    assert {"kanban_create", "kanban_list", "kanban_show"} <= names


def test_there_is_only_one_registry_module(result):
    assert result["one_registry"] is True and result["shadow_copy_loaded"] is False


def test_dynamic_schema_overrides_are_applied_and_failures_are_harmless(result):
    assert result["defs"]["probe_dyn"] == "dynamic"
    assert result["defs"]["probe_bad"] == "static"


def test_discovery_no_longer_logs_import_errors_for_missing_backends(result):
    assert "Could not import tool module" not in result["warnings"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
