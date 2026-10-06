"""Regression for vectorcode/src/connectors/slack_connector.py: every
failure path in sync() was completely silent -- the module had zero
logging at all.

The core bug: _slack_api_with_retry's retry loop, on exhausting retries
for a persistent Slack API error (e.g. "ok": False, "error": "ratelimited"),
returns that real response dict from *within* the loop (`return data`) --
it never falls through to the trailing `return {}` under any realistic
max_retries (>= 0). sync() never checked the `ok` field on the
conversations.list / users.list responses, so a persistent API error
looked identical to ".get('channels', [])" returning an empty list --
sync() would silently "complete" having synced zero channels, with
nothing to distinguish that from a genuinely empty workspace.

Also fixed: channel-join and history-fetch exception/not-ok paths were
bare `except Exception: continue`/`break` with zero logging.

UPDATED (connectors round 1, 2026-10-06): a persistent conversations.list
failure logging a warning and then silently stopping with docs=[] was
itself still an instance of the "phantom success" bug class -- an empty
result is indistinguishable from a genuinely empty workspace, and
SyncEngine's checkpoint logic (sync_engine.py) relies on connectors raising
on real failure to record a distinguishable error state. sync() now raises
RuntimeError instead of logging-and-stopping; this test was updated to
match that stricter, more correct contract (see
test_connectors_round1_regressions.py::test_slack_collection_failure_is_not_reported_as_success
for the new coverage of this exact path).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import vectorcode.src.connectors.slack_connector as slack_connector


def test_sync_raises_when_conversations_list_returns_not_ok(monkeypatch):
    monkeypatch.setattr(
        slack_connector,
        "load_tokens",
        lambda path: {"token": "xoxb-fake"},
    )
    monkeypatch.setattr(
        slack_connector,
        "_slack_api_users_list",
        lambda token: {"ok": True, "members": []},
    )
    monkeypatch.setattr(
        slack_connector,
        "_slack_api_conversations_list",
        lambda token, cursor="": {"ok": False, "error": "ratelimited"},
    )

    conn = slack_connector.SlackConnector(credentials_path="/tmp/does-not-matter.json")
    with pytest.raises(RuntimeError, match="ratelimited"):
        list(conn.sync())
    assert conn._items_synced == 0


def test_sync_logs_when_users_list_returns_not_ok(monkeypatch):
    monkeypatch.setattr(
        slack_connector,
        "load_tokens",
        lambda path: {"token": "xoxb-fake"},
    )
    monkeypatch.setattr(
        slack_connector,
        "_slack_api_users_list",
        lambda token: {"ok": False, "error": "invalid_auth"},
    )
    monkeypatch.setattr(
        slack_connector,
        "_slack_api_conversations_list",
        lambda token, cursor="": {"ok": True, "channels": []},
    )

    logged = []
    monkeypatch.setattr(
        slack_connector.logger,
        "warning",
        lambda *a, **k: logged.append((a, k)),
    )

    conn = slack_connector.SlackConnector(credentials_path="/tmp/does-not-matter.json")
    list(conn.sync())

    assert any("users.list failed" in str(a) for a, _ in logged)


def test_join_and_history_failures_are_logged_not_silent():
    import inspect

    src = inspect.getsource(slack_connector.SlackConnector.sync)
    assert src.count("logger.debug") >= 2, (
        "join-failure and history-fetch-failure except blocks must log, "
        "not swallow silently"
    )


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
