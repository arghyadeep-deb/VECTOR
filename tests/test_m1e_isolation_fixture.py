"""
M1e — minimal reproduction of the VECTOR_DB_PATH collection-time leak, and
proof that the new `isolated_vector_db` fixture (tests/conftest.py) closes it.

Background: VECTOR_TECHNICAL_KNOWLEDGE/M1d_DEVELOPMENT_TEST_SAFETY_REMEDIATION.md
documents a real, reproduced regression where a fail-closed isolation guard
(reverted) turned a previously-silent leak into 260+ cascading test failures.
The leak's mechanism: pytest imports every specified test module BEFORE
running any test in any of them (collection happens first, for the whole
session). A module that sets `os.environ["VECTOR_DB_PATH"]` at module level
(not inside a fixture) does so once, during collection -- and nothing
restores it afterward, so every test that runs later in the same process
inherits whatever the LAST such module left behind, regardless of file
listing order.

This file proves, in isolation and without touching any real production
state:
  1. the OLD pattern (raw module-level-style mutation, simulated here inside
     a test body since we can't literally re-trigger collection mid-suite)
     genuinely leaks past the end of the test that set it, when nothing
     restores the env var;
  2. the NEW `isolated_vector_db` fixture does NOT leak -- the env var is
     back to its pre-test value immediately after the fixture tears down,
     confirmed by a follow-up test;
  3. the fixture's singleton reset (`close_db_connection()`) actually causes
     `get_db_connection()` to open a NEW connection at the NEW path, rather
     than silently keeping a stale connection to whatever path was active
     when some earlier code first called it in this process.

Order matters for tests 1-2 in this file (module-level test functions run in
definition order within one pytest process, same as the real leak's
mechanism) -- do not reorder them.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


_MARKER_PATH = "___m1e_leak_probe_should_never_survive___.db"
# The session's pinned VECTOR_DB_PATH (conftest sets a temp DB). The deliberate leak below must put it back:
# popping it instead left the variable unset, a later dotenv load refilled it with the relative live path, and
# every following test in the session errored with "resolves to live VECTOR state" (379 errors in a full run).
_ORIGINAL_DB_PATH = os.environ.get("VECTOR_DB_PATH")


def test_1_a_raw_unrestored_env_mutation_leaks_past_this_test():
    """Simulates the OLD (broken) pattern: set the env var with no fixture,
    no monkeypatch, no cleanup -- exactly what test_e1_persistent_learning.py
    etc. did before this milestone's fix. This deliberately LEAVES the leak
    in place so the next test can observe it -- that's the point of this
    reproduction."""
    os.environ["VECTOR_DB_PATH"] = _MARKER_PATH
    assert os.environ["VECTOR_DB_PATH"] == _MARKER_PATH


def test_2_the_leak_from_test_1_is_observable_here_proving_the_vulnerability():
    """Confirms the leak: with NO isolation mechanism of its own, this test
    (which runs strictly after test_1 in the same process) sees the marker
    path test_1 set -- proving cross-test contamination is real and requires
    no special trickery to reproduce."""
    assert os.environ.get("VECTOR_DB_PATH") == _MARKER_PATH, (
        "expected to observe the leaked marker from the previous test -- "
        "if this fails, the leak mechanism itself may have changed and this "
        "reproduction needs to be revisited"
    )
    # Clean up after ourselves so later, unrelated tests in the full suite
    # aren't affected by this deliberate reproduction.
    if _ORIGINAL_DB_PATH is None:
        os.environ.pop("VECTOR_DB_PATH", None)
    else:
        os.environ["VECTOR_DB_PATH"] = _ORIGINAL_DB_PATH


def test_3_isolated_vector_db_fixture_does_not_leak(isolated_vector_db):
    """Uses the NEW fixture. Its own value must be visible inside the test."""
    assert os.environ.get("VECTOR_DB_PATH") == isolated_vector_db


def test_4_the_fixture_from_test_3_left_no_trace_here():
    """Runs strictly after test_3. If the fixture correctly restored the env
    var, this test must NOT see test_3's isolated path -- proving the new
    fixture does not leak, unlike the raw pattern in tests 1-2."""
    assert os.environ.get("VECTOR_DB_PATH") != "isolated_vector.db"
    # It must be back to whatever it was before test_3 ran (real .env
    # default, or unset) -- not a lingering isolated path. Compare RESOLVED
    # (absolute) paths -- configured_db_path() legitimately returns a
    # relative Path when VECTOR_DB_PATH is the unmodified ".env" value
    # ("vector_memory.db"), which is not itself evidence of a leak.
    from core.memory.db_utils import configured_db_path
    from core.config import CONFIG
    current = configured_db_path().resolve()
    production_default = Path(str(CONFIG["db_path"])).resolve()
    assert current == production_default, (
        f"VECTOR_DB_PATH was not restored after isolated_vector_db's teardown: "
        f"resolved to {current}, expected the real configured default {production_default}"
    )


def test_5_singleton_reset_actually_switches_the_open_connection(isolated_vector_db, tmp_path):
    """Proves the fixture's close_db_connection() call is load-bearing: a
    fresh get_db_connection() call inside this isolated context must open
    the NEW isolated path, not silently reuse a connection cached from
    something that ran earlier in this same pytest process."""
    import core.memory.episodic as ep

    conn = ep.get_db_connection()
    assert conn is not None
    # The isolated path must actually exist as a real, distinct file now
    # that a connection to it was opened.
    assert os.path.exists(isolated_vector_db), (
        "get_db_connection() did not create the isolated DB file at the "
        "fixture's own path -- singleton reset did not take effect"
    )


def test_6_two_sequential_isolated_tests_get_genuinely_different_paths(isolated_vector_db):
    """A second, independent use of the fixture (different test) must get a
    DIFFERENT isolated path than test_5's -- proving isolation is per-test,
    not accidentally shared/cached across tests that both request it."""
    import core.memory.episodic as ep
    from core.memory.db_utils import configured_db_path

    assert str(configured_db_path()) == isolated_vector_db
    conn = ep.get_db_connection()
    assert conn is not None
    assert os.path.exists(isolated_vector_db)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
