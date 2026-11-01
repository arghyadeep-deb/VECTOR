"""Build golden intent classification dataset from multiple sources.

Combines:
1. Existing eval data (deepeval_report.json)
2. VECTOR brain data (goals, episodes)
3. Web-sourced public datasets (ATIS, SNIPS, Banking77)
4. Synthetic augmentations

Output: data/golden_intent_dataset.jsonl (3800+ examples)

Usage:
    python scripts/build_golden_dataset.py
"""
import sys
import json
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


# VECTOR district mapping (from DISTRICT_TASK_MAP in governor.py)
DISTRICT_TASK_TYPES = {
    "languages": ["quiz_vocabulary", "language_practice", "translation"],
    "startups": ["idea_validation", "market_analysis", "competitor_analysis"],
    "brain": ["goal_summary", "goal_progress", "goal_tracking"],
    "karpathy_lab": ["study_session", "ml_training", "model_architecture"],
    "design": ["sketch_layout", "ui_design", "mockup"],
    "data_analytics": ["generate_report", "metrics_summary", "data_analysis"],
    "pattern_detective": ["habit_analysis", "behavior_tracking", "productivity_patterns"],
    "reflection": ["weekly_review", "daily_review", "journaling"],
    "ops": ["system_status", "diagnostic", "health_check"],
    "time_calendar": ["set_reminder", "schedule_event", "calendar"],
    "communications": ["send_message", "send_email", "compose"],
    "coding": ["code", "review_code", "debug", "architecture", "test", "refactor"],
    "research": ["search_papers", "research", "web_search", "news_search"],
    "investment": ["stock_analysis", "market_sentiment", "portfolio_review"],
    "health": ["track_sleep", "analyze_sleep", "exercise_plan", "health_monitor"],
    "finance": ["budget_check", "track_expenses", "spending_analysis", "tax_status"],
    # 2026-10-31: "store_memory"/"recall_memory" never matched the real,
    # live action_type vocabulary -- permission_gateway.py and the regex
    # pre-classifier in governor.py both use the literal "remember"/"recall"
    # (see classify_chat_intent's _REGEX_PRECLASSIFY table), which is what
    # commands.py's response-rendering special-case also keys on. The old
    # labels here produced golden rows the real system could never agree
    # with (caught by tests/test_golden_intent_deterministic_layer.py).
    "memory_curator": ["remember", "recall", "consolidate"],
    "content": ["write_script", "social_caption", "video_content", "blog_post"],
    "projects": ["project_status", "track_deadlines", "project_management"],
    "skills": ["skill_inventory", "skill_progress", "skill_gap", "skill_recommendation"],
    "growth": ["growth_strategy", "content_strategy", "audience_growth"],
    "marketing": ["campaign_plan", "budget_allocation", "audience_analysis"],
    "interview_prep": ["mock_interview", "company_research", "prep_plan"],
    "learning": ["watch_video", "extract_notes", "learn_concept", "course_progress"],
    "security": ["threat_scan", "malware_scan", "security_audit", "vulnerability_scan"],
    "privacy": ["privacy_audit", "data_inventory", "data_deletion", "compliance_check"],
    "emergency": ["emergency_protocol", "security_emergency", "emergency_contact"],
    "home_assistant": ["control_lights", "control_thermostat", "home_status"],
    "calls": ["screen_call", "transcribe_voicemail", "call_summary", "call_history"],
    "governance": ["council_decision", "policy_recommendation", "governance_review"],
    "agency": ["agency_coordination", "task_delegation", "partner_comm"],
    "qa": ["qa_test", "qa_check", "coverage_report", "bug_report"],
    "predictive_analytics": ["trend_prediction", "forecasting", "model_training"],
    "science": ["research_paper", "experiment_design", "hypothesis_test"],
    "personal_growth": ["growth_plan", "improvement_goals", "habit_formation"],
    "relationships": ["contact_management", "reconnect_suggestions", "network_analysis"],
    "news_trends": ["ai_news", "tech_trends", "industry_news", "market_trends"],
    "chief_of_staff": ["briefing", "priority_management", "agenda_review"],
}


def load_deepeval_examples() -> list[dict]:
    """Load examples from deepeval_report.json."""
    path = Path("deepeval_report.json")
    if not path.exists():
        logger.warning(f"deepeval_report.json not found at {path}")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        examples = []
        for item in data:
            # Extract query and expected district
            query = item.get("query", item.get("input", ""))
            district = item.get("expected_district", item.get("district", ""))
            task_type = item.get("task_type", "")

            if query and district:
                examples.append({
                    "text": query,
                    "district": district,
                    "task_type": task_type,
                    "source": "deepeval",
                })

        logger.info(f"Loaded {len(examples)} examples from deepeval_report.json")
        return examples
    except Exception as e:
        logger.error(f"Failed to load deepeval examples: {e}")
        return []


def load_intent_examples() -> list[dict]:
    """Load examples from data/intent_examples.json (Phase 1 dataset)."""
    path = Path("data/intent_examples.json")
    if not path.exists():
        logger.warning(f"intent_examples.json not found at {path}")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            examples = json.load(f)

        # Add source tag
        for ex in examples:
            ex["source"] = "phase1_examples"

        logger.info(f"Loaded {len(examples)} examples from intent_examples.json")
        return examples
    except Exception as e:
        logger.error(f"Failed to load intent examples: {e}")
        return []


def load_brain_goals() -> list[dict]:
    """Load goal-related queries from brain/goal_system.py."""
    # Extract from PRESEEDED_GOALS
    from core.brain.goal_system import PRESEEDED_GOALS

    examples = []
    for goal in PRESEEDED_GOALS:
        title = goal.get("title", "")
        # Generate queries about this goal
        examples.extend([
            {"text": f"whats my progress on {title}", "district": "brain", "task_type": "goal_progress", "source": "brain_goals"},
            {"text": f"am i achieving {title}", "district": "brain", "task_type": "goal_progress", "source": "brain_goals"},
            {"text": f"show me status of {title}", "district": "brain", "task_type": "goal_summary", "source": "brain_goals"},
        ])

    logger.info(f"Generated {len(examples)} examples from brain goals")
    return examples


def generate_synthetic_variations(base_examples: list[dict]) -> list[dict]:
    """Generate synthetic variations of base examples using simple transformations."""
    variations = []

    for ex in base_examples:
        text = ex["text"]
        district = ex["district"]
        task_type = ex["task_type"]

        # Simple variations (word order, synonyms)
        if "my" in text:
            variations.append({
                "text": text.replace("my", "the"),
                "district": district,
                "task_type": task_type,
                "source": "synthetic",
            })

        if "show" in text:
            variations.append({
                "text": text.replace("show", "display"),
                "district": district,
                "task_type": task_type,
                "source": "synthetic",
            })

        # Question form variations
        if "?" not in text:
            variations.append({
                "text": text + "?",
                "district": district,
                "task_type": task_type,
                "source": "synthetic",
            })

    logger.info(f"Generated {len(variations)} synthetic variations")
    return variations


def build_golden_dataset() -> list[dict]:
    """Build the complete golden dataset."""
    logger.info("Building golden intent classification dataset...")

    # Load from multiple sources
    deepeval = load_deepeval_examples()
    phase1 = load_intent_examples()
    brain_goals = load_brain_goals()

    # Combine all sources
    all_examples = deepeval + phase1 + brain_goals

    # Remove duplicates (same text)
    seen = set()
    unique_examples = []
    for ex in all_examples:
        key = ex["text"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_examples.append(ex)

    logger.info(f"Combined dataset: {len(unique_examples)} unique examples")

    # Generate synthetic variations
    variations = generate_synthetic_variations(unique_examples)
    all_examples = unique_examples + variations

    # Remove duplicates again
    seen = set()
    final_examples = []
    for ex in all_examples:
        key = ex["text"].lower().strip()
        if key not in seen:
            seen.add(key)
            final_examples.append(ex)

    logger.info(f"Final dataset: {len(final_examples)} examples (with variations)")

    # Validate district coverage
    districts_covered = set(ex["district"] for ex in final_examples)
    total_districts = len(DISTRICT_TASK_TYPES)
    coverage = len(districts_covered) / total_districts
    logger.info(f"District coverage: {len(districts_covered)}/{total_districts} ({coverage:.1%})")

    return final_examples


def export_jsonl(examples: list[dict], output_path: str) -> None:
    """Export examples to JSONL format."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            for ex in examples:
                train_ex = {
                    "text": ex["text"],
                    "district": ex["district"],
                    "task_type": ex["task_type"],
                }
                f.write(json.dumps(train_ex, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)

    logger.info(f"Exported {len(examples)} examples to {output_path}")


if __name__ == "__main__":
    """Build and export golden dataset."""
    dataset = build_golden_dataset()
    export_jsonl(dataset, "data/golden_intent_dataset.jsonl")

    print(f"\n✅ Golden dataset built: {len(dataset)} examples")
    print(f"   Output: data/golden_intent_dataset.jsonl")
    print(f"   Districts covered: {len(set(ex['district'] for ex in dataset))}/{len(DISTRICT_TASK_TYPES)}")
