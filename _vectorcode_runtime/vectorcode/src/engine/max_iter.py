# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py
"""Handle graceful budget exhaustion."""
from typing import Any, Dict, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from .agent import AIAgent


async def handle_max_iterations(agent: "AIAgent", partial_text: str) -> Dict[str, Any]:
    """Called when iteration budget is exhausted.

    Tries to get a final summary from the model, then returns.
    """
    logger.warning(
        f"Max iterations ({agent.budget.max_total}) reached for session {agent.session_id[:8]}"
    )

    summary_prompt = (
        "You have reached the maximum number of iterations. "
        "Please provide a brief summary of what you have accomplished so far "
        "and what remains to be done."
    )

    agent._history.append({"role": "user", "content": summary_prompt})

    try:
        from .conversation import _call_model, _extract_content
        response = await _call_model(agent)
        summary = _extract_content(response)
    except Exception as e:
        logger.error(f"Failed to get summary on max iterations: {e}")
        summary = partial_text or "[Max iterations reached — no summary available]"

    return {
        "status": "max_iterations",
        "text": summary,
        "partial_text": partial_text,
        "iterations_used": agent.budget.used,
        "iterations_max": agent.budget.max_total,
    }
