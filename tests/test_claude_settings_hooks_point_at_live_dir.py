"""Regression guard for the .claude/hooks/ vs vectorcode/hooks/ divergence
(docs/OPEN_ISSUES.md item 132; post-audit improvement plan gap 10).

vectorcode/hooks/ is a dormant historical snapshot that looks identical to
.claude/hooks/ by filename -- a fix applied only to one of them is silently
inert for this Claude Code session. This was discovered the hard way: a
real secret-commit vulnerability stayed "fixed" in the wrong tree for an
entire audit session before anyone checked which path .claude/settings.json
actually invokes.

This test parses the real settings.json and fails if any configured hook
command ever stops pointing at .claude/hooks/ -- so a future edit that
accidentally repoints a hook at vectorcode/hooks/ (or anywhere else) is
caught immediately instead of silently shipping a dead control.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".claude" / "settings.json"

_COMMAND_PATH_RE = re.compile(r'\$CLAUDE_PROJECT_DIR[/\\](\.claude[/\\]hooks[/\\][^"\s]+\.py)')


def _iter_hook_commands():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    for event_name, matchers in hooks.items():
        for matcher in matchers:
            for hook in matcher.get("hooks", []):
                if hook.get("type") == "command":
                    yield event_name, hook["command"]


def test_settings_json_exists_and_has_hooks():
    assert SETTINGS.exists(), f"missing {SETTINGS}"
    commands = list(_iter_hook_commands())
    assert len(commands) >= 1, "expected at least one configured hook command"


def test_every_python_hook_command_points_at_live_claude_hooks_dir():
    violations = []
    for event_name, command in _iter_hook_commands():
        if ".py" not in command:
            continue  # non-Python hook commands (e.g. shell one-liners) are out of scope
        match = _COMMAND_PATH_RE.search(command)
        if not match:
            violations.append((event_name, command))
            continue
        relative = match.group(1).replace("\\", "/")
        hook_file = ROOT / relative
        if not hook_file.exists():
            violations.append((event_name, f"{command} -> resolved path does not exist: {hook_file}"))

    assert not violations, (
        "Found hook command(s) not pointing at an existing file under .claude/hooks/:\n"
        + "\n".join(f"  [{event}] {cmd}" for event, cmd in violations)
    )


def test_no_python_hook_command_points_at_the_dormant_vectorcode_copy():
    offenders = [
        (event_name, command)
        for event_name, command in _iter_hook_commands()
        if ".py" in command and "vectorcode" in command.lower() and "hooks" in command.lower()
    ]
    assert not offenders, (
        "A configured hook command points at vectorcode/hooks/ (the dormant "
        f"historical snapshot, see vectorcode/hooks/README.md), not the live "
        f".claude/hooks/ tree: {offenders}"
    )
