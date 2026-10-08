"""Regression coverage for OD-38 production file-tool confinement wiring."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.runtime_paths import get_data_root
from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_mcp.server import MCPServer
from vectorcode.src.vc_system.orchestrator import QueryOrchestrator
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec
from vectorcode.src.vc_tools.file_read import FileReadTool
from vectorcode.src.vc_tools.file_write import FileWriteTool


REPO_ROOT = Path(__file__).resolve().parents[1]


class _NoArgumentTool(BaseTool):
    """Sentinel proving generic factory calls remain argument-free."""

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="od38_no_argument_tool",
            description="OD-38 generic-construction sentinel.",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, **params: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.spec.name,
            content="ok",
            success=True,
        )


@pytest.fixture
def runtime_data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data_root = (tmp_path / "runtime-data").resolve()
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(data_root))
    assert get_data_root() == data_root
    return data_root


def _assert_confined(tool: FileReadTool | FileWriteTool, data_root: Path) -> None:
    expected_roots = [REPO_ROOT.resolve(), data_root.resolve()]
    assert tool._allowed_dirs == expected_roots
    assert tool._is_path_allowed(REPO_ROOT / "inside-repository.txt")
    assert tool._is_path_allowed(data_root / "inside-runtime-data.txt")
    assert not tool._is_path_allowed(data_root.parent / "outside-both-roots.txt")


def test_mcp_auto_discovery_injects_real_file_tool_roots(
    runtime_data_root: Path,
) -> None:
    tools = {tool.spec.name: tool for tool in MCPServer._auto_discover_tools()}

    _assert_confined(tools["file_read"], runtime_data_root)
    _assert_confined(tools["file_write"], runtime_data_root)


def test_orchestrator_factory_injects_real_file_tool_roots(
    runtime_data_root: Path,
) -> None:
    system = SimpleNamespace(memory_backend=None, engine=object(), model="test-model")
    tools = QueryOrchestrator(system)._build_tools(["file_read", "file_write"])
    tools_by_name = {tool.spec.name: tool for tool in tools}

    _assert_confined(tools_by_name["file_read"], runtime_data_root)
    _assert_confined(tools_by_name["file_write"], runtime_data_root)


def test_generic_builder_paths_keep_other_tool_construction_argument_free(
    runtime_data_root: Path,
) -> None:
    key = "od38_no_argument_tool"
    ToolRegistry.register_value(key, _NoArgumentTool)
    try:
        mcp_tools = MCPServer._auto_discover_tools()
        system = SimpleNamespace(memory_backend=None, engine=object(), model="test-model")
        orchestrator_tools = QueryOrchestrator(system)._build_tools([key])
    finally:
        ToolRegistry._entries().pop(key, None)

    assert any(isinstance(tool, _NoArgumentTool) for tool in mcp_tools)
    assert len(orchestrator_tools) == 1
    assert isinstance(orchestrator_tools[0], _NoArgumentTool)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
