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


# Session isolation (2026-09-24, docs/superpowers/specs/2026-09-24-test-suite-isolation-design.md):
# every pytest session gets a fresh temp DB + data dir, set BEFORE any VECTOR module
# is imported, so the suite never reads or writes the owner's live vector_memory.db
# or <repo>/data. Nothing survives to the next session (fixes stale dedup rows etc.).
import atexit
import shutil
import tempfile

_REPO_ROOT_PATH = Path(__file__).resolve().parents[1]
_LIVE_DB = (_REPO_ROOT_PATH / "vector_memory.db").resolve()
_LIVE_DATA = (_REPO_ROOT_PATH / "data").resolve()


def _is_live_path(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        p = Path(raw).expanduser().resolve()
    except Exception:
        return False
    return p == _LIVE_DB or p == _LIVE_DATA or _LIVE_DATA in p.parents


_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="vector_pytest_data_"))
atexit.register(shutil.rmtree, str(_TEST_DATA_DIR), True)
(_TEST_DATA_DIR / "data").mkdir()
os.environ["VECTOR_DB_PATH"] = str(_TEST_DATA_DIR / "vector_memory.db")
os.environ["VECTOR_TEST_DATA_DIR"] = str(_TEST_DATA_DIR / "data")
os.environ["VECTOR_DB_KEY"] = "pytest-session-key-not-for-production"
# A preset VECTOR_DB_PATH (e.g. .env's relative "vector_memory.db") is deliberately
# overridden above. VECTOR_DATA_DIR would beat nothing (TEST wins in runtime_paths)
# but is dropped so it can never point a test at live data.
os.environ.pop("VECTOR_DATA_DIR", None)
# .env carries LangSmith keys, so a test run uploaded traces of its (fake) LLM calls to an external service and printed
# "429 Monthly unique traces usage limit exceeded" at exit. Tests must not talk to third parties; the env var wins over
# python-dotenv because dotenv never overrides a variable that is already set.
for _tracing_var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING"):
    os.environ[_tracing_var] = "false"
# Behaviour flags the owner turns on in .env (fair HP, playbooks, exploration, gym, gesture) must not leak into tests that assert the default
# behaviour; tests that exercise a flag set it themselves. Same dotenv rule as above: a variable that is already set wins.
for _flag in ("VECTOR_HP_FAIR", "VECTOR_PLAYBOOK", "VECTOR_EXPLORE", "VECTOR_GYM", "VECTOR_GYM_LLM", "VECTOR_LEVEL_COUNCIL",
              "VECTOR_GESTURE_ENABLED"):
    os.environ[_flag] = "0"
os.environ.pop("VECTOR_EXPLORE_SHARE", None)


def _assert_not_live(where: str) -> None:
    """Hard guard: abort rather than ever run against live VECTOR state."""
    from core.memory.db_utils import configured_db_path
    from core.runtime_paths import data_path

    bad = [str(p) for p in (configured_db_path(), data_path("x").parent) if _is_live_path(str(p))]
    if bad:
        pytest.exit(f"refusing to run ({where}): resolves to live VECTOR state: {bad}", returncode=3)


# Some tests pop VECTOR_DB_PATH from the environment; the code then falls back to
# CONFIG["db_path"], which is the LIVE vector_memory.db. Point that baseline at the
# session temp DB too so a popped env var can never resolve to live state.
from core.config import CONFIG as _CONFIG  # noqa: E402
_CONFIG["db_path"] = _TEST_DATA_DIR / "vector_memory.db"

_assert_not_live("session start")

# Centralized sys.path setup — eliminates the need for per-test sys.path.insert hacks.
# The repo root is 1 level above tests/.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# Files that make real, unmocked calls to the local Ollama daemon. With
# OLLAMA_MAX_LOADED_MODELS=1 a cold model swap can outlast a short per-test
# timeout in a big suite run, so they get a `requires_ollama` marker (deselect
# with `-m "not requires_ollama"`) and a generous timeout instead of being
# mocked. See VECTOR_TECHNICAL_KNOWLEDGE/90_AUTHORITATIVE_REPOSITORY_BASELINE.md §6.
_REQUIRES_OLLAMA_FILES = frozenset({
    "test_intent_matcher.py",
    "test_agency_run_wiring.py",
    "test_coding_reviewers_run_wiring.py",
    "test_email_agent_permission_gate.py",
    "test_red_interactive_tools_bypass.py",
    "test_regression_governor_capability_routing.py",
    "test_command_websocket_parity.py",
})
# Single tests (not whole files) that also hit real LLMs; hangs identically on
# the pre-2026-09-24 baseline (trading pipeline call inside Governor.dispatch).
_REQUIRES_OLLAMA_TESTS = frozenset({
    "test_trader_hand_reaches_trading_conductor_not_stock_analyst",
})
_OLLAMA_TEST_TIMEOUT_SEC = 300


def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(str(item.fspath)).name in _REQUIRES_OLLAMA_FILES or item.name in _REQUIRES_OLLAMA_TESTS:
            item.add_marker(pytest.mark.requires_ollama)
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(_OLLAMA_TEST_TIMEOUT_SEC))


@pytest.fixture(autouse=True)
def _never_resolve_to_live_state():
    """Fail (not silently proceed) if any test leaves the DB/data paths pointing at live state."""
    from core.memory.db_utils import configured_db_path
    from core.runtime_paths import data_path

    bad = [str(p) for p in (configured_db_path(), data_path("x").parent) if _is_live_path(str(p))]
    if bad:
        pytest.fail(f"test environment resolves to live VECTOR state: {bad}", pytrace=False)
    yield


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


@pytest.fixture
def isolated_vector_db(tmp_path, monkeypatch):
    """M1e (2026-09-09): correct, reusable per-test VECTOR_DB_PATH isolation.

    Use this instead of setting `os.environ["VECTOR_DB_PATH"]` at module level.
    Module-level sets run once at COLLECTION time -- pytest imports every
    specified test module before running any test in any of them -- so a
    module-level override leaks into every test that runs afterward in the
    same process, for the rest of the session, regardless of file-listing
    order. This is the confirmed root cause of a severe cross-suite
    regression documented in
    VECTOR_TECHNICAL_KNOWLEDGE/M1d_DEVELOPMENT_TEST_SAFETY_REMEDIATION.md
    (the reverted P0-C attempt) and independently root-caused again in
    VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md.

    This fixture instead sets the override via `monkeypatch` at TEST-RUN time
    (inside setup/teardown, not collection) -- monkeypatch guarantees the
    original value is restored after the test regardless of pass/fail/error,
    immune to collection-order effects entirely.

    It also resets `core.memory.episodic`'s process-wide singleton DB
    connection (`close_db_connection()`, which clears both the connection and
    the cached encryption key) on both setup and teardown -- required because
    `EpisodicMemory`'s singleton caches its connection on FIRST use in the
    process; without this reset, a later `VECTOR_DB_PATH` change has no
    effect on an already-open connection, silently defeating isolation for
    any test that runs after another test (or the leaking pattern above) has
    already opened a connection.

    Adopted by: tests/test_e1_persistent_learning.py,
    tests/test_r10_decision_provenance.py,
    tests/test_task89c_goal_progress.py,
    tests/test_r11_learning_integration.py.

    Does NOT isolate EpistemicTracker/CounterfactualMemory (they ignore
    VECTOR_DB_PATH entirely -- isolate those separately via their own
    explicit `db_path=` constructor kwarg).
    """
    import core.memory.episodic as ep

    db_path = str(tmp_path / "isolated_vector.db")
    monkeypatch.setenv("VECTOR_DB_PATH", db_path)
    monkeypatch.setenv("VECTOR_DB_KEY", "isolated-test-key-not-for-production")
    try:
        ep.close_db_connection()
    except Exception:
        pass
    yield db_path
    try:
        ep.close_db_connection()
    except Exception:
        pass
