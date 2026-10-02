"""Standing regression guard for the systemic bug found across
vectorcode/src/tools/ during the Phase 3 whole-repo audit: a file imports
`from loguru import logger` (often the import itself sitting inert inside
the module docstring) but then shadows it with
`logger = logging.getLogger(__name__)`, leaving every logger call in that
file silently using stdlib `%s`/`%d` placeholders under loguru's own `{}`
formatter. 23 files fixed this cycle (4 in an earlier slice, 19 in this
one) -- this test locks in that none of them regress, and gives any new
file added to this list in the future the same real-depth check rather
than waiting for the next whole-repo sweep to notice it by hand.
"""
import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_ROOT = Path(__file__).resolve().parent.parent / "vectorcode" / "src" / "tools"

_FIXED_FILES = [
    "feishu_doc_tool.py", "managed_tool_gateway.py", "environments/ssh.py",
    "video_generation_tool.py", "tirith_security.py",
    "browser_camofox.py", "checkpoint_manager.py", "computer_use/cua_backend.py",
    "discord_tool.py", "environments/daytona.py", "environments/docker.py",
    "environments/managed_modal.py", "environments/modal.py",
    "environments/vercel_sandbox.py", "feishu_drive_tool.py",
    "image_generation_tool.py", "lazy_deps.py", "mcp_oauth.py", "memory_tool.py",
    "skill_manager_tool.py", "skill_usage.py", "skills_sync.py", "vision_tools.py",
    "yuanbao_tools.py",
]

_PLACEHOLDER_RE = re.compile(r'%-?\d*\.?\d*[sdrfx]')


def _has_real_loguru_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "loguru":
            if any(a.name == "logger" for a in node.names):
                return True
    return False


def _has_stdlib_getlogger_reassignment(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "logger"
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "getLogger"):
                return True
    return False


def _logger_calls_with_printf_placeholders(tree: ast.AST) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("info", "warning", "error", "debug", "critical", "exception")):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if _PLACEHOLDER_RE.search(arg.value):
                        hits.append(arg.value)
    return hits


def _logger_calls_with_exc_info_kwarg(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "exc_info":
                    return True
    return False


def test_no_file_has_both_real_loguru_import_and_stdlib_shadow():
    offenders = []
    for rel in _FIXED_FILES:
        path = _ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _has_real_loguru_import(tree) and _has_stdlib_getlogger_reassignment(tree):
            offenders.append(rel)
    assert not offenders, f"loguru import shadowed by stdlib logging.getLogger in: {offenders}"


def test_no_file_has_real_loguru_import_missing():
    missing = []
    for rel in _FIXED_FILES:
        path = _ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not _has_real_loguru_import(tree):
            missing.append(rel)
    assert not missing, f"no real top-level 'from loguru import logger' in: {missing}"


def test_no_logger_call_has_printf_style_placeholder():
    offenders = {}
    for rel in _FIXED_FILES:
        path = _ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = _logger_calls_with_printf_placeholders(tree)
        if hits:
            offenders[rel] = hits
    assert not offenders, f"printf-style (%s/%d) placeholders found in logger calls: {offenders}"


def test_no_logger_call_uses_stdlib_exc_info_kwarg():
    offenders = []
    for rel in _FIXED_FILES:
        path = _ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _logger_calls_with_exc_info_kwarg(tree):
            offenders.append(rel)
    assert not offenders, (
        f"exc_info=True kwarg found (silently ignored by loguru -- use "
        f"logger.opt(exception=True).<level>(...) instead): {offenders}"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
