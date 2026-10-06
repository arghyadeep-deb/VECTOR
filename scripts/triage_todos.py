#!/usr/bin/env python3
"""
scripts/triage_todos.py — Phase 6C: Categorize TODO/FIXME/XXX/HACK comments.

Usage: python scripts/triage_todos.py [--output triage_report.md]

Outputs a markdown report grouping TODOs by:
  - REAL BUG: likely causes incorrect behavior
  - FUTURE FEATURE: planned enhancement
  - OBSOLETE: workaround that can be deleted
  - UNKNOWN: needs manual review
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
PATTERN = re.compile(r'#\s*(TODO|FIXME|XXX|HACK)[:\s]*(.*)', re.IGNORECASE)
EXCLUDE = {'.claude', 'node_modules', '__pycache__', 'venv', '.git', 'dist', 'build'}

# Heuristics for auto-classification
BUG_KEYWORDS = {'bug', 'broken', 'wrong', 'incorrect', 'crash', 'fail', 'error', 'fix', 'race', 'leak', 'unsafe'}
FEATURE_KEYWORDS = {'add', 'implement', 'support', 'extend', 'improve', 'enhance', 'future', 'later', 'month', 'year', 'v2', 'phase'}
OBSOLETE_KEYWORDS = {'remove', 'delete', 'cleanup', 'clean up', 'dead', 'unused', 'deprecated', 'old', 'legacy', 'workaround'}


def classify(text: str) -> str:
    t = text.lower()
    if any(k in t for k in BUG_KEYWORDS):
        return 'REAL_BUG'
    if any(k in t for k in OBSOLETE_KEYWORDS):
        return 'OBSOLETE'
    if any(k in t for k in FEATURE_KEYWORDS):
        return 'FUTURE_FEATURE'
    return 'UNKNOWN'


def scan() -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = defaultdict(list)
    for py_file in ROOT.rglob('*.py'):
        if any(ex in py_file.parts for ex in EXCLUDE):
            continue
        try:
            lines = py_file.read_text(encoding='utf-8', errors='replace').splitlines()
        except Exception:
            continue
        for lineno, line in enumerate(lines, 1):
            m = PATTERN.search(line)
            if m:
                tag, text = m.group(1).upper(), m.group(2).strip()
                category = classify(text)
                results[category].append({
                    'file': str(py_file.relative_to(ROOT)),
                    'line': lineno,
                    'tag': tag,
                    'text': text[:120],
                })
    return results


def report(results: dict, output_path: str | None = None) -> str:
    total = sum(len(v) for v in results.values())
    lines = [
        '# VECTOR TODO/FIXME Triage Report',
        '',
        f'**Total:** {total} items across {sum(1 for v in results.values() for _ in v)} occurrences',
        '',
    ]
    order = ['REAL_BUG', 'OBSOLETE', 'FUTURE_FEATURE', 'UNKNOWN']
    for cat in order:
        items = results.get(cat, [])
        if not items:
            continue
        emoji = {'REAL_BUG': '🔴', 'OBSOLETE': '🟡', 'FUTURE_FEATURE': '🔵', 'UNKNOWN': '⚪'}[cat]
        lines.append(f'## {emoji} {cat} ({len(items)} items)')
        lines.append('')
        for item in sorted(items, key=lambda x: x['file']):
            lines.append(f"- `{item['file']}:{item['line']}` **{item['tag']}**: {item['text']}")
        lines.append('')
    text = '\n'.join(lines)
    if output_path:
        Path(output_path).write_text(text, encoding='utf-8')
        print(f'Report written to {output_path}')
    else:
        print(text)
    return text


if __name__ == '__main__':
    output = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]
    results = scan()
    report(results, output)
    total = sum(len(v) for v in results.values())
    bugs = len(results.get('REAL_BUG', []))
    print(f'\nSummary: {total} total, {bugs} real bugs, {len(results.get("OBSOLETE", []))} obsolete')
