"""
districts/design/knowledge/__init__.py
Design corpus loader — BM25-style keyword search over UI/UX CSV corpus files.

Harvested from: ui-ux-pro-max-skill-main/cli/assets/data/
Contains: ux-guidelines, design, styles, typography, colors, icons, charts,
          landing, ui-reasoning, react-performance, products, google-fonts,
          and per-stack CSVs (React, Next.js, Svelte, Vue, Angular, Flutter, etc.)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

_KNOWLEDGE_DIR = Path(__file__).parent

# Priority corpora for general design search (checked first, in order)
_PRIMARY_CORPORA = [
    "ux-guidelines.csv",
    "design.csv",
    "ui-reasoning.csv",
    "styles.csv",
    "typography.csv",
    "colors.csv",
    "icons.csv",
    "charts.csv",
    "landing.csv",
    "react-performance.csv",
]

# Cached rows: { filename: [row_dict, ...] }
_cache: dict[str, list[dict]] = {}


def _load_csv(filename: str) -> list[dict]:
    """Load a CSV file from the knowledge directory (cached)."""
    if filename in _cache:
        return _cache[filename]
    # Check root and stacks/ subdirectory
    candidates = [
        _KNOWLEDGE_DIR / filename,
        _KNOWLEDGE_DIR / "stacks" / filename,
    ]
    root = _KNOWLEDGE_DIR.resolve()
    for path in candidates:
        # CWE-22: `corpora` is caller-controlled; never read outside the knowledge dir
        # (an absolute or ../ filename would otherwise escape it).
        if not path.resolve().is_relative_to(root) or path.suffix.lower() != ".csv":
            logger.warning("[VECTOR][design_knowledge] rejected corpus path outside knowledge dir: {}", filename)
            _cache[filename] = []
            return []
        if path.exists():
            try:
                rows: list[dict] = []
                with open(path, newline="", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(dict(row))
                _cache[filename] = rows
                return rows
            except Exception as e:
                logger.warning(f"[VECTOR][design_knowledge] failed to load {filename}: {e}")
                _cache[filename] = []
                return []
    _cache[filename] = []
    return []


def _score_row(row: dict, terms: list[str]) -> int:
    """Simple BM25-inspired score: count term occurrences across all fields."""
    text = " ".join(str(v) for v in row.values()).lower()
    return sum(text.count(t) for t in terms)


def search_design_corpus(
    query: str,
    top_k: int = 10,
    corpora: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    BM25-style text search over the UI/UX design corpus.

    Args:
        query:   Natural language search query.
        top_k:   Maximum results to return (default 10).
        corpora: Specific CSV filenames to search. Defaults to _PRIMARY_CORPORA.

    Returns:
        List of dicts, each with keys: 'corpus', 'score', and all row fields.
        Sorted by score descending.
    """
    if not query or not query.strip():
        return []

    terms = [t.lower() for t in query.split() if len(t) > 1]
    if not terms:
        return []

    target_corpora: list[str] = corpora or _PRIMARY_CORPORA
    results: list[dict[str, Any]] = []

    for filename in target_corpora:
        rows = _load_csv(filename)
        for row in rows:
            score = _score_row(row, terms)
            if score > 0:
                results.append({"corpus": filename, "score": score, **row})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def list_corpora() -> list[str]:
    """Return all available corpus filenames in the knowledge directory."""
    corpora: list[str] = []
    for path in _KNOWLEDGE_DIR.rglob("*.csv"):
        corpora.append(path.name)
    return sorted(corpora)


def load_corpus(filename: str) -> list[dict]:
    """Load and return all rows from a specific corpus file."""
    return _load_csv(filename)


__all__ = [
    "search_design_corpus",
    "list_corpora",
    "load_corpus",
]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    available = list_corpora()
    print(f"[OK] corpora available: {len(available)}")
    results = search_design_corpus("button hover focus state accessibility")
    print(f"[OK] search 'button hover focus': {len(results)} results")
    if results:
        top = results[0]
        print(f"     top hit: corpus={top['corpus']} score={top['score']}")
    print("districts/design/knowledge/__init__.py OK")
