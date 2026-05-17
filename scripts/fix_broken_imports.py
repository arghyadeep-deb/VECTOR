"""Fix broken imports caused by removing useless modules."""
import re
from pathlib import Path

CA = Path("core/coding_assistant")
RE = Path("core/research_engine")

fixes = 0


def comment_import_block(path: Path, start_patterns: list[str]) -> int:
    """Comment out import lines matching any start pattern (handles multi-line imports)."""
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)
    new_lines = []
    i = 0
    changed = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        matched = any(p in line for p in start_patterns)
        if matched and (stripped.startswith("from ") or stripped.startswith("import ")):
            # Comment out this line
            new_lines.append("# [VECTOR] removed: " + line)
            changed += 1
            # If it's a multi-line import (ends with comma or backslash, or open paren)
            if "(" in line and ")" not in line:
                # consume until closing paren
                i += 1
                while i < len(lines):
                    new_lines.append("# [VECTOR] removed: " + lines[i])
                    changed += 1
                    if ")" in lines[i]:
                        break
                    i += 1
        else:
            new_lines.append(line)
        i += 1
    if changed:
        path.write_text("".join(new_lines), encoding="utf-8")
    return changed


# ── Fix coding_assistant broken imports ───────────────────────────────────────

# acp/acp_agent_loop.py — data_retention, proxy_setup
n = comment_import_block(
    CA / "acp/acp_agent_loop.py",
    ["data_retention", "proxy_setup"]
)
fixes += n
print(f"acp/acp_agent_loop.py: commented {n} import lines")

# acp/entrypoint.py — tracing
n = comment_import_block(
    CA / "acp/entrypoint.py",
    ["core.tracing", ".tracing"]
)
fixes += n
print(f"acp/entrypoint.py: commented {n} import lines")

# acp/utils.py — proxy_setup
n = comment_import_block(
    CA / "acp/utils.py",
    ["proxy_setup"]
)
fixes += n
print(f"acp/utils.py: commented {n} import lines")

# cli/cli.py — tracing
n = comment_import_block(
    CA / "cli/cli.py",
    ["core.tracing", ".tracing"]
)
fixes += n
print(f"cli/cli.py: commented {n} import lines")

# cli/commands.py — plan_offer
n = comment_import_block(
    CA / "cli/commands.py",
    ["plan_offer"]
)
fixes += n
print(f"cli/commands.py: commented {n} import lines")

# core/agent_loop.py — teleport, tracing
n = comment_import_block(
    CA / "core/agent_loop.py",
    ["teleport", "tracing"]
)
fixes += n
print(f"core/agent_loop.py: commented {n} import lines")

# core/output_formatters.py — teleport
n = comment_import_block(
    CA / "core/output_formatters.py",
    ["teleport"]
)
fixes += n
print(f"core/output_formatters.py: commented {n} import lines")

# core/programmatic.py — teleport
n = comment_import_block(
    CA / "core/programmatic.py",
    ["teleport"]
)
fixes += n
print(f"core/programmatic.py: commented {n} import lines")

# ── Fix research_engine broken imports ────────────────────────────────────────

# error_handling/error_reporter.py — notifications
n = comment_import_block(
    RE / "error_handling/error_reporter.py",
    ["notifications"]
)
fixes += n
print(f"error_handling/error_reporter.py: commented {n} import lines")

# advanced_search_system/strategies/mcp_strategy.py — mcp.client
n = comment_import_block(
    RE / "advanced_search_system/strategies/mcp_strategy.py",
    ["research_engine.mcp", "mcp.client"]
)
fixes += n
print(f"advanced_search_system/strategies/mcp_strategy.py: commented {n} import lines")

print(f"\nTotal import lines fixed: {fixes}")

# ── Verify no more broken imports ─────────────────────────────────────────────
deleted_ca = ["teleport", "plan_offer", "update_notifier", "data_retention",
              "proxy_setup", "tracing"]
deleted_re = ["notifications", "research_engine.mcp", ".mcp import", "research_scheduler"]

remaining = []
for f in CA.rglob("*.py"):
    c = f.read_text(encoding="utf-8", errors="replace")
    for line in c.splitlines():
        s = line.strip()
        if (s.startswith("from ") or s.startswith("import ")) and any(d in s for d in deleted_ca):
            remaining.append(f"CA {f.relative_to(CA)}: {s}")

for f in RE.rglob("*.py"):
    c = f.read_text(encoding="utf-8", errors="replace")
    for line in c.splitlines():
        s = line.strip()
        if (s.startswith("from ") or s.startswith("import ")) and any(d in s for d in deleted_re):
            remaining.append(f"RE {f.relative_to(RE)}: {s}")

print(f"Remaining broken imports: {len(remaining)} (want 0)")
for r in remaining[:10]:
    print(f"  {r}")
