"""Deterministic, offline YouTube SEO scorer + chapter builder.

Repo integration (docs/repo_analysis/youtube-automation-agent.md): VECTOR's
content district generates SEO copy via LLM (script_generator.py,
video_generator.py) but had no rule-based scorer to grade/gate that output,
and no deterministic chapter builder from script section durations. This
module is the cheap, free, offline pre-publish quality gate the LLM output
should pass through.

Behavior reimplemented from the absorbed repo's heuristics (title
length/number/year/power-word, description timestamps/links/format, tag
count/long-tail/dedup, chapters-from-section-durations) — no JS copied, no
hardcoded power-word list or stop-words ported verbatim; written fresh.
Pure Python, zero external dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["score_seo", "build_chapters", "SEOScoreResult"]

# Title length sweet spot for YouTube search/recommendation surfaces.
_TITLE_MIN_CHARS = 40
_TITLE_MAX_CHARS = 70
_TITLE_HARD_CAP = 100

# Words that signal a concrete, clickable promise rather than vague hype.
_POWER_WORDS = frozenset({
    "ultimate", "complete", "essential", "proven", "secret", "free",
    "easy", "fast", "best", "top", "guide", "tutorial", "review",
    "honest", "real", "new", "2024", "2025", "2026", "step-by-step",
    "beginner", "advanced", "explained", "vs",
})

_LONG_TAIL_MIN_WORDS = 2  # a "long-tail" tag has 2+ words


@dataclass
class SEOScoreResult:
    score: int                     # 0-100
    breakdown: dict = field(default_factory=dict)
    suggestions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "breakdown": self.breakdown, "suggestions": self.suggestions}


def _score_title(title: str) -> tuple[int, list[str]]:
    """0-30 points: length, presence of a number, a recent year, a power word."""
    points = 0
    notes: list[str] = []
    length = len(title)

    if _TITLE_MIN_CHARS <= length <= _TITLE_MAX_CHARS:
        points += 12
    elif length < _TITLE_HARD_CAP:
        points += 6
        notes.append(f"title length {length} — sweet spot is {_TITLE_MIN_CHARS}-{_TITLE_MAX_CHARS} chars")
    else:
        notes.append(f"title length {length} exceeds {_TITLE_HARD_CAP} chars — will be truncated in search results")

    if re.search(r"\d", title):
        points += 6
    else:
        notes.append("no number in title (lists/years/counts improve CTR)")

    if re.search(r"20[2-3]\d", title):
        points += 4
    else:
        notes.append("no recent year in title (signals freshness)")

    title_lower = title.lower()
    if any(w in title_lower for w in _POWER_WORDS):
        points += 8
    else:
        notes.append("no power word found — consider one of: " + ", ".join(sorted(_POWER_WORDS)[:5]) + "...")

    return points, notes


def _score_description(description: str) -> tuple[int, list[str]]:
    """0-30 points: length, timestamps present, links present, paragraph formatting."""
    points = 0
    notes: list[str] = []
    desc = description or ""

    if len(desc) >= 200:
        points += 8
    else:
        notes.append("description under 200 chars — add more context for search indexing")

    if re.search(r"\b\d{1,2}:\d{2}(:\d{2})?\b", desc):
        points += 10
    else:
        notes.append("no timestamps found — add chapter timestamps (mm:ss) for YouTube's chapter UI")

    if re.search(r"https?://", desc):
        points += 6
    else:
        notes.append("no links found — add a relevant link (channel, related video, socials)")

    if "\n\n" in desc or desc.count("\n") >= 3:
        points += 6
    else:
        notes.append("description reads as one block — break into paragraphs for readability")

    return points, notes


def _score_tags(tags: list[str]) -> tuple[int, list[str]]:
    """0-25 points: count, long-tail presence, dedup/case-insensitive uniqueness."""
    points = 0
    notes: list[str] = []
    tags = [t.strip() for t in (tags or []) if t and t.strip()]

    if not tags:
        notes.append("no tags provided")
        return 0, notes

    if 8 <= len(tags) <= 15:
        points += 10
    elif tags:
        points += 5
        notes.append(f"{len(tags)} tags — 8-15 is the recommended range")

    long_tail = [t for t in tags if len(t.split()) >= _LONG_TAIL_MIN_WORDS]
    if long_tail:
        points += 8
    else:
        notes.append("no long-tail (multi-word) tags — these capture more specific search intent")

    lowered = [t.lower() for t in tags]
    if len(lowered) == len(set(lowered)):
        points += 7
    else:
        dupes = len(lowered) - len(set(lowered))
        points += max(0, 7 - dupes * 2)
        notes.append(f"{dupes} duplicate tag(s) (case-insensitive) — wasting tag slots")

    return points, notes


def _score_format(title: str, description: str, tags: list[str]) -> tuple[int, list[str]]:
    """0-15 points: nothing missing entirely (title/description/tags all present)."""
    points = 0
    notes: list[str] = []
    if title and title.strip():
        points += 5
    else:
        notes.append("title is empty")
    if description and description.strip():
        points += 5
    else:
        notes.append("description is empty")
    if tags:
        points += 5
    else:
        notes.append("no tags at all")
    return points, notes


def score_seo(title: str, description: str = "", tags: list[str] | None = None) -> dict:
    """Score a YouTube title/description/tag set 0-100 with a breakdown and
    actionable suggestions. Pure offline heuristic — no API calls, no LLM.

    Returns: {"score": int, "breakdown": {...}, "suggestions": [...]}
    """
    tags = tags or []
    title_pts, title_notes = _score_title(title or "")
    desc_pts, desc_notes = _score_description(description or "")
    tags_pts, tags_notes = _score_tags(tags)
    fmt_pts, fmt_notes = _score_format(title or "", description or "", tags)

    total = title_pts + desc_pts + tags_pts + fmt_pts
    result = SEOScoreResult(
        score=min(100, total),
        breakdown={
            "title": title_pts,
            "description": desc_pts,
            "tags": tags_pts,
            "format": fmt_pts,
        },
        suggestions=title_notes + desc_notes + tags_notes + fmt_notes,
    )
    return result.to_dict()


def build_chapters(sections: list[dict]) -> list[dict]:
    """Build a YouTube chapter list from script sections with durations.

    Input: [{"name"|"title": str, "duration_sec": float}, ...] in playback order
    (the shape script_generator.py's `_extract_sections` produces, with a
    duration added per section).

    Output: [{"start_sec": int, "label": "mm:ss", "title": str}, ...]
    YouTube requires the first chapter to start at 0:00 and each subsequent
    chapter to be at least 10s after the previous one — both enforced here.
    """
    if not sections:
        return []

    chapters: list[dict] = []
    cursor = 0.0
    for i, section in enumerate(sections):
        title = section.get("title") or section.get("name") or f"Section {i + 1}"
        start = 0 if i == 0 else int(cursor)
        # YouTube's chapter UI requires consecutive chapters to be >=10s apart.
        if chapters and start - chapters[-1]["start_sec"] < 10:
            start = chapters[-1]["start_sec"] + 10
        chapters.append({
            "start_sec": start,
            "label": _format_timestamp(start),
            "title": str(title),
        })
        cursor = max(cursor, start) + float(section.get("duration_sec", 0) or 0)

    return chapters


def _format_timestamp(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    result = score_seo(
        "5 Python Tricks Every Beginner Should Know in 2026",
        "In this video I cover 5 essential Python tricks.\n\n0:00 Intro\n1:30 Trick 1\n\nWatch more: https://youtube.com/@vector",
        ["python tips", "python tricks", "python", "beginner python", "coding tutorial 2026", "learn python fast", "python basics", "programming tips"],
    )
    assert 0 <= result["score"] <= 100
    print(f"[seo_scorer] score={result['score']} breakdown={result['breakdown']}")

    chapters = build_chapters([
        {"name": "intro_hook", "duration_sec": 15},
        {"name": "main_content", "duration_sec": 180},
        {"name": "summary", "duration_sec": 30},
    ])
    assert chapters[0]["start_sec"] == 0
    assert len(chapters) == 3
    print(f"[seo_scorer] chapters={chapters}")

    print("✅ seo_scorer.py OK")
