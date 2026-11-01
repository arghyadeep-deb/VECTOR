"""SessionBuffer — per-session rolling conversational buffer.

Deliberately separate from the rest of core/memory/: everything else in this
package (episodic, semantic, policy, reasoning, counterfactual, the
knowledge graph) is DURABLE memory — written once, decayed/reinforced over
days via Ebbinghaus (core.memory.decay), meant to outlive a session.

A session buffer is the opposite: "what did we just say a moment ago in
THIS conversation" — pure recency, scoped to one session_id, capped by row
count (a rolling window), never decayed or reinforced. It exists to fix a
real gap: /command's LLM answer path (core/api/routers/commands.py::
_llm_answer) had no memory of the last few turns AT ALL — every call was a
cold start dressed up in durable-memory context (goals/doctrine/screen), so
a direct follow-up like "what did I just say?" had nothing to look at.
Session-scoped by design: an owner running two conversations in parallel
(HUD chat + a scripted caller, say) must not have them bleed into each
other's short-term context.

Storage: reuses episodic.py's single shared SQLite connection (session_turns
table, created in episodic._create_tables()) instead of opening a second DB
file/lock — this module has no state of its own.

Backward compatibility: callers that never pass a session_id must see
IDENTICAL behavior to before this module existed. Every public function
here is a no-op (or returns "") when session_id is falsy — enforced at the
call site in commands.py, not just here, but also defensively here.
"""
from __future__ import annotations

import datetime
import uuid

from loguru import logger
from core.config import CONFIG

# Rows kept on disk per session (rolling window) — generous so nothing is
# lost if a long conversation later wants deeper recall via the LLM
# classifier read path; MAX_TURNS_IN_PROMPT below is what actually gets
# spent as LLM context per call.
MAX_TURNS_STORED = 40
MAX_TURNS_IN_PROMPT = MAX_TURNS_STORED


def append_turn(session_id: str, role: str, content: str) -> None:
    """Record one turn (role='user'|'assistant') and prune the session back
    down to MAX_TURNS_STORED rows. Best-effort — a buffer failure must never
    break the actual response path."""
    if not session_id or not content:
        return
    try:
        from core.memory.episodic import get_temp_cursor
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with get_temp_cursor() as cur:
            cur.execute(
                "INSERT INTO session_turns (id, session_id, role, content, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, role,
                 content[:CONFIG["hud_chat"]["max_turn_chars"]], now),
            )
            cur.execute(
                """DELETE FROM session_turns WHERE session_id = ? AND id NOT IN (
                       SELECT id FROM session_turns WHERE session_id = ?
                       ORDER BY timestamp DESC LIMIT ?
                   )""",
                (session_id, session_id, MAX_TURNS_STORED),
            )
    except Exception as e:
        logger.debug(f"[VECTOR][session_buffer] append_turn failed (non-fatal): {e}")


def get_recent_turns(session_id: str, limit: int = MAX_TURNS_IN_PROMPT) -> list[dict]:
    """Oldest-first list of {role, content, timestamp} for this session."""
    if not session_id or limit <= 0:
        return []
    try:
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cur:
            cur.execute(
                "SELECT role, content, timestamp FROM session_turns "
                "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cur.fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
    except Exception as e:
        logger.debug(f"[VECTOR][session_buffer] get_recent_turns failed (non-fatal): {e}")
        return []


def format_for_prompt(session_id: str, limit: int = MAX_TURNS_IN_PROMPT) -> str:
    """Compact 'user: ... / assistant: ...' block ready to hand to
    ContextEngine.session_hydration_prompt()'s extra_context, or "" if the
    session has no prior turns (or session_id is falsy) — callers should
    skip adding the line entirely on empty string."""
    turns = get_recent_turns(session_id, limit=limit)
    if not turns:
        return ""
    context = "\n".join(f"{turn['role']}: {turn['content']}" for turn in turns)
    budget = CONFIG["hud_chat"]["context_chars"]
    if len(context) <= budget:
        return context
    marker = "\n[Some intervening conversation omitted to fit the context budget.]\n"
    anchor_chars = budget // 3
    return context[:anchor_chars] + marker + context[-(budget - anchor_chars - len(marker)):]


def clear_session(session_id: str) -> None:
    """Drop all buffered turns for a session (e.g. explicit 'new conversation')."""
    if not session_id:
        return
    try:
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cur:
            cur.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
    except Exception as e:
        logger.debug(f"[VECTOR][session_buffer] clear_session failed (non-fatal): {e}")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    sid = f"selftest-{uuid.uuid4().hex[:8]}"
    assert get_recent_turns(sid) == []
    assert format_for_prompt(sid) == ""

    append_turn(sid, "user", "what's my dark mode preference")
    append_turn(sid, "assistant", "you prefer dark mode in all apps")
    turns = get_recent_turns(sid)
    assert len(turns) == 2, turns
    assert turns[0]["role"] == "user" and turns[1]["role"] == "assistant"

    prompt_block = format_for_prompt(sid)
    assert "user: what's my dark mode" in prompt_block
    assert "assistant: you prefer dark mode" in prompt_block

    # rolling-window cap
    for i in range(MAX_TURNS_STORED + 10):
        append_turn(sid, "user", f"filler {i}")
    all_turns = get_recent_turns(sid, limit=1000)
    assert len(all_turns) == MAX_TURNS_STORED, len(all_turns)

    # no session_id -> pure no-op, no crash
    append_turn("", "user", "should be dropped")
    assert get_recent_turns("") == []

    clear_session(sid)
    assert get_recent_turns(sid) == []

    print("✅ session_buffer.py OK — rolling window, formatting, and no-op-without-session_id all verified")
