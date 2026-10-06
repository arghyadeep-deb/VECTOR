"""Full audit of vectorcode/src — stubs, security, wiring, syntax."""
from __future__ import annotations
import ast, re, sys
from pathlib import Path
from collections import defaultdict

vc = Path(__file__).parent.parent / "vectorcode" / "src"
SKIP = "__pycache__"

STUB_PATTERNS = re.compile(
    r"\b(TODO|FIXME|HACK|XXX|PLACEHOLDER)\b"
    r"|raise NotImplementedError"
    r"|^\s*\.\.\.\s*$"
    r"|^\s*pass\s*$",
    re.IGNORECASE | re.MULTILINE
)

SEC_PATTERNS = re.compile(
    r"eval\s*\("
    r"|exec\s*\("
    r"|shell\s*=\s*True"
    r"|os\.system\s*\("
    r"|yaml\.load\s*\([^,)]*\)"
    r"|hashlib\.(md5|sha1)\s*\("
    r"|password\s*=\s*['\"][^'\"]{4,}['\"]"
    r"|secret_key\s*=\s*['\"][^'\"]{4,}['\"]"
)

stubs    : list[tuple[str,int,str]] = []
security : list[tuple[str,int,str]] = []
syntax   : list[tuple[str,int,str]] = []
empty_files: list[str] = []

py_files = sorted(f for f in vc.rglob("*.py") if SKIP not in str(f))
print(f"Scanning {len(py_files)} files...", flush=True)

for py in py_files:
    try:
        text = py.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    rel = str(py.relative_to(vc))
    lines = text.splitlines()

    real = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    if len(real) < 3:
        empty_files.append(rel)
        continue

    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        syntax.append((rel, e.lineno or 0, str(e).split("(")[0].strip()))
        continue

    # Stub check — functions whose body is only pass/raise NotImplementedError
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        non_doc = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if not non_doc:
            continue
        if len(non_doc) == 1:
            s = non_doc[0]
            if isinstance(s, ast.Pass):
                stubs.append((rel, node.lineno, f"def {node.name}(): pass"))
            elif isinstance(s, ast.Raise):
                exc = ast.unparse(s) if hasattr(ast, "unparse") else "raise ..."
                if "NotImplementedError" in exc:
                    stubs.append((rel, node.lineno, f"def {node.name}(): {exc}"))

    # Security check
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if SEC_PATTERNS.search(line):
            if "yaml.load(" in line and "Loader=" in line:
                continue
            if "nosec" in line.lower():
                continue
            security.append((rel, i, stripped[:90]))

print(f"Done. Syntax={len(syntax)} Stubs={len(stubs)} Security={len(security)} Empty={len(empty_files)}")
print()

if syntax:
    print("=== SYNTAX ERRORS (must fix) ===")
    for f, l, m in syntax[:20]:
        print(f"  {f}:{l} — {m}")
    print()

if stubs:
    print("=== STUB / NOTIMPLEMENTED FUNCTIONS ===")
    by_file: dict[str, list] = defaultdict(list)
    for f, l, t in stubs:
        by_file[f].append((l, t))
    for f, items in sorted(by_file.items())[:40]:
        print(f"  {f}")
        for l, t in items[:5]:
            print(f"    :{l} {t}")
    print()

if security:
    print("=== SECURITY FLAGS ===")
    for f, l, t in security[:30]:
        print(f"  {f}:{l}  {t}")
    print()

if empty_files:
    print("=== EMPTY / TRIVIAL FILES ===")
    for f in empty_files[:30]:
        print(f"  {f}")
    print()

# Wiring check
print("=== WIRING: public functions never called ===")
all_calls: set[str] = set()
defined: list[tuple[str,str,int]] = []

for py in py_files:
    try:
        text = py.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except Exception:
        continue
    rel = str(py.relative_to(vc))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                all_calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                all_calls.add(node.func.attr)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                defined.append((rel, node.name, node.lineno))

never_called = [
    (f, n, l) for f, n, l in defined
    if n not in all_calls
    and n not in {"main","setup","teardown","test","check","run","start","stop","close","cleanup"}
    and not f.startswith("test")
]

print(f"  {len(defined)} public funcs defined, {len(never_called)} appear uncalled")
by_file2: dict[str, list] = defaultdict(list)
for f, n, l in never_called[:300]:
    by_file2[f].append((l, n))
for f, items in sorted(by_file2.items())[:20]:
    print(f"  {f}: {[n for _,n in items[:8]]}")

print()
print("Audit complete.")
sys.exit(1 if syntax or stubs or security else 0)
