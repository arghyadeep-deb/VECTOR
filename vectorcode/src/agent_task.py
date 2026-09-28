"""Run one task through the real tool-using agent loop (engine.agent_loop.VectorAgent)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def run_agent_task(task: str, project_dir: Path, model: Optional[str] = None) -> str:
    """Run ONE task through the real agent loop and return its final answer.

    `vector run` used to make a single raw chat call with no tools, so asked to read a file it invented the
    contents. If the agent cannot start (model unreachable, no tools) this raises rather than guessing.
    """
    from engine.agent_loop import VectorAgent
    from session import VectorCodeSession

    session = VectorCodeSession.get()
    agent = VectorAgent(model_id=model or session.current_model, project_dir=Path(project_dir),
                        session_id=session.session_id, quiet_mode=True, save_trajectories=False)
    result = agent.run_conversation(
        task,
        system_message=("You are VectorCode, a coding agent working in " + str(project_dir) + ". "
                        "Use your tools to read files and run commands; never guess file contents or command output."),
        conversation_history=[],
    )
    reply = (result.get("response") or "").strip()
    if reply.startswith("[VECTOR error:"):
        raise RuntimeError(reply)
    return reply
