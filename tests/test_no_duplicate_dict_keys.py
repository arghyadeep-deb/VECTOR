"""Phase 4 (external review 2026-09-24): governor `_DISTRICT_DISAMBIGUATION_HINTS`
had two "content" keys and swarm `TASK_TO_DISTRICT` two "news" keys -- Python
silently keeps the last, so the earlier text/route was dead. Guard against the
whole class in core/: a dict literal must not repeat a constant key with a
different value.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

_CORE = Path(__file__).resolve().parents[1] / "core"


def _duplicates() -> list[str]:
    found = []
    for path in _CORE.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen: dict = {}
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, (str, int)):
                    if key.value in seen and ast.dump(seen[key.value]) != ast.dump(value):
                        found.append(f"{path.relative_to(_CORE.parent)}:{key.lineno} {key.value!r}")
                    seen[key.value] = value
    return found


def test_no_dict_literal_repeats_a_key_with_a_different_value():
    assert _duplicates() == []


def test_news_and_content_routes_are_single_and_correct():
    from core.swarm.orchestrator import TASK_TO_DISTRICT
    from core.city.governor import _DISTRICT_DISAMBIGUATION_HINTS

    assert TASK_TO_DISTRICT["news"] == "news_trends"
    assert "public-facing" in _DISTRICT_DISAMBIGUATION_HINTS["content"]
    assert "marketing" in _DISTRICT_DISAMBIGUATION_HINTS["content"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
