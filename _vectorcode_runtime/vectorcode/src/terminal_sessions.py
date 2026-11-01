"""Durable terminal checkpoints using the existing SQLite and /restore session stores."""

import json
from pathlib import Path

from loguru import logger


def checkpoint(bridge):
    import session_db

    from vectorcode.src.repl import _save_session
    from vectorcode.src.session import VectorCodeSession

    if not bridge.history:
        return None
    session = VectorCodeSession.get()
    usage = {
        "prompt_tokens": session.token_usage.prompt_tokens,
        "completion_tokens": session.token_usage.completion_tokens,
        "cache_read_tokens": session.token_usage.cache_read_tokens,
    }
    # /restore and --resume read this primary store. A secondary SQLite failure
    # must not prevent the completed conversation from being saved here.
    saved = _save_session(
        [{"role": "system", "content": bridge.system_prompt}] + bridge.history,
        session.current_model,
        session.mode,
        usage,
        session.tool_calls,
        session_id=session.session_id,
        project=str(bridge.project),
        title=session.display_title,
        worker_name=getattr(bridge, "worker_name", None),
    )
    try:
        session_db.get_session_db().checkpoint_terminal(
            session.session_id, session.current_model, str(bridge.project), session.mode, bridge.history, usage
        )
    except Exception as exc:
        logger.warning("[VECTOR][terminal] JSON checkpoint saved; SQLite indexing unavailable: {}", type(exc).__name__)
    return saved


def resume(bridge, selector="latest"):
    from vectorcode.src.repl import _list_sessions
    from vectorcode.src.session import VectorCodeSession

    records = _list_sessions()
    candidates = []
    for index, item in enumerate(records, 1):
        try:
            data = json.loads(Path(item["path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        history = data.get("history") if isinstance(data, dict) else None
        if not isinstance(history, list) or not any(
            isinstance(message, dict) and message.get("role") in {"user", "assistant", "tool"}
            and (message.get("content") or message.get("tool_calls")) for message in history
        ):
            continue
        if data.get("project") and Path(data["project"]).resolve() == bridge.project.resolve():
            if selector == "latest" and data.get("worker_name"):
                continue
            if selector == "latest" or str(data.get("session_id") or "").startswith(selector):
                candidates.append((index, data))
    if not candidates:
        raise ValueError("No saved terminal session matches this project and selector. Use /restore to list sessions.")
    if selector != "latest" and len(candidates) != 1:
        raise ValueError("Session selector is ambiguous for this project.")
    index, data = candidates[0]
    event = bridge.commands()._restore_data(data)
    session = VectorCodeSession.get()
    if data.get("session_id"):
        session.session_id = data["session_id"]
    bridge.system_prompt = next((m.get("content", "") for m in data["history"] if m.get("role") == "system"), "")
    event["response"] = "Resumed saved conversation for this project. Tool approvals must be granted again."
    return event


if __name__ == "__main__":
    assert callable(checkpoint) and callable(resume)
