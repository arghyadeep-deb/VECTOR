"""Fix remaining jarvis CLI strings and Hermes in code/method docstrings."""
import pathlib, re, ast

ROOT = pathlib.Path(__file__).parent.parent
vc = ROOT / "vectorcode/src"

REPLACEMENTS = [
    ("jarvis agents create", "vector agents create"),
    ("jarvis mine models", "vector mine models"),
    ("jarvis mine doctor", "vector mine doctor"),
    ("jarvis mine start", "vector mine start"),
    ("jarvis mine init", "vector mine init"),
    ("jarvis init", "vector init"),
    ("jarvis quickstart", "vector quickstart"),
    ("jarvis skill install", "vector skill install"),
    ("jarvis bench", "vector bench"),
    ("jarvis auth generate-key", "vector auth generate-key"),
    ("jarvis registry", "vector registry"),
    ("jarvis scheduler", "vector scheduler"),
    ("jarvis workflow", "vector workflow"),
    ("jarvis chat", "vector chat"),
    ("jarvis digest", "vector digest"),
    ("Run jarvis", "Run vector"),
    ("run jarvis", "run vector"),
    ('"jarvis"', '"vector"'),
    ("'jarvis'", "'vector'"),
    ("sender=\"jarvis\"", 'sender="vector"'),
    ("Hermes Trajectory Format", "VECTOR Trajectory Format"),
    ("Hermes-Agent trajectory", "VECTOR trajectory"),
    ("Hermes-Agent format", "VECTOR format"),
    ("Hermes-Agent built-in", "VECTOR built-in"),
    ("Hermes-Agent/graph-client", "VECTOR-Agent/graph-client"),
    ("Hermes-Agent", "VECTOR"),
    ("Configure the Hermes logging subsystem", "Configure the VECTOR logging subsystem"),
    ("Override for the Hermes home directory", "Override for the VECTOR home directory"),
    ("upgrade Hermes, keep", "upgrade VECTOR, keep"),
    ("one Hermes session", "one VECTOR session"),
    ("A Hermes session", "A VECTOR session"),
    ("a Hermes session", "a VECTOR session"),
    ("(Hermes Agent, OpenClaw)", "(VECTOR, OpenClaw)"),
    ("Hermes Agent backends.", "VECTOR backends."),
    ("Hermes Agent often need", "VECTOR plugins often need"),
    ("opt-in Hermes Agent backends", "opt-in VECTOR backends"),
    ("Many Hermes features", "Many VECTOR features"),
    ("Hermes needs", "VECTOR needs"),
    ("Real Hermes Agent (Nous Research) via subprocess", "Real VECTOR agent via subprocess"),
    ("Mini-SWE Runner with Hermes", "Mini-SWE Runner with VECTOR"),
    ("Hermes Agent's built-in", "VECTOR built-in"),
    ("print(\"🚀 Mini-SWE Runner", 'print("🚀 Mini-SWE Runner'),
]

fixed = []
for f in vc.rglob("*.py"):
    if "release.py" in f.name:
        continue
    src = f.read_text(encoding="utf-8", errors="replace")
    orig = src
    for old, new in REPLACEMENTS:
        src = src.replace(old, new)
    # backtick jarvis refs
    src = re.sub(r"`jarvis\s+", "`vector ", src)
    if src != orig:
        try:
            ast.parse(src)
            f.write_text(src, encoding="utf-8")
            n = sum(1 for a, b in zip(orig.splitlines(), src.splitlines()) if a != b)
            fixed.append((str(f.relative_to(ROOT)), n))
        except SyntaxError as e:
            print(f"SYNTAX ERROR {f.name}: {e}")

print(f"Fixed {len(fixed)} files:")
for fp, n in fixed:
    print(f"  {fp} ({n} lines changed)")
