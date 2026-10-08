"""Regression coverage for OD-41 ApplyPatchTool root confinement."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.runtime_paths import get_data_root
from vectorcode.src.vc_mcp.server import MCPServer
from vectorcode.src.vc_system.orchestrator import QueryOrchestrator
from vectorcode.src.vc_tools.apply_patch import ApplyPatchTool


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH = """--- a/target.txt
+++ b/target.txt
@@ -1 +1 @@
-before
+after
"""


@pytest.fixture
def runtime_data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data_root = (tmp_path / "runtime-data").resolve()
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(data_root))
    assert get_data_root() == data_root
    return data_root


def test_apply_patch_rejects_outside_root_without_touching_file(tmp_path: Path) -> None:
    allowed_root = (tmp_path / "allowed").resolve()
    allowed_root.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("before\n", encoding="utf-8")

    result = ApplyPatchTool(allowed_dirs=[str(allowed_root)]).execute(
        path=str(outside_file),
        patch=PATCH,
        backup=False,
    )

    assert not result.success
    assert "outside allowed directories" in result.content
    assert outside_file.read_text(encoding="utf-8") == "before\n"


def test_apply_patch_inside_allowed_root_still_works(tmp_path: Path) -> None:
    allowed_root = (tmp_path / "allowed").resolve()
    allowed_root.mkdir()
    inside_file = allowed_root / "target.txt"
    inside_file.write_text("before\n", encoding="utf-8")

    result = ApplyPatchTool(allowed_dirs=[str(allowed_root)]).execute(
        path=str(inside_file),
        patch=PATCH,
        backup=False,
    )

    assert result.success
    assert inside_file.read_text(encoding="utf-8") == "after\n"


def _assert_production_roots(tool: ApplyPatchTool, data_root: Path) -> None:
    assert tool._allowed_dirs == [REPO_ROOT.resolve(), data_root.resolve()]


def test_mcp_auto_discovery_injects_apply_patch_roots(
    runtime_data_root: Path,
) -> None:
    tools = {tool.spec.name: tool for tool in MCPServer._auto_discover_tools()}

    _assert_production_roots(tools["apply_patch"], runtime_data_root)


def test_orchestrator_factory_injects_apply_patch_roots(
    runtime_data_root: Path,
) -> None:
    system = SimpleNamespace(memory_backend=None, engine=object(), model="test-model")
    tools = QueryOrchestrator(system)._build_tools(["apply_patch"])

    assert len(tools) == 1
    _assert_production_roots(tools[0], runtime_data_root)


def test_sensitive_file_blocklist_remains_enforced(tmp_path: Path) -> None:
    sensitive_file = tmp_path / ".env"
    sensitive_file.write_text("before\n", encoding="utf-8")

    result = ApplyPatchTool(allowed_dirs=[str(tmp_path)]).execute(
        path=str(sensitive_file),
        patch=PATCH,
        backup=False,
    )

    assert not result.success
    assert "sensitive file" in result.content
    assert sensitive_file.read_text(encoding="utf-8") == "before\n"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
