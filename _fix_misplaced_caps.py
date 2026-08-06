"""Fix misplaced self.capabilities inside super().__init__() calls.

Pattern:
    super().__init__(agent_id="...",
    self.capabilities = [...]       <-- WRONG: inside the call
                     name="...", district="...")

Fix:
    super().__init__(agent_id="...",
                     name="...", district="...")
    self.capabilities = [...]       <-- RIGHT: after the call
"""
from pathlib import Path

ROOT = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase")
fixed_files = []

for py_file in sorted(ROOT.rglob("districts/**/*.py")):
    content = py_file.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    # Find lines with self.capabilities that are inside super().__init__() calls
    new_lines = []
    saved_caps = []  # list of (cap_line, insert_after_index)
    in_init = False
    init_depth = 0
    init_start = -1

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track when we enter a super().__init__() call
        if "super().__init__(" in line:
            in_init = True
            init_start = i
            init_depth = line.count("(") - line.count(")")
            new_lines.append(line)
            if init_depth <= 0:
                in_init = False
            continue

        if in_init:
            init_depth += line.count("(") - line.count(")")

            # Check if this line is a misplaced self.capabilities
            if stripped.startswith("self.capabilities = ["):
                # Save it — we'll insert it after super().__init__() closes
                saved_caps.append((line, i))
                continue  # skip adding this line

            new_lines.append(line)
            if init_depth <= 0:
                in_init = False
                # Insert any saved capabilities lines right here
                for cap_line, _ in saved_caps:
                    new_lines.append(cap_line)
                saved_caps = []
        else:
            new_lines.append(line)

    # If we still have unsaved caps (shouldn't happen), add them at end
    for cap_line, _ in saved_caps:
        new_lines.append(cap_line)

    new_content = "\n".join(new_lines)
    if new_content != content:
        py_file.write_text(new_content, encoding="utf-8")
        fixed_files.append(str(py_file.relative_to(ROOT)))

print(f"Fixed {len(fixed_files)} files:")
for f in fixed_files:
    print(f"  {f}")
