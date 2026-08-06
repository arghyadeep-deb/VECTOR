from __future__ import annotations

import os
import sys
import asyncio
from pathlib import Path

import pytest


# Windows: force the SelectorEventLoop for the entire test session.
# The default ProactorEventLoop allocates an IOCP self-pipe socketpair per event
# loop. A large suite calls asyncio.run() thousands of times; the accumulated
# socketpairs exhaust Windows socket buffers (WinError 10055) and a later loop
# hangs forever inside GetQueuedCompletionStatus — which then cascades into
# spurious ERRORs on every downstream async/DB test. Every asyncio subprocess
# call in this suite is mocked (AsyncMock), so SelectorEventLoop is safe here.
# (test_collections.py set this locally and claimed it "mirrors conftest.py";
# this is the global definition that claim referred to.)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_TEST_DATA_DIR = Path(__file__).resolve().parents[1] / "test_tmp" / "vector_pytest_data"
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("VECTOR_TEST_DATA_DIR", str(_TEST_DATA_DIR))

# Centralized sys.path setup — eliminates the need for per-test sys.path.insert hacks.
# The repo root is 1 level above tests/.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@pytest.fixture(autouse=True)
def _reset_permission_gateway_singleton():
    """Reset PermissionGateway's process-wide singleton before/after every test.

    2026-07-21 fix (core/loop/permission_gateway.py): PermissionGateway.__new__
    was changed to ALWAYS return one shared instance — 37 call sites across the
    codebase each constructing their own PermissionGateway() meant a Pushover
    "Approve" tap could hit a different instance's _pending_events than the one
    actually awaiting confirmation, silently timing out every RED/YELLOW
    approval. That fix is correct and necessary for production.

    It has a side effect on tests, though: dozens of unit tests call
    PermissionGateway() expecting a FRESH instance (empty audit_log, empty
    _unknown_actions, no leftover _pending_events from a previous test). With
    a real singleton and no reset, state accumulates across the whole pytest
    session — e.g. `test_get_unknown_actions_empty_initially` sees unknown
    actions recorded by unrelated earlier tests, `test_audit_log_grows` sees
    a log length inflated by every prior test's audit entries. This is a test-
    isolation gap, not a fresh production bug (found + root-caused 2026-07-23,
    task #91's core-subsystem test pass).

    Resetting `_shared = None` before AND after each test gives every test a
    genuinely isolated gateway (idempotent __init__ still runs, so nothing
    else about the class's behavior changes) without touching the singleton
    fix itself.
    """
    try:
        from core.loop.permission_gateway import PermissionGateway
        PermissionGateway._shared = None
    except Exception:
        pass
    yield
    try:
        from core.loop.permission_gateway import PermissionGateway
        PermissionGateway._shared = None
    except Exception:
        pass
