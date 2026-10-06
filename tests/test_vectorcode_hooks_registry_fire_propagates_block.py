"""Regression for vectorcode/src/hooks/registry.py's HookRegistry.fire():

A handler's exception was caught inside its daemon thread, logged, and
then silently discarded -- fire() itself never re-raised. This defeats
_make_claude_hook_wrapper()'s documented "can_block=True" contract: a
Claude-style hook script exiting 2 (meaning "block this operation") makes
the wrapper raise RuntimeError specifically so the caller aborts the
lifecycle event, but fire() swallowed that exception into a log line,
so the caller had no way to know a hook wanted to block anything.
"""
from __future__ import annotations

import pytest

from vectorcode.src.hooks.registry import HookName, HookRegistry


def test_fire_reraises_a_handler_exception_to_the_caller() -> None:
    registry = HookRegistry(default_timeout=1.0)

    def _blocking_handler(ctx: dict) -> None:
        raise RuntimeError("blocked by policy")

    registry.register(HookName.PRE_EDIT, _blocking_handler)

    with pytest.raises(RuntimeError, match="blocked by policy"):
        registry.fire(HookName.PRE_EDIT, {"file": "secret.env"})


def test_fire_does_not_raise_when_no_handler_errors() -> None:
    registry = HookRegistry(default_timeout=1.0)
    seen = []
    registry.register(HookName.PRE_EDIT, lambda ctx: seen.append(ctx))

    registry.fire(HookName.PRE_EDIT, {"file": "ok.py"})

    assert seen == [{"file": "ok.py"}]
