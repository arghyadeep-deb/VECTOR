"""Lightweight skill matcher — loads data/skills_manifest.json, no faiss/vc_tools deps."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from vectorcode.src.skills.types import MatchedSkill


def _score(
    skill_data: Dict[str, Any],
    skill_id: str,
    query_lower: str,
    query_words: set,
) -> float:
    """Score a skill entry against the query; returns [0.0, 1.0]."""
    name = str(skill_data.get("name", skill_id)).lower()
    sid = skill_id.lower()
    description = str(skill_data.get("description", "")).lower()
    trigger_text = " ".join(str(t) for t in skill_data.get("triggers", [])).lower()

    if not query_words:
        return 0.0
    if query_lower in (name, sid):
        return 1.0

    name_words = set(re.sub(r"[-_]", " ", name).split())
    id_words = set(re.sub(r"[-_]", " ", sid).split())
    all_name_words = name_words | id_words
    desc_words = set(description.split())
    trigger_words = set(trigger_text.split())

    name_overlap = len(query_words & all_name_words) / len(query_words)
    desc_overlap = len(query_words & desc_words) / len(query_words)
    trigger_overlap = len(query_words & trigger_words) / len(query_words)
    # Substring boost for words > 3 chars (avoids matching "my", "a", "to")
    name_substr = any(w in name or w in sid for w in query_words if len(w) > 3)

    return round(max(
        name_overlap * 0.9,
        desc_overlap * 0.75,
        trigger_overlap * 0.65,
        0.7 if name_substr else 0.0,
    ), 3)


def _find_manifest_path() -> Optional[Path]:
    """Locate data/skills_manifest.json relative to the repo root."""
    candidates = [
        Path("data/skills_manifest.json"),
        Path(__file__).parent.parent.parent.parent / "data" / "skills_manifest.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


class SkillMatcher:
    """Keyword-overlap skill matcher backed by data/skills_manifest.json.

    Instantiates with no arguments. All external dependencies are optional.
    """

    def __init__(self) -> None:
        self._manifest: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        if self._manifest is not None:
            return self._manifest
        path = _find_manifest_path()
        if path is None:
            logger.debug("[VECTOR][skills.matcher] skills_manifest.json not found")
            self._manifest = {}
            return self._manifest
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                self._manifest = json.load(fh)
        except Exception as exc:
            logger.debug("[VECTOR][skills.matcher] manifest load failed: {}", exc)
            self._manifest = {}
        return self._manifest

    def match(
        self,
        query: Optional[str] = None,
        *,
        action_type: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[MatchedSkill]:
        """Return skills matching *query* with confidence >= 0.6, sorted descending.

        Accepts a free-text *query* or keyword args *action_type* / *params*
        (the form used by the autonomous loop).
        """
        if query is None and action_type:
            query = action_type.replace("_", " ")
            if params:
                query += " " + " ".join(
                    str(v) for v in params.values() if isinstance(v, str)
                )
        if not query:
            return []

        query_lower = query.lower()
        query_words = {w for w in query_lower.split() if w}

        results: List[MatchedSkill] = []
        for skill_id, skill_data in self._load().items():
            confidence = _score(skill_data, skill_id, query_lower, query_words)
            if confidence >= 0.6:
                results.append(MatchedSkill(
                    name=skill_data.get("name", skill_id),
                    description=str(skill_data.get("description", ""))[:200],
                    confidence=confidence,
                    skill_id=skill_id,
                    category=str(skill_data.get("category", "")),
                    triggers=[str(t) for t in skill_data.get("triggers", [])],
                ))

        results.sort(key=lambda s: s.confidence, reverse=True)
        return results


__all__ = ["SkillMatcher"]
