"""Phase 4.1 (external review 2026-09-24): protect the existing routes with the
golden intent dataset. Offline -- no Ollama, no real LLM: the embedding stage
is disabled and the LLM stub says "not an action", so the only thing that can
answer is the deterministic regex pre-classifier. Every regex hit must agree
with the golden label (measured 52/737 hits, 52/52 correct on 2026-09-24).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.city.governor import classify_chat_intent

_GOLDEN = Path(__file__).resolve().parents[1] / "data" / "golden_intent_dataset.jsonl"


class _NoEmbeddings:
    def __getattr__(self, name):
        raise RuntimeError("embedding stage disabled for this test")


class _NotAnAction:
    content = '{"is_action": false}'


@pytest.mark.asyncio
async def test_regex_preclassifier_hits_agree_with_golden_labels(monkeypatch):
    monkeypatch.setattr(classify_chat_intent, "_matcher", _NoEmbeddings(), raising=False)
    client = MagicMock()
    client.chat = AsyncMock(return_value=_NotAnAction())
    rows = [json.loads(line) for line in _GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]

    hits, wrong = 0, []
    with patch("core.inference.provider_client.get_client", return_value=client):
        for row in rows:
            res = await classify_chat_intent(row["text"])
            if res.get("source") != "regex_preclassify":
                continue
            hits += 1
            if (res["district"], res["type"]) != (row["district"], row["task_type"]):
                wrong.append((row["text"], row["district"], row["task_type"], res["district"], res["type"]))

    assert hits >= 40, f"regex layer matched only {hits} golden rows -- pre-classifier table shrank?"
    assert wrong == [], f"regex pre-classifier disagrees with golden labels: {wrong[:5]}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
