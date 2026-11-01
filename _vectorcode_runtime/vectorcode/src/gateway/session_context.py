"""
Session-scoped context variables for the VectorCode gateway.

Replaces the previous ``os.environ``-based session state
(``VECTOR_SESSION_PLATFORM``, ``VECTOR_SESSION_CHAT_ID``, etc.) with
Python's ``contextvars.ContextVar``.

**Why this matters**

The gateway processes messages concurrently via ``asyncio``.  When two
messages arrive at the same time the old code did:

    os.environ["VECTOR_SESSION_THREAD_ID"] = str(context.source.thread_id)

Because ``os.environ`` is *process-global*, Message A's value was
silently overwritten by Message B before Message A's agent finished
running.  Background-task notifications and tool calls therefore routed
to the wrong thread.

``contextvars.ContextVar`` values are *task-local*: each ``asyncio``
task (and any ``run_in_executor`` thread it spawns) gets its own copy,
so concurrent messages never interfere.

**Backward compatibility**

The public helper ``get_session_env(name, default="")`` mirrors the old
``os.environ.get("VECTOR_SESSION_*", ...)`` calls.  Existing tool code only
needs to replace the import + call site:

    # before
    import os
    platform = os.environ.get("VECTOR_SESSION_PLATFORM", "")

    # after
    from gateway.session_context import get_session_env
    platform = get_session_env("VECTOR_SESSION_PLATFORM", "")
"""

from contextvars import ContextVar
from typing import Any

# Sentinel to distinguish "never set in this context" from "explicitly set to empty".
# When a contextvar holds _UNSET, we fall back to os.environ (CLI/cron compat).
# When it holds "" (after clear_session_vars resets it), we return "" — no fallback.
_UNSET: Any = object()

# ---------------------------------------------------------------------------
# Per-task session variables
# ---------------------------------------------------------------------------

_SESSION_PLATFORM: ContextVar = ContextVar("VECTOR_SESSION_PLATFORM", default=_UNSET)
_SESSION_CHAT_ID: ContextVar = ContextVar("VECTOR_SESSION_CHAT_ID", default=_UNSET)
_SESSION_CHAT_NAME: ContextVar = ContextVar("VECTOR_SESSION_CHAT_NAME", default=_UNSET)
_SESSION_THREAD_ID: ContextVar = ContextVar("VECTOR_SESSION_THREAD_ID", default=_UNSET)
_SESSION_USER_ID: ContextVar = ContextVar("VECTOR_SESSION_USER_ID", default=_UNSET)
_SESSION_USER_NAME: ContextVar = ContextVar("VECTOR_SESSION_USER_NAME", default=_UNSET)
_SESSION_KEY: ContextVar = ContextVar("VECTOR_SESSION_KEY", default=_UNSET)

# Cron auto-delivery vars — set per-job in run_job() so concurrent jobs
# don't clobber each other's delivery targets.
_CRON_AUTO_DELIVER_PLATFORM: ContextVar = ContextVar("VECTOR_CRON_AUTO_DELIVER_PLATFORM", default=_UNSET)
_CRON_AUTO_DELIVER_CHAT_ID: ContextVar = ContextVar("VECTOR_CRON_AUTO_DELIVER_CHAT_ID", default=_UNSET)
_CRON_AUTO_DELIVER_THREAD_ID: ContextVar = ContextVar("VECTOR_CRON_AUTO_DELIVER_THREAD_ID", default=_UNSET)

_VAR_MAP = {
    "VECTOR_SESSION_PLATFORM": _SESSION_PLATFORM,
    "VECTOR_SESSION_CHAT_ID": _SESSION_CHAT_ID,
    "VECTOR_SESSION_CHAT_NAME": _SESSION_CHAT_NAME,
    "VECTOR_SESSION_THREAD_ID": _SESSION_THREAD_ID,
    "VECTOR_SESSION_USER_ID": _SESSION_USER_ID,
    "VECTOR_SESSION_USER_NAME": _SESSION_USER_NAME,
    "VECTOR_SESSION_KEY": _SESSION_KEY,
    "VECTOR_CRON_AUTO_DELIVER_PLATFORM": _CRON_AUTO_DELIVER_PLATFORM,
    "VECTOR_CRON_AUTO_DELIVER_CHAT_ID": _CRON_AUTO_DELIVER_CHAT_ID,
    "VECTOR_CRON_AUTO_DELIVER_THREAD_ID": _CRON_AUTO_DELIVER_THREAD_ID,
}


def set_session_vars(
    platform: str = "",
    chat_id: str = "",
    chat_name: str = "",
    thread_id: str = "",
    user_id: str = "",
    user_name: str = "",
    session_key: str = "",
) -> list:
    """Set all session context variables and return reset tokens.

    Call ``clear_session_vars(tokens)`` in a ``finally`` block to restore
    the previous values when the handler exits.

    Returns a list of ``Token`` objects (one per variable) that can be
    passed to ``clear_session_vars``.
    """
    tokens = [
        _SESSION_PLATFORM.set(platform),
        _SESSION_CHAT_ID.set(chat_id),
        _SESSION_CHAT_NAME.set(chat_name),
        _SESSION_THREAD_ID.set(thread_id),
        _SESSION_USER_ID.set(user_id),
        _SESSION_USER_NAME.set(user_name),
        _SESSION_KEY.set(session_key),
    ]
    return tokens


def clear_session_vars(tokens: list) -> None:
    """Restore the context that preceded :func:`set_session_vars`.

    Resetting with the returned tokens is important for nested gateway work:
    blindly writing empty strings here erased an enclosing request's routing
    context.  When the preceding value was the never-set sentinel, install an
    explicit empty value after the reset so stale process-wide environment
    variables still cannot leak into a completed gateway task.
    """
    variables = (
        _SESSION_PLATFORM,
        _SESSION_CHAT_ID,
        _SESSION_CHAT_NAME,
        _SESSION_THREAD_ID,
        _SESSION_USER_ID,
        _SESSION_USER_NAME,
        _SESSION_KEY,
    )
    if len(tokens) != len(variables):
        raise ValueError("session context token count does not match variables")
    for var, token in zip(reversed(variables), reversed(tokens)):
        var.reset(token)
        if var.get() is _UNSET:
            var.set("")


def get_session_env(name: str, default: str = "") -> str:
    """Read a session context variable by its legacy ``VECTOR_SESSION_*`` name.

    Drop-in replacement for ``os.environ.get("VECTOR_SESSION_*", default)``.

    Resolution order:
    1. Context variable (set by the gateway for concurrency-safe access).
       If the variable was explicitly set (even to ``""``) via
       ``set_session_vars`` or ``clear_session_vars``, that value is
       returned — **no fallback to os.environ**.
    2. ``os.environ`` (only when the context variable was never set in
       this context — i.e. CLI, cron scheduler, and test processes that
       don't use ``set_session_vars`` at all).
    3. *default*
    """
    import os

    var = _VAR_MAP.get(name)
    if var is not None:
        value = var.get()
        if value is not _UNSET:
            return value
    # Fall back to os.environ for CLI, cron, and test compatibility
    return os.environ.get(name, default)
