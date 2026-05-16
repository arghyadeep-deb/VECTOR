"""Fix Hermes/Jarvis in method docstrings and remaining string literals."""
import pathlib, re, ast

ROOT = pathlib.Path(__file__).parent.parent
vc = ROOT / "vectorcode/src"

# These replace in ALL text (including method docstrings)
ALL_REPLACEMENTS = [
    # Hermes format/trajectory references
    ("Hermes trajectory format", "VECTOR trajectory format"),
    ("Hermes format (from/value", "VECTOR format (from/value"),
    ("Hermes-format", "VECTOR-format"),
    ("to Hermes trajectory format", "to VECTOR trajectory format"),
    ("in Hermes format", "in VECTOR format"),
    ("Hermes trajectory", "VECTOR trajectory"),
    ("Hermes format", "VECTOR format"),
    ("Hermes Agent's built-in", "VECTOR built-in"),
    ("Hermes-Agent's", "VECTOR"),
    # jarvis CLI command names in strings (all remaining)
    ("jarvis channels", "vector channels"),
    ("jarvis config", "vector config"),
    ("jarvis-direct", "vector-direct"),
    ("jarvis-agent", "vector-agent"),
    ("jarvis agents", "vector agents"),
    ("jarvis mine", "vector mine"),
    ("jarvis skill", "vector skill"),
    ("jarvis auth", "vector auth"),
    ("jarvis bench", "vector bench"),
    ("jarvis init", "vector init"),
    ("jarvis quickstart", "vector quickstart"),
    ("jarvis workflow", "vector workflow"),
    ("jarvis chat", "vector chat"),
    ("jarvis digest", "vector digest"),
    ("jarvis registry", "vector registry"),
    ("jarvis scheduler", "vector scheduler"),
    # Remaining Hermes in docstrings
    ("Hermes entry point", "VECTOR entry point"),
    ("every Hermes entry", "every VECTOR entry"),
    ("Hermes home directory", "VECTOR home directory"),
    ("Hermes logging", "VECTOR logging"),
    ("Hermes session", "VECTOR session"),
    ("Hermes, keep", "VECTOR, keep"),
    ("Hermes request", "VECTOR request"),
    ("Hermes static user-facing", "VECTOR static user-facing"),
    ("by Hermes itself", "by VECTOR itself"),
    ("built on Hermes Agent", "built on VECTOR"),
    ("extend an existing Hermes", "extend an existing VECTOR"),
    ("Hermes features", "VECTOR features"),
    ("for Hermes.", "for VECTOR."),
    ("Configuration for a single skill source (VECTOR, OpenClaw, GitHub)",
     "Configuration for a single skill source (VECTOR, OpenClaw, GitHub)"),  # no-op
    ("skill source (Hermes", "skill source (VECTOR"),
    ("Hermes to a local Chrome", "VECTOR to a local Chrome"),
    ("attaching Hermes to", "attaching VECTOR to"),
    ("Nous can attribute usage to Hermes Agent", "Nous can attribute usage to VECTOR"),
    ("Hermes Agent and bucket", "VECTOR and bucket"),
    ("Hermes Agent's", "VECTOR's"),
    ("Hermes Agent", "VECTOR"),
    ("with Hermes.", "with VECTOR."),
    ("for Hermes,", "for VECTOR,"),
    ("Hermes never", "VECTOR never"),
    ("Hermes-", "VECTOR-"),
    ("(Hermes)", "(VECTOR)"),
    (" Hermes ", " VECTOR "),
]

fixed = []
errors = []

for f in vc.rglob("*.py"):
    if "release.py" in f.name:
        continue
    src = f.read_text(encoding="utf-8", errors="replace")
    orig = src
    for old, new in ALL_REPLACEMENTS:
        src = src.replace(old, new)
    if src != orig:
        try:
            ast.parse(src)
            f.write_text(src, encoding="utf-8")
            fixed.append(str(f.relative_to(ROOT)))
        except SyntaxError as e:
            errors.append(f"{f.name}: {e}")

print(f"Fixed {len(fixed)} files")
if errors:
    print(f"Errors: {errors}")
