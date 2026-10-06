"""Pre-commit syntax gate — blocks commits containing files that don't parse.

The mass-edit incident of 2026-05-30 silently broke 44 Python files (stripped
if-bodies, truncated tails) because nothing checked syntax at commit time.
This gate makes that class of accident impossible.

Checks STAGED CONTENT (git show :path — not the working tree, which may differ):
  *.py   -> compile() with the running interpreter
  *.js   -> node --check (skipped silently when node isn't installed)
  *.json -> json.loads
  *.yaml/yml -> yaml.safe_load (skipped when PyYAML missing)
  .env / secrets — refuses *.env-ish files outright (defense in depth; .env is
  already gitignored)

Install as a git hook:   python scripts/install_git_hooks.py
Run manually:            python scripts/precommit_syntax_gate.py
Exit 0 = clean, 1 = block commit (offending files listed).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def staged_files() -> list[str]:
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                       capture_output=True, text=True, cwd=REPO, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git diff failed")
    return [f for f in r.stdout.strip().splitlines() if f]


def staged_content(path: str) -> bytes:
    r = subprocess.run(["git", "show", f":{path}"],
                       capture_output=True, cwd=REPO, timeout=30)
    if r.returncode != 0:
        detail = r.stderr.decode("utf-8", errors="replace").strip() or "git show failed"
        raise RuntimeError(f"cannot read staged content for {path}: {detail}")
    return r.stdout


def check_python(path: str, data: bytes) -> str:
    try:
        compile(data.decode("utf-8", errors="replace"), path, "exec")
        return ""
    except SyntaxError as e:
        return f"line {e.lineno}: {e.msg}"


def check_js(path: str, data: bytes) -> str:
    try:
        node = subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        if node.returncode != 0:
            return ""
    except Exception:
        return ""  # node not installed — skip JS checks
    with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        r = subprocess.run(["node", "--check", tmp_path],
                           capture_output=True, text=True, timeout=20)
        return "" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["syntax error"])[-1][:160]
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def check_json(path: str, data: bytes) -> str:
    try:
        json.loads(data.decode("utf-8", errors="replace"))
        return ""
    except Exception as e:
        return str(e)[:160]


def check_yaml(path: str, data: bytes) -> str:
    try:
        import yaml
    except ImportError:
        return ""
    try:
        yaml.safe_load(data.decode("utf-8", errors="replace"))
        return ""
    except Exception as e:
        return str(e).replace("\n", " ")[:160]


def main() -> int:
    try:
        files = staged_files()
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        print(f"COMMIT BLOCKED — could not inspect staged files: {exc}", file=sys.stderr)
        return 1
    if not files:
        return 0
    failures: list[tuple[str, str]] = []
    for f in files:
        name = f.lower()
        if name.endswith(".env") or name == ".env" or "/.env" in name:
            failures.append((f, "refusing to commit .env-like file (secrets)"))
            continue
        try:
            data = staged_content(f)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            failures.append((f, str(exc)))
            continue
        if not data:
            continue
        err = ""
        if name.endswith(".py"):
            err = check_python(f, data)
        elif name.endswith(".js"):
            err = check_js(f, data)
        elif name.endswith(".json"):
            err = check_json(f, data)
        elif name.endswith((".yaml", ".yml")):
            err = check_yaml(f, data)
        if err:
            failures.append((f, err))
    if failures:
        print("COMMIT BLOCKED — staged files fail syntax checks:", file=sys.stderr)
        for f, err in failures:
            print(f"  {f}: {err}", file=sys.stderr)
        print("Fix the files (or unstage them) and retry.", file=sys.stderr)
        return 1
    print(f"syntax gate: {len(files)} staged file(s) clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
