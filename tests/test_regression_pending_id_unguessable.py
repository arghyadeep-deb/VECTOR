"""Regression test for a real bug an independent review found:
`PermissionGateway._make_pending_id()` used to return a trivially
guessable, sequential id (f"{action_type}#{self._pending_seq}", e.g.
"run_shell_command#42"). That SAME id is embedded in the real Pushover
approve/reject URLs `request_approval()` sends
(core/api/routers/gateway.py's GET /gateway/approve/{action_id} route has
no authentication of its own -- it trusts the id alone), so anyone able
to reach that HTTP endpoint could approve ANY pending RED-tier action --
including a real shell command -- by guessing or enumerating the next
sequence number.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real `_make_pending_id()` implementation directly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.loop.permission_gateway import PermissionGateway


def test_pending_id_contains_an_unguessable_component():
    gw = PermissionGateway()
    pid = gw._make_pending_id("run_shell_command")
    assert pid.startswith("run_shell_command#")
    # Must carry a real random component beyond the bare sequence number --
    # a URL-safe token, not just digits after the '#'.
    suffix = pid.split("#", 1)[1]
    assert "_" in suffix, f"expected '<seq>_<random_token>', got {suffix!r}"
    seq_part, token_part = suffix.split("_", 1)
    assert seq_part.isdigit()
    assert len(token_part) >= 16, "random component must be substantial, not a token stub"
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", token_part), (
        "random component must be URL-safe (it goes straight into a Pushover link)"
    )


def test_consecutive_pending_ids_for_the_same_action_type_are_not_predictable_from_each_other():
    gw = PermissionGateway()
    ids = [gw._make_pending_id("run_shell_command") for _ in range(5)]
    assert len(set(ids)) == 5, "every pending id must be unique"
    tokens = [pid.split("_", 1)[1] for pid in ids]
    assert len(set(tokens)) == 5, (
        "the random component itself must differ every time -- an "
        "attacker who has seen one real id must not be able to derive "
        "the next one"
    )


def test_resolve_pending_id_still_works_with_the_new_format():
    """The id remains an opaque key everywhere else in the file -- this
    proves the fix didn't break exact-match lookup."""
    gw = PermissionGateway()
    pid = gw._make_pending_id("run_shell_command")
    gw._pending_events[pid] = object()  # minimal stand-in, exact-match path only
    assert gw._resolve_pending_id(pid) == pid


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
