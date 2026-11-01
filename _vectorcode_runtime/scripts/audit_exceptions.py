#!/usr/bin/env python3
"""
scripts/audit_exceptions.py — Phase 1A re-audit: classify every except block.

Categories:
  LOGGED        - has logger.*/print/raise inside
  RE_RAISED     - re-raises the exception
  BARE_PASS_TELEMETRY - bare pass in a telemetry/trace/metrics path (intentional)
  BARE_PASS_REAL      - bare pass in real logic (needs at minimum a debug log)
  ABC_PASS      - pass in an abstract method body (legitimate)

Usage: python scripts/audit_exceptions.py [--fix] [--output exception_audit.md]
  --fix   Add logger.debug(...) to every BARE_PASS_REAL block
"""
import ast
import sys
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
EXCLUDE = {'.claude', 'node_modules', '__pycache__', 'venv', '.git', 'dist', 'build', 'legacy_ported'}
TELEMETRY_PATHS = {'telemetry', 'trace', 'metrics', 'prometheus', 'statsd', 'monitor'}

FIX_MODE = '--fix' in sys.argv
OUTPUT = None
if '--output' in sys.argv:
    idx = sys.argv.index('--output')
    if idx + 1 < len(sys.argv):
        OUTPUT = sys.argv[idx + 1]


def _is_telemetry_path(path: Path) -> bool:
    return any(t in str(path).lower() for t in TELEMETRY_PATHS)


def _body_has_logging(body: list) -> bool:
    """Check if an except body has any logging or print call."""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Call):
            func = node.func
            # logger.xxx(...) or print(...)
            if isinstance(func, ast.Attribute) and func.attr in (
                'debug', 'info', 'warning', 'error', 'critical', 'exception', 'log'
            ):
                return True
            if isinstance(func, ast.Name) and func.id == 'print':
                return True
    return False


def _body_has_raise(body: list) -> bool:
    return any(
        isinstance(node, ast.Raise)
        for node in ast.walk(ast.Module(body=body, type_ignores=[]))
    )


def _is_abstract_method(handler: ast.ExceptHandler, parent_func) -> bool:
    """True if the except is inside a function whose body is just pass/..."""
    if parent_func is None:
        return False
    # If the function body is [pass] or [Expr(Constant(...))] it's abstract
    body = parent_func.body
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    return False


def classify_file(path: Path) -> list[dict]:
    results = []
    try:
        source = path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    lines = source.splitlines()

    # Walk and find all ExceptHandler nodes
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        lineno = node.lineno
        body = node.body

        # Determine category
        if _body_has_raise(body):
            cat = 'RE_RAISED'
        elif _body_has_logging(body):
            cat = 'LOGGED'
        elif len(body) == 1 and isinstance(body[0], ast.Pass):
            if _is_telemetry_path(path):
                cat = 'BARE_PASS_TELEMETRY'
            else:
                # Check surrounding context for telemetry keywords
                context_lines = ' '.join(lines[max(0, lineno-5):lineno+5]).lower()
                if any(t in context_lines for t in TELEMETRY_PATHS):
                    cat = 'BARE_PASS_TELEMETRY'
                else:
                    cat = 'BARE_PASS_REAL'
        elif len(body) == 1 and isinstance(body[0], ast.Expr):
            # Could be ... (Ellipsis) — abstract
            val = body[0].value
            if isinstance(val, ast.Constant) and val.value is ...:
                cat = 'ABC_PASS'
            else:
                cat = 'UNLOGGED_REAL'
        else:
            cat = 'UNLOGGED_REAL'

        exc_type = ''
        if node.type:
            if isinstance(node.type, ast.Name):
                exc_type = node.type.id
            elif isinstance(node.type, ast.Attribute):
                exc_type = f"{node.type.value.id}.{node.type.attr}" if isinstance(node.type.value, ast.Name) else '?'

        try:
            display_path = str(path.relative_to(ROOT))
        except ValueError:
            display_path = str(path)
        results.append({
            'file': display_path,
            'line': lineno,
            'exc_type': exc_type or 'bare',
            'category': cat,
            'snippet': lines[lineno - 1].strip() if lineno <= len(lines) else '',
        })
    return results


def fix_bare_pass(path: Path, items: list[dict]) -> int:
    """Add logger.debug to BARE_PASS_REAL blocks. Returns count fixed."""
    if not items:
        return 0
    source = path.read_text(encoding='utf-8', errors='replace')
    lines = source.splitlines(keepends=True)
    # Work backwards so line numbers stay valid
    fixed = 0
    for item in sorted(items, key=lambda x: x['line'], reverse=True):
        lineno = item['line']  # 1-indexed, this is the `except` line
        # Find the `pass` line after it
        for i in range(lineno, min(lineno + 5, len(lines))):
            if lines[i].rstrip() == lines[i].rstrip().lstrip() + 'pass' or lines[i].strip() == 'pass':
                indent = len(lines[i]) - len(lines[i].lstrip())
                prefix = ' ' * indent
                lines[i] = (
                    prefix + 'from loguru import logger\n'
                    + prefix + 'logger.opt(exception=True).debug("[VECTOR] suppressed exception")\n'
                )
                fixed += 1
                break
    path.write_text(''.join(lines), encoding='utf-8')
    return fixed


def main():
    all_results: dict[str, list[dict]] = defaultdict(list)
    scanned = 0

    for py_file in ROOT.rglob('*.py'):
        if any(ex in py_file.parts for ex in EXCLUDE):
            continue
        items = classify_file(py_file)
        scanned += 1
        for item in items:
            all_results[item['category']].append(item)

    total = sum(len(v) for v in all_results.values())
    bare_real = all_results.get('BARE_PASS_REAL', [])
    unlogged_real = all_results.get('UNLOGGED_REAL', [])

    if FIX_MODE and bare_real:
        by_file: dict[str, list] = defaultdict(list)
        for item in bare_real:
            by_file[item['file']].append(item)
        fixed_total = 0
        for rel_path, items in by_file.items():
            abs_path = ROOT / rel_path
            fixed_total += fix_bare_pass(abs_path, items)
        print(f"Fixed {fixed_total} BARE_PASS_REAL blocks")

    lines = [
        '# VECTOR Exception Audit Report',
        '',
        f'**Files scanned:** {scanned}  ',
        f'**Total except blocks:** {total}  ',
        f'**BARE_PASS_REAL (needs fix):** {len(bare_real)}  ',
        f'**UNLOGGED_REAL (needs review):** {len(unlogged_real)}  ',
        '',
    ]
    order = ['BARE_PASS_REAL', 'UNLOGGED_REAL', 'BARE_PASS_TELEMETRY', 'ABC_PASS', 'LOGGED', 'RE_RAISED']
    emoji = {'BARE_PASS_REAL': '🔴', 'BARE_PASS_TELEMETRY': '🟡', 'ABC_PASS': '⚪', 'LOGGED': '🟢', 'RE_RAISED': '🔵'}
    for cat in order:
        items = all_results.get(cat, [])
        if not items:
            continue
        lines.append(f'## {emoji.get(cat, "")} {cat} ({len(items)})')
        lines.append('')
        for item in sorted(items, key=lambda x: x['file']):
            lines.append(f"- `{item['file']}:{item['line']}` `except {item['exc_type']}` — {item['snippet']}")
        lines.append('')

    report = '\n'.join(lines)
    if OUTPUT:
        Path(OUTPUT).write_text(report, encoding='utf-8')
        print(f'Report written to {OUTPUT}')
    else:
        print(report)

    print(f'\nSummary: {total} total, {len(bare_real)} BARE_PASS_REAL, {len(all_results.get("LOGGED", []))} logged')
    return len(bare_real) + len(unlogged_real)


if __name__ == '__main__':
    sys.exit(0 if main() == 0 else 1)
