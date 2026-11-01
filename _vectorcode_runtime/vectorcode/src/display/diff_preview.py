"""ANSI-colored diff preview for file edits and patches."""
import difflib
import sys
from dataclasses import dataclass, field
from typing import Optional


from loguru import logger

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_RED    = "\x1b[31m"
_GREEN  = "\x1b[32m"
_CYAN   = "\x1b[36m"
_YELLOW = "\x1b[33m"
_DIM    = "\x1b[2m"
_BOLD   = "\x1b[1m"
_RESET  = "\x1b[0m"


def _red(s: str) -> str:    return f"{_RED}{s}{_RESET}"
def _green(s: str) -> str:  return f"{_GREEN}{s}{_RESET}"
def _cyan(s: str) -> str:   return f"{_CYAN}{s}{_RESET}"
def _yellow(s: str) -> str: return f"{_YELLOW}{s}{_RESET}"
def _dim(s: str) -> str:    return f"{_DIM}{s}{_RESET}"
def _bold(s: str) -> str:   return f"{_BOLD}{s}{_RESET}"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class DiffStats:
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0


# ---------------------------------------------------------------------------
# Core rendering
# ---------------------------------------------------------------------------

def render_diff(
    old_content: str,
    new_content: str,
    filename: str = "",
    *,
    context_lines: int = 3,
    max_lines: int = 200,
) -> str:
    """
    Render a unified diff between *old_content* and *new_content* with ANSI color.

    Lines starting with '+' → green
    Lines starting with '-' → red
    Lines starting with '@@' → cyan
    Header lines (---/+++) → yellow + bold
    Context lines → dim

    Truncates to *max_lines* with a notice if longer.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    from_label = f"a/{filename}" if filename else "before"
    to_label   = f"b/{filename}" if filename else "after"

    raw_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=from_label,
            tofile=to_label,
            n=context_lines,
        )
    )

    if not raw_lines:
        return _dim("(no changes)")

    colored: list[str] = []
    for line in raw_lines:
        # Strip trailing newline for display; re-add at end of each line
        stripped = line.rstrip("\n")
        if stripped.startswith("--- ") or stripped.startswith("+++ "):
            colored.append(_bold(_yellow(stripped)))
        elif stripped.startswith("@@"):
            colored.append(_cyan(stripped))
        elif stripped.startswith("+"):
            colored.append(_green(stripped))
        elif stripped.startswith("-"):
            colored.append(_red(stripped))
        else:
            colored.append(_dim(stripped))

    truncated, was_truncated = _truncate_lines("\n".join(colored), max_lines)
    if was_truncated:
        truncated += f"\n{_dim(f'… ({len(colored) - max_lines} more lines truncated)')}"
    return truncated


def render_patch(
    patch_text: str,
    *,
    max_lines: int = 200,
) -> str:
    """
    Render an already-computed unified diff patch string with ANSI color.
    Same coloring rules as render_diff.
    """
    if not patch_text.strip():
        return _dim("(empty patch)")

    colored: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            colored.append(_bold(_yellow(line)))
        elif line.startswith("@@"):
            colored.append(_cyan(line))
        elif line.startswith("+"):
            colored.append(_green(line))
        elif line.startswith("-"):
            colored.append(_red(line))
        else:
            colored.append(_dim(line))

    truncated, was_truncated = _truncate_lines("\n".join(colored), max_lines)
    if was_truncated:
        truncated += f"\n{_dim(f'… ({len(colored) - max_lines} more lines truncated)')}"
    return truncated


def diff_stats(old_content: str, new_content: str) -> DiffStats:
    """Count additions and deletions in a diff."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    stats = DiffStats()
    for line in difflib.unified_diff(old_lines, new_lines, n=0):
        if line.startswith("+") and not line.startswith("+++"):
            stats.additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            stats.deletions += 1
    if stats.additions or stats.deletions:
        stats.changed_files = 1
    return stats


# ---------------------------------------------------------------------------
# Tool-level preview builders
# ---------------------------------------------------------------------------

def build_tool_preview(
    tool_name: str,
    args: dict,
    result: Optional[str] = None,
) -> str:
    """
    Build a human-readable, ANSI-colored preview of a tool call and its result.

    For write_file / edit_file  → colored diff
    For read_file               → first 20 lines with line numbers
    For bash                    → command in a box + truncated result
    For git_commit              → commit message + stats
    Others                      → tool name + args summary
    """
    tool_lower = tool_name.lower()

    if tool_lower in ("write_file", "edit_file"):
        return _preview_file_edit(tool_name, args, result)

    if tool_lower == "read_file":
        return _preview_read_file(args, result)

    if tool_lower == "bash":
        return _preview_bash(args, result)

    if tool_lower == "git_commit":
        return _preview_git_commit(args, result)

    # Generic fallback
    lines = [_bold(_cyan(f"▸ {tool_name}"))]
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 120:
            v_str = v_str[:120] + "…"
        lines.append(_dim(f"  {k}: ") + v_str)
    if result:
        lines.append(_dim("  result: ") + format_tool_result(tool_name, result))
    return "\n".join(lines)


def _preview_file_edit(tool_name: str, args: dict, result: Optional[str]) -> str:
    old = args.get("old_content", args.get("before", ""))
    new = args.get("new_content", args.get("after", result or ""))
    filename = args.get("path", args.get("file_path", args.get("filename", "")))
    header = _bold(_yellow(f"▸ {tool_name}")) + (f"  {_dim(filename)}" if filename else "")
    diff = render_diff(old, new, filename=str(filename))
    return f"{header}\n{diff}"


def _preview_read_file(args: dict, result: Optional[str]) -> str:
    filename = args.get("path", args.get("file_path", args.get("filename", "")))
    header = _bold(_cyan(f"▸ read_file")) + (f"  {_dim(str(filename))}" if filename else "")
    if not result:
        return header + "\n" + _dim("(no content)")
    lines = result.splitlines()[:20]
    numbered = "\n".join(
        f"{_dim(str(i + 1).rjust(4))} {_DIM}|{_RESET} {line}"
        for i, line in enumerate(lines)
    )
    suffix = _dim(f"\n  … ({len(result.splitlines()) - 20} more lines)") if len(result.splitlines()) > 20 else ""
    return f"{header}\n{numbered}{suffix}"


def _preview_bash(args: dict, result: Optional[str]) -> str:
    command = str(args.get("command", args.get("cmd", "?")))
    # Box drawing
    width = min(max(len(command) + 4, 20), 80)
    top    = _cyan("╔═") + _bold(_cyan(" bash ")) + _cyan("═" * max(width - 8, 2) + "╗")
    middle = _cyan("║ ") + command + _cyan(" ║")
    bottom = _cyan("╚" + "═" * (width - 2) + "╝")
    box = f"{top}\n{middle}\n{bottom}"
    if result:
        result_preview = format_tool_result("bash", result, max_lines=30)
        return f"{box}\n{result_preview}"
    return box


def _preview_git_commit(args: dict, result: Optional[str]) -> str:
    msg = args.get("message", args.get("msg", ""))
    header = _bold(_yellow("▸ git_commit"))
    lines = [header]
    if msg:
        lines.append(_green(f"  📦 {msg}"))
    if result:
        lines.append(format_tool_result("git_commit", result, max_lines=10))
    return "\n".join(lines)


def format_tool_result(tool_name: str, result: str, *, max_lines: int = 50) -> str:
    """
    Format a tool result for display. Truncates long outputs.
    Adds ANSI styling appropriate to the tool.
    """
    if not result:
        return _dim("(empty result)")

    truncated, was_truncated = _truncate_lines(result, max_lines)
    total_lines = len(result.splitlines())

    tool_lower = tool_name.lower()

    if tool_lower == "bash":
        styled = _dim(truncated)
    elif tool_lower in ("write_file", "edit_file"):
        styled = _green(truncated)
    elif tool_lower == "read_file":
        styled = truncated  # already formatted with line numbers upstream
    elif "error" in result.lower()[:80]:
        styled = _red(truncated)
    else:
        styled = _dim(truncated)

    if was_truncated:
        styled += f"\n{_dim(f'… ({total_lines - max_lines} more lines)')}"
    return styled


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _truncate_lines(text: str, max_lines: int) -> tuple[str, bool]:
    """Return (truncated_text, was_truncated)."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, False
    return "\n".join(lines[:max_lines]), True


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("[VECTOR][diff_preview] smoke test starting")

    # render_diff
    old = "hello\nworld\nfoo\n"
    new = "hello\nearth\nfoo\n"
    diff_out = render_diff(old, new, "test.txt")
    assert "earth" in diff_out, "expected 'earth' in diff output"
    assert "\x1b[" in diff_out, "expected ANSI codes in diff output"
    logger.info(f"[VECTOR][diff_preview] render_diff:\n{diff_out}")

    # render_patch — use the raw diff text without ANSI
    raw_patch = "\n".join(
        list(difflib.unified_diff(old.splitlines(keepends=True),
                                  new.splitlines(keepends=True),
                                  fromfile="a/test.txt", tofile="b/test.txt"))
    )
    patch_out = render_patch(raw_patch)
    assert "earth" in patch_out, "expected 'earth' in patch output"

    # diff_stats
    stats = diff_stats(old, new)
    assert stats.additions == 1 and stats.deletions == 1, f"stats mismatch: {stats}"
    assert stats.changed_files == 1

    # build_tool_preview — bash
    bash_preview = build_tool_preview("bash", {"command": "ls -la"}, "total 42\ndrwxr-xr-x 2 user group 4096 .")
    assert "bash" in bash_preview, "expected 'bash' in preview"
    assert "ls -la" in bash_preview, "expected command in preview"
    logger.info(f"[VECTOR][diff_preview] bash preview:\n{bash_preview}")

    # build_tool_preview — read_file
    read_preview = build_tool_preview("read_file", {"path": "core/config.py"}, "line1\nline2\nline3")
    assert "read_file" in read_preview

    # format_tool_result truncation
    long_result = "\n".join(str(i) for i in range(200))
    truncated = format_tool_result("bash", long_result, max_lines=30)
    assert "more lines" in truncated

    sys.stdout.buffer.write(b"\xe2\x9c\x85 diff_preview.py OK\n")
    sys.stdout.buffer.flush()
