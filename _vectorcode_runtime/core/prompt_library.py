"""
PromptLibrary — live system prompt registry for VECTOR district agents.

Scans two locations:
  core/prompts/shared/          — cross-district and unmapped prompts
  districts/<name>/prompts/     — prompts owned by a specific district

Usage:
    from core.prompt_library import get_library

    lib = get_library()
    system_prompt = lib.get("engineering-code-reviewer")   # by slug
    system_prompt = lib.get_for_agent("code_reviewer")     # by Python agent name

Each prompt file has YAML frontmatter (name, description, vibe) followed by the
full system prompt body.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger

_SHARED = Path(__file__).parent / "prompts" / "shared"
_DISTRICTS_ROOT = Path(__file__).parent.parent / "districts"

# ── Map: agent Python filename stem → prompt file stem (without category prefix)
# Key  = how the agent file is named in districts/ (snake_case, no .py)
# Value = the archived prompt file stem (e.g. "engineering-code-reviewer")
AGENT_PROMPT_MAP: dict[str, str] = {
    # ── coding district ──────────────────────────────────────────────────────
    "code_reviewer":                "engineering-code-reviewer",
    "architect_bot":                "engineering-software-architect",
    "bug_hunter":                   "engineering-security-engineer",
    "git_bot":                      "engineering-git-workflow-master",
    "test_writer":                  "engineering-ai-engineer",
    "minimal_change_engineer":      "engineering-minimal-change-engineer",
    "codebase_onboarding_engineer": "engineering-codebase-onboarding-engineer",
    "rapid_prototyper":             "engineering-rapid-prototyper",
    "technical_writer":             "engineering-technical-writer",

    # ── security district ────────────────────────────────────────────────────
    "threat_detection_engineer":    "engineering-threat-detection-engineer",
    "threat_scout":                 "engineering-security-engineer",

    # ── ops / devops district ────────────────────────────────────────────────
    "sre_monitor":                  "engineering-sre",
    "devops_automator":             "engineering-devops-automator",
    "incident_commander":           "engineering-incident-response-commander",

    # ── data_analytics district ──────────────────────────────────────────────
    "analytics_reporter":           "support-analytics-reporter",
    "data_engineer":                "engineering-data-engineer",
    "performance_benchmarker":      "testing-performance-benchmarker",

    # ── QA district ──────────────────────────────────────────────────────────
    "reality_checker":              "testing-reality-checker",
    "api_tester":                   "testing-api-tester",
    "evidence_collector":           "testing-evidence-collector",
    "accessibility_auditor":        "testing-accessibility-auditor",
    "test_results_analyzer":        "testing-test-results-analyzer",
    "tool_evaluator":               "testing-tool-evaluator",
    "workflow_optimizer":           "testing-workflow-optimizer",

    # ── governance / council district ────────────────────────────────────────
    "product_manager":              "product-manager",
    "llm_council":                  "specialized-chief-of-staff",

    # ── chief_of_staff district ──────────────────────────────────────────────
    "chief_of_staff":               "specialized-chief-of-staff",

    # ── projects / startups ──────────────────────────────────────────────────
    "project_planner":              "project-mgmt-sprint-planner",
    "competitor_spy":               "strategy-competitive-analyst",
    "idea_validator":               "strategy-decision-advisor",

    # ── research district ────────────────────────────────────────────────────
    "paper_reader":                 "academic-paper-summarizer",
    "web_scout":                    "product-trend-researcher",

    # ── personal_growth district ─────────────────────────────────────────────
    "behavioral_nudge_engine":      "product-behavioral-nudge-engine",
    "feedback_synthesizer":         "product-feedback-synthesizer",
    "zk_steward":                   "zk-steward",

    # ── agency / sales district ──────────────────────────────────────────────
    "sales_strategist":             "sales-outbound-strategist",
    "proposal_strategist":          "sales-proposal-strategist",
    "client_manager":               "sales-account-strategist",

    # ── autonomous loop ──────────────────────────────────────────────────────
    "governor":                     "specialized-agents-orchestrator",
    "agents_orchestrator":          "specialized-agents-orchestrator",

    # ── support / communications ─────────────────────────────────────────────
    "communications_adapter":       "support-support-responder",

    # ── content district ─────────────────────────────────────────────────────
    "script_generator":             "content-youtube-script-writer",
    "caption_generator":            "content-instagram-caption-writer",
    "video_generator":              "content-video-strategist",
    "voice_generator":              "content-social-media-creator",

    # ── marketing district ───────────────────────────────────────────────────
    "content_creator":              "content-social-media-creator",
    "social_media_strategist":      "content-social-media-creator",
}


@dataclass
class PromptEntry:
    slug: str
    name: str
    description: str
    vibe: str
    body: str
    path: Path
    tags: list[str] = field(default_factory=list)

    @property
    def system_prompt(self) -> str:
        """Return the full system prompt body (no frontmatter)."""
        return self.body


def _parse_file(path: Path) -> PromptEntry | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Strip HTML comment ingest header
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()

    # Parse frontmatter block
    fm_match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not fm_match:
        # No frontmatter — treat entire file as body
        slug = path.stem
        return PromptEntry(slug=slug, name=slug, description="", vibe="", body=text.strip(), path=path)

    fm_raw = fm_match.group(1)
    body   = fm_match.group(2).strip()

    def _fm(key: str) -> str:
        m = re.search(rf"^{key}:\s*(.+)", fm_raw, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else ""

    return PromptEntry(
        slug        = path.stem,
        name        = _fm("name") or path.stem,
        description = _fm("description"),
        vibe        = _fm("vibe"),
        body        = body,
        path        = path,
        tags        = [path.parent.name],  # category folder as tag
    )


class PromptLibrary:
    """Lazy-loading registry of VECTOR system prompts."""

    def __init__(self) -> None:
        self._by_slug: dict[str, PromptEntry] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        count = 0
        # Scan core/prompts/shared/ (cross-district and unmapped prompts)
        if _SHARED.exists():
            for md in _SHARED.rglob("*.md"):
                entry = _parse_file(md)
                if entry:
                    self._by_slug[entry.slug] = entry
                    count += 1
        # Scan districts/*/prompts/ (district-owned prompts)
        if _DISTRICTS_ROOT.exists():
            for district_dir in _DISTRICTS_ROOT.iterdir():
                if district_dir.is_dir():
                    prompts_dir = district_dir / "prompts"
                    if prompts_dir.is_dir():
                        for md in prompts_dir.rglob("*.md"):
                            entry = _parse_file(md)
                            if entry:
                                self._by_slug[entry.slug] = entry
                                count += 1
        self._loaded = True
        logger.debug("[VECTOR][prompt_library] loaded {} prompts (shared + district folders)", count)

    # ── Public API ─────────────────────────────────────────────────────────────

    # 2026-07-28 owner decision: VECTOR must understand any language the user
    # writes in, but always reply in English — appended once here as the
    # single choke point for every district-agent prompt loaded through this
    # library (~100 agents), instead of editing each prompt file individually.
    # Deliberately NOT applied to core/prompts/shared/specialized/
    # language-translator.md's slug — an explicit "translate to another
    # language" tool would be broken by this suffix — but that prompt is
    # currently unwired into AGENT_PROMPT_MAP and not called anywhere at
    # runtime (confirmed via grep), so no exclusion logic is needed yet. If it
    # ever gets wired up, exclude its slug here first.
    _ENGLISH_ONLY_SUFFIX = (
        "\n\nAlways respond in English, no matter what language the user's "
        "message is written in. Understand any language on input, but reply "
        "only in English."
    )

    def get(self, slug: str) -> str | None:
        """Return system prompt body for a prompt slug, or None if not found."""
        self._ensure_loaded()
        entry = self._by_slug.get(slug)
        if entry is None:
            # Try stripping common category prefixes for convenience
            for prefix in ("engineering-", "specialized-", "testing-", "support-",
                           "product-", "strategy-", "sales-", "academic-",
                           "content-", "project-mgmt-", "project-management-"):
                entry = self._by_slug.get(f"{prefix}{slug}")
                if entry:
                    break
        if entry is None:
            return None
        return entry.body + self._ENGLISH_ONLY_SUFFIX

    def get_for_agent(self, agent_name: str) -> str | None:
        """Look up system prompt by Python agent filename stem (e.g. 'code_reviewer')."""
        slug = AGENT_PROMPT_MAP.get(agent_name)
        if slug is None:
            return None
        return self.get(slug)

    def list_by_tag(self, tag: str) -> list[PromptEntry]:
        """Return all prompts in a category folder (e.g. 'engineering', 'testing')."""
        self._ensure_loaded()
        return [e for e in self._by_slug.values() if tag in e.tags]

    def all_slugs(self) -> list[str]:
        self._ensure_loaded()
        return sorted(self._by_slug.keys())

    def summary(self) -> dict:
        self._ensure_loaded()
        by_tag: dict[str, int] = {}
        for e in self._by_slug.values():
            for t in e.tags:
                by_tag[t] = by_tag.get(t, 0) + 1
        return {"total": len(self._by_slug), "by_category": by_tag}


# Module-level singleton — lazy, one load per process
@lru_cache(maxsize=1)
def get_library() -> PromptLibrary:
    return PromptLibrary()


if __name__ == "__main__":
    lib = get_library()
    s = lib.summary()
    print(f"OK prompt_library.py -- {s['total']} prompts loaded")
    for cat, n in sorted(s["by_category"].items()):
        print(f"  {cat}: {n}")

    # Spot-check agent lookups
    assert lib.get_for_agent("code_reviewer") is not None,   "code_reviewer must resolve"
    assert lib.get_for_agent("reality_checker") is not None, "reality_checker must resolve"
    assert lib.get_for_agent("chief_of_staff") is not None,  "chief_of_staff must resolve"
    assert lib.get("engineering-code-reviewer") is not None, "direct slug must work"
    print("OK all spot-checks passed")
