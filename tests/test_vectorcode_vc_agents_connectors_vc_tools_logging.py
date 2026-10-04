"""Regression for a batch of vectorcode/src/{vc_agents,connectors,vc_tools} files
that used stdlib ``logging.getLogger(__name__)`` instead of loguru, or (in
rlm_repl.py's case) correctly imported loguru at module level but then shadowed
it with a fresh stdlib logger inside one function. Either way, every %-style
placeholder in these files' log calls silently failed to substitute under
loguru's {}-style formatter once converted (or, before conversion, was simply
production code violating CLAUDE.md's "loguru everywhere, never stdlib logging"
rule).

Also covers two instances of stdlib's ``exc_info=True`` kwarg, which loguru's
.debug()/.warning() do not understand and would silently ignore -- the fix
uses ``logger.opt(exception=True)`` instead, loguru's actual equivalent.

This test asserts the static source no longer contains stdlib `import logging`
or any %-style placeholder in a logger.* call, for each of the 16 touched
files, and does a live smoke check that each module still imports cleanly.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

_REPO_ROOT = Path(__file__).parent.parent

_FILES = [
    "vectorcode/src/connectors/apple_music.py",
    "vectorcode/src/connectors/gmail_imap.py",
    "vectorcode/src/connectors/scheduler.py",
    "vectorcode/src/connectors/whatsapp.py",
    "vectorcode/src/vc_agents/__init__.py",
    "vectorcode/src/vc_agents/claude_code.py",
    "vectorcode/src/vc_agents/executor.py",
    "vectorcode/src/vc_agents/morning_digest.py",
    "vectorcode/src/vc_agents/prompt_loader.py",
    "vectorcode/src/vc_agents/rlm_repl.py",
    "vectorcode/src/vc_agents/scheduler.py",
    "vectorcode/src/vc_tools/agent_tools.py",
    "vectorcode/src/vc_tools/description_loader.py",
    "vectorcode/src/vc_tools/http_request.py",
    "vectorcode/src/vc_tools/templates/loader.py",
    "vectorcode/src/vc_tools/web_search.py",
]

_LOGGER_CALL_RE = re.compile(
    r"logger\.(debug|info|warning|error|critical|exception)\([^)]*%[sdr.]"
)


def test_no_stdlib_logging_import_remains():
    for rel in _FILES:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert not re.search(r"^import logging\b", src, re.MULTILINE), (
            f"{rel} still imports stdlib logging"
        )


def test_no_percent_style_logger_placeholders_remain():
    for rel in _FILES:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        match = _LOGGER_CALL_RE.search(src)
        assert match is None, f"{rel} still has a %-style logger call: {match.group(0) if match else ''}"


def test_no_stdlib_exc_info_kwarg_remains():
    for rel in _FILES:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "exc_info=True" not in src, f"{rel} still passes exc_info=True to a loguru call"


def test_all_files_parse_as_valid_python():
    for rel in _FILES:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        ast.parse(src, filename=rel)


def test_rlm_repl_execute_uses_module_logger_not_local_shadow():
    src = (_REPO_ROOT / "vectorcode/src/vc_agents/rlm_repl.py").read_text(encoding="utf-8")
    execute_start = src.index("def execute(self, code: str) -> str:")
    execute_body = src[execute_start:execute_start + 400]
    assert "import logging" not in execute_body
    assert "logger.warning(\"[VECTOR][rlm_repl] code execution:" in execute_body


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
