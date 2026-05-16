"""Final pass: fix all remaining Hermes/jarvis references."""
import pathlib, re, ast

ROOT = pathlib.Path(__file__).parent.parent
vc = ROOT / "vectorcode/src"

fixed = []
for f in vc.rglob("*.py"):
    if "release.py" in f.name:
        continue
    src = f.read_text(encoding="utf-8", errors="replace")
    orig = src

    # Hermes possessive and variants
    src = src.replace("Hermes'", "VECTOR's")
    src = src.replace("Hermes' ", "VECTOR's ")
    src = src.replace(" Hermes,", " VECTOR,")
    src = src.replace(" Hermes.", " VECTOR.")
    src = src.replace(" Hermes\n", " VECTOR\n")
    src = src.replace("mirrors Hermes", "mirrors VECTOR")
    src = src.replace("per-task override Hermes", "per-task override VECTOR")
    src = src.replace("configured by Hermes", "configured by VECTOR")
    src = src.replace("by Hermes itself", "by VECTOR itself")
    src = src.replace("Hermes' own", "VECTOR's own")

    # jarvis CLI command examples — catch ALL remaining
    src = re.sub(r'\bjarvis\b', 'vector', src, flags=re.IGNORECASE)

    if src != orig:
        try:
            ast.parse(src)
            f.write_text(src, encoding="utf-8")
            fixed.append(str(f.relative_to(ROOT)))
        except SyntaxError as e:
            print(f"SYNTAX ERROR {f.name}: {e}")

print(f"Fixed {len(fixed)} files")
