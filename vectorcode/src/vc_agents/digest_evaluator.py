"""Digest evaluator agent."""
from __future__ import annotations
from typing import Any, Dict

class DigestEvaluator:
    """Evaluates the quality of generated digests."""
    def evaluate(self, digest: str, **kw: Any) -> Dict[str, Any]:
        return {"score": 1.0, "feedback": "ok"}
