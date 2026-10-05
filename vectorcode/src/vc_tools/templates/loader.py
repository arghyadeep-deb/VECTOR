# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Template loader — dynamically construct BaseTool from TOML definitions."""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec

_SHELL_VALUE_REJECT = re.compile(r"[;&|`$<>\r\n]")
_SHELL_INTERPRETERS = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}


def _tmpl_base64_encode(value: Any) -> str:
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _tmpl_sha256(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _tmpl_regex_extract(pattern: Any, text: Any) -> str:
    matches = re.findall(str(pattern), str(text))
    return json.dumps(matches)


def _tmpl_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _SafeExpressionEvaluator(ast.NodeVisitor):
    """Tiny expression evaluator for template expressions.

    It intentionally supports only literals, params, containers, simple
    arithmetic/string concatenation, and calls to a fixed allowlist.
    """

    _functions = {
        "str": str,
        "int": int,
        "float": float,
        "len": len,
        "sorted": sorted,
        "list": list,
        "dict": dict,
        "base64_encode": _tmpl_base64_encode,
        "sha256": _tmpl_sha256,
        "regex_extract": _tmpl_regex_extract,
        "now_iso": _tmpl_now_iso,
    }

    def __init__(self, params: Dict[str, Any]) -> None:
        self._params = params

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self._params:
            return self._params[node.id]
        raise ValueError(f"unknown name: {node.id}")

    def visit_List(self, node: ast.List) -> list[Any]:
        return [self.visit(item) for item in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.visit(item) for item in node.elts)

    def visit_Dict(self, node: ast.Dict) -> dict[Any, Any]:
        return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values) if k is not None}

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise ValueError("operator is not allowed")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError("unary operator is not allowed")

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        value = self.visit(node.value)
        key = self.visit(node.slice)
        return value[key]

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name) or node.func.id not in self._functions:
            raise ValueError("function call is not allowed")
        fn = self._functions[node.func.id]
        args = [self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords if kw.arg}
        return fn(*args, **kwargs)

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"expression node is not allowed: {type(node).__name__}")


def _safe_eval_template_expression(expr: str, params: Dict[str, Any]) -> Any:
    tree = ast.parse(expr, mode="eval")
    return _SafeExpressionEvaluator(params).visit(tree)

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

class ToolTemplate(BaseTool):
    """A tool dynamically constructed from a TOML template definition."""

    tool_id: str

    def __init__(self, template_data: Dict[str, Any]) -> None:
        self._data = template_data
        self.tool_id = template_data.get("name", "template")
        self._name = template_data.get("name", "template")
        self._description = template_data.get("description", "")
        self._parameters = template_data.get("parameters", {})
        self._action = template_data.get("action", {})

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description=self._description,
            parameters=self._parameters,
            category="template",
            metadata={"template": True},
        )

    def execute(self, **params: Any) -> ToolResult:
        action_type = self._action.get("type", "python")

        try:
            if action_type == "python":
                return self._execute_python(params)
            elif action_type == "shell":
                return self._execute_shell(params)
            elif action_type == "transform":
                return self._execute_transform(params)
            else:
                return ToolResult(
                    tool_name=self._name,
                    content=f"Unknown action type: {action_type}",
                    success=False,
                )
        except Exception as exc:
            return ToolResult(
                tool_name=self._name,
                content=f"Template execution error: {exc}",
                success=False,
            )

    def _execute_python(self, params: Dict[str, Any]) -> ToolResult:
        """Execute a Python expression."""
        expr = self._action.get("expression", "")
        if not expr:
            return ToolResult(
                tool_name=self._name,
                content="No expression defined.",
                success=False,
            )
        result = _safe_eval_template_expression(expr, params)
        return ToolResult(
            tool_name=self._name,
            content=str(result),
            success=True,
        )

    def _execute_shell(self, params: Dict[str, Any]) -> ToolResult:
        """Execute a shell command (requires code:execute capability)."""
        cmd = self._action.get("command", "")
        if not cmd:
            return ToolResult(
                tool_name=self._name,
                content="No command defined.",
                success=False,
            )
        for key, val in params.items():
            safe_val = str(val)
            if _SHELL_VALUE_REJECT.search(safe_val):
                return ToolResult(
                    tool_name=self._name,
                    content=f"Rejected unsafe shell parameter: {key}",
                    success=False,
                )
            cmd = cmd.replace(f"{{{key}}}", shlex.quote(safe_val))
        # Split into args list to avoid shell injection
        args = shlex.split(cmd)
        if args and Path(args[0]).name.lower() in _SHELL_INTERPRETERS:
            return ToolResult(
                tool_name=self._name,
                content="Shell interpreters are not allowed in template commands.",
                success=False,
            )
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout or result.stderr
        return ToolResult(
            tool_name=self._name,
            content=output.strip(),
            success=result.returncode == 0,
        )

    def _execute_transform(self, params: Dict[str, Any]) -> ToolResult:
        """Execute a data transformation."""
        transform = self._action.get("transform", "identity")
        input_val = params.get("input", "")
        if transform == "upper":
            return ToolResult(
                tool_name=self._name,
                content=str(input_val).upper(),
                success=True,
            )
        elif transform == "lower":
            return ToolResult(
                tool_name=self._name,
                content=str(input_val).lower(),
                success=True,
            )
        elif transform == "length":
            return ToolResult(
                tool_name=self._name,
                content=str(len(str(input_val))),
                success=True,
            )
        elif transform == "reverse":
            return ToolResult(
                tool_name=self._name,
                content=str(input_val)[::-1],
                success=True,
            )
        elif transform == "json_pretty":
            try:
                parsed = json.loads(str(input_val))
                return ToolResult(
                    tool_name=self._name,
                    content=json.dumps(
                        parsed,
                        indent=2,
                    ),
                    success=True,
                )
            except json.JSONDecodeError as exc:
                return ToolResult(
                    tool_name=self._name,
                    content=f"Invalid JSON: {exc}",
                    success=False,
                )
        else:
            return ToolResult(
                tool_name=self._name,
                content=str(input_val),
                success=True,
            )

def load_template(path: str | Path) -> ToolTemplate:
    """Load a single tool template from a TOML file."""
    path = Path(path)
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    tool_data = data.get("tool", data)
    return ToolTemplate(tool_data)

def discover_templates(
    directory: Optional[str | Path] = None,
) -> List[ToolTemplate]:
    """Discover all TOML templates in a directory."""
    if directory is None:
        directory = Path(__file__).parent / "builtin"
    directory = Path(directory)
    if not directory.exists():
        return []
    templates = []
    for path in sorted(directory.glob("*.toml")):
        try:
            templates.append(load_template(path))
        except Exception as exc:
            logger.debug("Skipping unparseable template {}: {}", path, exc)
    return templates

__all__ = ["ToolTemplate", "discover_templates", "load_template"]
