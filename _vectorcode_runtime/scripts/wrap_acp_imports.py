"""
Wrap all bare 'from acp import' / 'import acp' in coding_assistant/acp/
with try/except blocks so they don't crash when the ACP protocol package
isn't installed.

The acp/ subpackage uses the Agent Communication Protocol library which
requires a specific private build. The code is retained for when the
correct package becomes available.
"""
from pathlib import Path
import re

ACP_DIR = Path("core/coding_assistant/acp")

STUB_HEADER = '''# [VECTOR] acp protocol package not installed — stubs below
# The acp/ subpackage requires the Agent Communication Protocol library.
# Install the correct version when available.
try:
    _acp_available = True
'''

fixed = 0
for f in ACP_DIR.rglob("*.py"):
    content = f.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)

    # Collect all bare acp import blocks (not from core.coding_assistant.acp)
    has_bare_acp = any(
        ("from acp " in line or "import acp" in line or "from acp." in line)
        and "coding_assistant.acp" not in line
        and not line.strip().startswith("#")
        for line in lines
    )

    if not has_bare_acp:
        continue

    # Already wrapped?
    if "try:\n" in content and "_acp_available" in content:
        continue

    # Build new file: wrap all bare acp imports
    new_lines = []
    i = 0
    import_block = []
    collected_symbols = []
    in_import_block = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        is_bare_acp = (
            ("from acp " in line or "import acp" in line or "from acp." in line)
            and "coding_assistant.acp" not in line
            and not stripped.startswith("#")
            and (stripped.startswith("from ") or stripped.startswith("import "))
        )

        if is_bare_acp:
            import_block.append(line)
            # Handle multi-line
            if "(" in line and ")" not in line:
                i += 1
                while i < len(lines):
                    import_block.append(lines[i])
                    if ")" in lines[i]:
                        break
                    i += 1
        else:
            if import_block:
                # Emit try/except around the collected imports
                new_lines.append("try:\n")
                for imp in import_block:
                    new_lines.append("    " + imp)
                new_lines.append("except (ImportError, AttributeError):\n")
                new_lines.append("    pass  # acp protocol package not installed\n")
                import_block = []
            new_lines.append(line)

        i += 1

    if import_block:
        new_lines.append("try:\n")
        for imp in import_block:
            new_lines.append("    " + imp)
        new_lines.append("except (ImportError, AttributeError):\n")
        new_lines.append("    pass  # acp protocol package not installed\n")

    new_content = "".join(new_lines)
    if new_content != content:
        f.write_text(new_content, encoding="utf-8")
        fixed += 1
        print(f"  Wrapped: {f.relative_to(ACP_DIR)}")

print(f"\nWrapped {fixed} files in acp/")
