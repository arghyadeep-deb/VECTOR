"""Regression tests for shell-hook consent persistence."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import shell_hooks


def test_allowlist_rejects_script_modified_after_approval(tmp_path, monkeypatch) -> None:
    script = tmp_path / "approved_hook.py"
    script.write_text("print('safe')\n", encoding="utf-8")
    command = f'python "{script}"'
    approved_mtime = shell_hooks.script_mtime_iso(command)
    allowlist = tmp_path / shell_hooks.ALLOWLIST_FILENAME
    allowlist.write_text(
        json.dumps(
            {
                "approvals": [
                    {
                        "event": "pre_tool_call",
                        "command": command,
                        "script_mtime_at_approval": approved_mtime,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(shell_hooks, "allowlist_path", lambda: allowlist)
    stat = script.stat()
    script.write_text("print('changed')\n", encoding="utf-8")
    os.utime(script, (stat.st_atime, stat.st_mtime + 2))

    assert shell_hooks._is_allowlisted("pre_tool_call", command) is False
