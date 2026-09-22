"""RG-D2a — deterministic situation_hash stability for the live, owner-run
verification probe shape (git_status / recent_commits).

RG-D2a's owner-run verification depends on a plain, side-effect-free, real-
handler GREEN command reliably reaching:

    Candidate -> DecisionEngine.evaluate() -> PermissionGateway.execute()
    -> Governor.dispatch() -> the real GitBot handler

with a STABLE `PolicyMemory.make_situation_hash(action_type, params)` value
across two separate calls carrying the identical input text. If the
situation_hash were unstable (e.g. because params carried something
non-deterministic like a timestamp), the live probe's own hash-comparison
step would be inherently flaky -- these tests prove the exact shape it
depends on is deterministic BEFORE that live probe is ever run.

The two probe texts below are the exact 'e.g.' phrasings named in the
mission ("what's the status of our git repo", "anything changed in our repo
recently") and are proven (test class 1 below) to be resolved by
`classify_chat_intent()`'s deterministic `_REGEX_PRECLASSIFY` patterns in
core/city/governor.py -- never the embedding matcher or the LLM fallback --
so nothing about this test's determinism depends on an LLM/embedding call
happening to return the same thing twice.

Per .claude/rules/testing.md, `permission_gateway.py` and
`session_hydration_prompt()` are NEVER mocked here. `Governor.dispatch()` is
ALSO left real (an independent review of an earlier version of this file
correctly found that mocking it only proves PermissionGateway called the
mock, not that Governor routing and GitBot handler selection actually work)
-- real registry lookup, real capability match, real `GitBot.run()`. A real,
single-agent `AgentRegistry` (scoped to this test via a `get_registry()`
monkeypatch, never the process-wide singleton) supplies the real GitBot
instance so dispatch has something real to route to.

The ONLY boundary mocked is `git.Repo(...)` -- the actual subprocess/
filesystem git call GitBot's handler would otherwise perform to open a real
repository -- plus the phone notifier (Pushover, an external service) and
`update_policy` (spied, per the mission's own instruction, to capture the
real `situation_hash` PolicyMemory computed for this call without a second,
possibly-diverging DB read).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.city.agent_registry import AgentRegistry
from core.city.governor import classify_chat_intent
from core.loop.context_engine import ContextEngine
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory
from districts.coding.git_bot import GitBot

# Exact "e.g." probe phrasings from the mission -- both must be resolved by
# governor.py's deterministic _REGEX_PRECLASSIFY, never the LLM/embedding path.
GIT_STATUS_PROBE = "what's the status of our git repo"
RECENT_COMMITS_PROBE = "anything changed in our repo recently"


def _fake_git_status_repo() -> MagicMock:
    """Just enough of gitpython's `Repo` surface for the real
    `GitBot.get_status()` to run its own real branch/diff/untracked logic
    against, without ever touching a real repository on disk."""
    repo = MagicMock()
    repo.head.is_detached = False
    repo.active_branch.name = "main"
    repo.active_branch.tracking_branch.return_value = None
    repo.index.diff.return_value = []
    repo.untracked_files = []
    return repo


def _fake_recent_commits_repo() -> MagicMock:
    """Just enough of gitpython's `Repo` surface for the real
    `GitBot.get_recent_commits()` to run its own real commit-rendering logic
    against, without ever touching a real repository on disk."""
    commit = MagicMock()
    commit.hexsha = "deadbeefcafebabe"
    commit.message = "probe commit\n"
    commit.author = "T. Ester"
    commit.committed_datetime.isoformat.return_value = "2026-09-22T00:00:00"
    repo = MagicMock()
    repo.iter_commits.return_value = [commit]
    return repo


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    """Fresh, isolated SQLite DB -- never the real vector_memory.db."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "rgd2a_probe_stability_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_rgd2a_probe_stability")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


@pytest.fixture()
def isolated_gitbot_registry(monkeypatch):
    """A real, single GitBot instance in an `AgentRegistry` scoped to this
    test. `Governor.dispatch()` (left real -- see module docstring) looks
    this up via `core.city.agent_registry.get_registry()`, monkeypatched
    here so the test neither depends on nor pollutes the process-wide
    agent-registry singleton (which nothing bootstraps in a bare test run)."""
    registry = AgentRegistry()
    registry.register(GitBot())
    monkeypatch.setattr("core.city.agent_registry.get_registry", lambda: registry)
    return registry


async def _run_probe(text: str, isolated_episodic, fake_repo_factory):
    """Drives the real /command pipeline end to end for one probe call:
    real classify_chat_intent() (REGEX_PRECLASSIFY), real Candidate
    construction, real DecisionEngine.evaluate(), real
    PermissionGateway.execute() (spied, never replaced), real
    Governor.dispatch() (real registry lookup, real capability match), and
    the real GitBot.run() -> get_status()/get_recent_commits() handler code.
    `GitBot.run` is spied (never replaced) to independently confirm the real
    handler -- not a stub -- was actually invoked with the authorized
    action_type."""
    policy_calls: list[tuple] = []
    gateway_results: list = []
    gitbot_run_calls: list[dict] = []
    real_execute = PermissionGateway.execute
    real_gitbot_run = GitBot.run

    async def spy_execute(self, action):
        result = await real_execute(self, action)
        gateway_results.append(result)
        return result

    async def spy_gitbot_run(self, task):
        gitbot_run_calls.append(task)
        return await real_gitbot_run(self, task)

    with patch("git.Repo", return_value=fake_repo_factory()), \
         patch.object(GitBot, "run", new=spy_gitbot_run), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()), \
         patch.object(PermissionGateway, "execute", new=spy_execute), \
         patch.object(commands_router, "update_policy",
                      side_effect=lambda a, h, r: policy_calls.append((a, h, r))):
        response = await commands_router.command_endpoint(
            body=CommandRequest(text=text),
            ctx_engine=ContextEngine(),
            decision_engine=DecisionEngine(),
            perm_gateway=PermissionGateway(),
            episodic_mem=isolated_episodic,
        )
    return response, policy_calls, gateway_results, gitbot_run_calls


# ── 1. classify_chat_intent() REGEX_PRECLASSIFY determinism (no LLM) ───────
# Confirms the exact phrasing gap check the mission requires before any
# stability claim: both probe texts are resolved deterministically, with the
# LLM classifier never even consulted.

class TestRegexPreclassifyDeterminism:
    @pytest.mark.asyncio
    async def test_git_status_probe_routes_via_regex_preclassify_no_llm(self):
        boom = AsyncMock()
        boom.chat = AsyncMock(side_effect=AssertionError(
            "git_status probe must be resolved by REGEX_PRECLASSIFY -- the "
            "LLM classifier must never be consulted for this exact phrasing"
        ))
        with patch("core.inference.provider_client.get_client", return_value=boom):
            result = await classify_chat_intent(GIT_STATUS_PROBE)
        assert result["type"] == "git_status", result
        assert result["district"] == "coding", result
        assert result.get("source") == "regex_preclassify", result

    @pytest.mark.asyncio
    async def test_recent_commits_probe_routes_via_regex_preclassify_no_llm(self):
        boom = AsyncMock()
        boom.chat = AsyncMock(side_effect=AssertionError(
            "recent_commits probe must be resolved by REGEX_PRECLASSIFY -- "
            "the LLM classifier must never be consulted for this exact phrasing"
        ))
        with patch("core.inference.provider_client.get_client", return_value=boom):
            result = await classify_chat_intent(RECENT_COMMITS_PROBE)
        assert result["type"] == "recent_commits", result
        assert result["district"] == "coding", result
        assert result.get("source") == "regex_preclassify", result


# ── 2. End-to-end probe-shape stability through the real pipeline ──────────

class TestGitStatusProbeStability:
    @pytest.mark.asyncio
    async def test_reaches_real_handler_with_stable_situation_hash(
        self, isolated_episodic, isolated_gitbot_registry,
    ):
        resp1, calls1, gw1, run1 = await _run_probe(
            GIT_STATUS_PROBE, isolated_episodic, _fake_git_status_repo
        )
        resp2, calls2, gw2, run2 = await _run_probe(
            GIT_STATUS_PROBE, isolated_episodic, _fake_git_status_repo
        )

        # A. Candidate -> DecisionEngine: exactly one candidate evaluated, both calls.
        assert resp1.candidates_evaluated == 1, resp1
        assert resp2.candidates_evaluated == 1, resp2

        # B. Resolved action_type is exactly git_status, not 'respond' or an
        #    unrelated task_type -- both calls.
        assert resp1.action_taken == "git_status", resp1
        assert resp2.action_taken == "git_status", resp2

        # C. PermissionGateway.execute() -> Governor.dispatch() -> the real
        #    GitBot handler was reached (real handler path, not
        #    not_implemented) -- both calls.
        for gw in (gw1, gw2):
            assert len(gw) == 1
            assert gw[0].level == "GREEN"
            assert gw[0].executed is True
            assert gw[0].result.get("status") != "not_implemented", gw[0].result

        # D. The real GitBot.run() (never mocked/replaced) was actually
        #    invoked with the authorized action_type -- both calls. This is
        #    independent, direct evidence Governor really routed to the real
        #    handler, not just that the gateway's own result looked healthy.
        for run in (run1, run2):
            assert len(run) == 1
            assert run[0]["type"] == "git_status"

        # E. The owner sees real evidence (from GitBot's own real
        #    get_status() logic, run against the mocked git.Repo boundary),
        #    never a phantom "Done".
        assert "main" in resp1.response and "main" in resp2.response

        # F. IDENTICAL PolicyMemory.make_situation_hash(action_type, params)
        #    across two separate calls with the same input text.
        assert calls1 and calls2, "PolicyMemory write (update_policy) must happen for both calls"
        hash1, hash2 = calls1[0][1], calls2[0][1]
        assert hash1 == hash2, (
            "situation_hash must be identical across two separate /command "
            "calls carrying the identical git_status probe text"
        )
        expected_params = {
            "query": GIT_STATUS_PROBE, "content": GIT_STATUS_PROBE,
            "source": "api_command", "district": "coding",
        }
        assert hash1 == PolicyMemory.make_situation_hash("git_status", expected_params), (
            "the captured situation_hash must equal an independently computed "
            "canonical hash for the real (action_type, params) pair -- not "
            "merely self-consistent across the two calls"
        )


class TestRecentCommitsProbeStability:
    @pytest.mark.asyncio
    async def test_reaches_real_handler_with_stable_situation_hash(
        self, isolated_episodic, isolated_gitbot_registry,
    ):
        resp1, calls1, gw1, run1 = await _run_probe(
            RECENT_COMMITS_PROBE, isolated_episodic, _fake_recent_commits_repo
        )
        resp2, calls2, gw2, run2 = await _run_probe(
            RECENT_COMMITS_PROBE, isolated_episodic, _fake_recent_commits_repo
        )

        assert resp1.candidates_evaluated == 1, resp1
        assert resp2.candidates_evaluated == 1, resp2

        assert resp1.action_taken == "recent_commits", resp1
        assert resp2.action_taken == "recent_commits", resp2

        for gw in (gw1, gw2):
            assert len(gw) == 1
            assert gw[0].level == "GREEN"
            assert gw[0].executed is True
            assert gw[0].result.get("status") != "not_implemented", gw[0].result

        for run in (run1, run2):
            assert len(run) == 1
            assert run[0]["type"] == "recent_commits"

        assert "deadbeef" in resp1.response and "deadbeef" in resp2.response

        assert calls1 and calls2, "PolicyMemory write (update_policy) must happen for both calls"
        hash1, hash2 = calls1[0][1], calls2[0][1]
        assert hash1 == hash2, (
            "situation_hash must be identical across two separate /command "
            "calls carrying the identical recent_commits probe text"
        )
        expected_params = {
            "query": RECENT_COMMITS_PROBE, "content": RECENT_COMMITS_PROBE,
            "source": "api_command", "district": "coding",
        }
        assert hash1 == PolicyMemory.make_situation_hash("recent_commits", expected_params), (
            "the captured situation_hash must equal an independently computed "
            "canonical hash for the real (action_type, params) pair -- not "
            "merely self-consistent across the two calls"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
