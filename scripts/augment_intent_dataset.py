"""Augment intent classification dataset using LLM.

Generates 80+ variations per district using qwen3:8b via Ollama.
Output: 3000+ examples for LoRA fine-tuning.

Usage:
    python scripts/augment_intent_dataset.py
"""
import sys
import json
import asyncio
import os
import tempfile
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
import ollama
from core.loop.context_engine import ContextEngine


# VECTOR districts (38 total)
DISTRICTS = [
    "languages", "startups", "brain", "karpathy_lab", "design", "data_analytics",
    "pattern_detective", "reflection", "ops", "time_calendar", "communications",
    "coding", "research", "investment", "health", "finance", "memory_curator",
    "content", "projects", "skills", "growth", "marketing", "interview_prep",
    "learning", "security", "privacy", "emergency", "home_assistant", "calls",
    "governance", "agency", "qa", "predictive_analytics", "science", "personal_growth",
    "relationships", "news_trends", "chief_of_staff"
]

# Seed examples per district (from intent_examples.json)
SEED_EXAMPLES = {
    "languages": [
        "quiz me on french vocabulary",
        "practice hindi vocabulary",
        "quiz me on japanese words",
        "help me practice bengali",
        "test my spanish vocabulary",
    ],
    "startups": [
        "help me scope a startup idea",
        "validate my startup idea",
        "think through this market opportunity",
        "scope out this side project",
        "analyze this business idea",
    ],
    "brain": [
        "what are my current goals",
        "show me my goals",
        "how am i doing on my goals",
        "what are my main goals right now",
        "whats my goal progress",
    ],
    "coding": [
        "review my code",
        "write a python function",
        "debug this error",
        "architect this module",
        "write unit tests",
    ],
    "research": [
        "search for recent ai papers",
        "find research on transformers",
        "look up arxiv papers",
        "research this topic",
        "find information about",
    ],
}


async def generate_variations(district: str, seed_examples: list[str], count: int = 80) -> list[str]:
    """Use LLM to generate variations for a district.

    Args:
        district: District name
        seed_examples: 5 seed examples
        count: Number of variations to generate

    Returns:
        List of generated query variations
    """
    seed_text = "\n".join(f"- {ex}" for ex in seed_examples)

    prompt = ContextEngine().session_hydration_prompt() + "\n\n" + f"""Generate {count} different ways a user might ask VECTOR to help with the {district} district.

Examples:
{seed_text}

Generate {count} natural, varied queries that would route to the {district} district.
Make them diverse: different word orders, synonyms, question forms, command forms.
Output one query per line, no numbering, no explanations."""

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ollama.generate(
                model="qwen3:8b",
                prompt=prompt,
                options={"temperature": 0.8, "num_predict": 2000}
            )
        )

        # Parse response
        lines = response["response"].strip().split("\n")
        variations = [line.strip("- ").strip() for line in lines if line.strip()]

        # Filter out empty lines and duplicates
        variations = list(set(v for v in variations if v and len(v) > 5))

        logger.info(f"[{district}] Generated {len(variations)} variations")
        return variations[:count]  # Cap at requested count

    except Exception as e:
        logger.error(f"[{district}] Generation failed: {e}")
        return []


async def augment_dataset() -> list[dict]:
    """Generate augmented dataset with 80+ examples per district."""
    logger.info("Starting dataset augmentation...")

    all_examples = []

    for district in DISTRICTS:
        # Get seed examples (use defaults if not in SEED_EXAMPLES)
        seeds = SEED_EXAMPLES.get(district, [f"help me with {district}", f"{district} task", f"do {district} work"])

        # Generate variations
        variations = await generate_variations(district, seeds, count=80)

        # Add to dataset
        for var in variations:
            all_examples.append({
                "text": var,
                "district": district,
            })

        # Small delay to avoid overwhelming Ollama
        await asyncio.sleep(0.5)

    logger.info(f"Augmentation complete: {len(all_examples)} total examples")
    return all_examples


def export_dataset(examples: list[dict], output_path: str) -> None:
    """Export dataset to JSONL format."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
            suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)

    logger.info(f"Exported {len(examples)} examples to {output_path}")


async def main():
    """Main augmentation pipeline."""
    print("\n" + "=" * 70)
    print("INTENT DATASET AUGMENTATION")
    print("=" * 70 + "\n")

    # Generate augmented dataset
    examples = await augment_dataset()

    # Export
    output_path = "data/golden_intent_dataset_augmented.jsonl"
    export_dataset(examples, output_path)

    # Stats
    district_counts = defaultdict(int)
    for ex in examples:
        district_counts[ex["district"]] += 1

    print(f"\n{'=' * 70}")
    print(f"DATASET STATISTICS")
    print(f"{'=' * 70}")
    print(f"Total examples: {len(examples)}")
    print(f"Districts covered: {len(district_counts)}/{len(DISTRICTS)}")
    average = len(examples) / len(district_counts) if district_counts else 0.0
    print(f"Average per district: {average:.1f}")
    print(f"Min per district: {min(district_counts.values(), default=0)}")
    print(f"Max per district: {max(district_counts.values(), default=0)}")

    print(f"\nPer-district breakdown:")
    for district in sorted(district_counts.keys()):
        print(f"  {district}: {district_counts[district]}")

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())
