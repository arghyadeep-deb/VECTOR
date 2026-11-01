# Ported from GitHub/vectorcode_vector/repo/v2/CLAUDE.md + v2/src/sparc/
"""SPARC methodology coordinator -- Specification -> Pseudocode -> Architecture -> Refinement -> Completion."""
import asyncio
from typing import Any, Optional

from loguru import logger

SPARC_STAGES = [
    "specification",
    "pseudocode",
    "architecture",
    "refinement",
    "completion",
]

STAGE_PROMPTS = {
    "specification": (
        "You are in the SPECIFICATION stage of SPARC.\n"
        "Analyze the task and produce:\n"
        "1. Clear requirements list\n"
        "2. Acceptance criteria\n"
        "3. Constraints and assumptions\n"
        "4. Out-of-scope items\n\n"
        "Task: {task}"
    ),
    "pseudocode": (
        "You are in the PSEUDOCODE stage of SPARC.\n"
        "Given the specification, produce:\n"
        "1. High-level algorithm in pseudocode\n"
        "2. Key data structures\n"
        "3. Function signatures\n"
        "4. Edge cases to handle\n\n"
        "Task: {task}\nSpecification: {spec}"
    ),
    "architecture": (
        "You are in the ARCHITECTURE stage of SPARC.\n"
        "Given the pseudocode, design:\n"
        "1. Module/file structure\n"
        "2. Class/function hierarchy\n"
        "3. Data flow diagram\n"
        "4. External dependencies\n\n"
        "Task: {task}\nPseudocode: {pseudocode}"
    ),
    "refinement": (
        "You are in the REFINEMENT stage of SPARC.\n"
        "Implement the architecture with TDD:\n"
        "1. Write failing tests first\n"
        "2. Implement to make tests pass\n"
        "3. Refactor for clarity\n"
        "4. Document public APIs\n\n"
        "Task: {task}\nArchitecture: {architecture}"
    ),
    "completion": (
        "You are in the COMPLETION stage of SPARC.\n"
        "Finalize the implementation:\n"
        "1. Integration tests\n"
        "2. Performance review\n"
        "3. Security review\n"
        "4. Documentation update\n"
        "5. Final summary\n\n"
        "Task: {task}\nRefinement: {refinement}"
    ),
}

async def run_sparc_stage(
    stage: str,
    task: str,
    context: dict,
    agent: Any,
) -> str:
    """Run a single SPARC stage using the provided agent."""
    if stage not in STAGE_PROMPTS:
        raise ValueError(f"Unknown SPARC stage: {stage!r}")

    prompt_template = STAGE_PROMPTS[stage]
    prompt_context = {
        "spec": "",
        "pseudocode": "",
        "architecture": "",
        "refinement": "",
        **context,
    }
    prompt = prompt_template.format(task=task, **prompt_context)

    logger.info(f"[SPARC] Running stage: {stage}")
    result = await agent.run_conversation(prompt)
    return result.get("text", "")

async def run_sparc_full(task: str, agent: Any) -> dict:
    """Run the full SPARC pipeline for a task.

    Returns dict with output from each stage.
    """
    context = {}
    results = {}

    stage_keys = {
        "specification": "spec",
        "pseudocode": "pseudocode",
        "architecture": "architecture",
        "refinement": "refinement",
        "completion": "completion",
    }

    for stage in SPARC_STAGES:
        try:
            output = await run_sparc_stage(stage, task, context, agent)
            results[stage] = output
            context[stage_keys[stage]] = output[:2000]  # truncate for next stage context
            logger.info(f"[SPARC] Stage {stage} complete ({len(output)} chars)")
        except Exception as e:
            logger.error(f"[SPARC] Stage {stage} failed: {e}")
            results[stage] = f"[Error: {e}]"
            break

    return results

def sparc_slash_command(stage: Optional[str], task: str, agent: Any) -> str:
    """Entry point for /sparc slash command in REPL."""
    if stage not in (None, "full", *SPARC_STAGES):
        task = f"{stage} {task}".strip()
        stage = "full"

    if stage == "full" or stage is None:
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(run_sparc_full(task, agent))
        finally:
            loop.close()
        return "\n\n".join(f"## {s.upper()}\n{r}" for s, r in results.items())
    else:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_sparc_stage(stage, task, {}, agent))
        finally:
            loop.close()
        return result
