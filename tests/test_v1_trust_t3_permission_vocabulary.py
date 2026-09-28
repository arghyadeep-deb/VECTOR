"""V1 TRUST CLOSURE — T3 (permission / handler vocabulary alignment) tests.

Background (OWNER_ROUTING_CLOSURE_REPORT.md Sections 23/28): owner routing
could now resolve real capabilities and reach Candidate -> DecisionEngine,
but three independently maintained vocabularies had drifted apart:

  1. routing      — `DISTRICT_TASK_MAP` (task_type -> district)
  2. permission   — `CONFIG["permission"]` GREEN/YELLOW/RED tiers
  3. execution    — `PermissionGateway._execute_action`'s handlers (the only
                    owner-path route to a real district agent is its narrow,
                    individually-verified `_PLAN_COMPOSABLE_ACTION_TYPES`
                    dispatch allowlist)

Findings proven by these tests (source-traced 2026-09-21):
  * Real, read-only GREEN capabilities with real district handlers
    (`git_status`/`check_git`/`git_log`/`recent_commits` -> GitBot,
    `search_arxiv` -> PaperReader) had NO owner-path execution route:
    `_execute_action` fell through to `not_implemented`.
  * `/command` reported such a `not_implemented` execution as
    "Done — X completed." with `action_taken=X` and a 0.8 policy reward —
    a phantom success (`/ws/command` already refuses this: RR-3.6 §15).
  * `research_papers` (a real DISTRICT_TASK_MAP key) had no permission tier
    and no handler; the real executable capability is `search_arxiv`.
  * `index_codebase` was deliberately left unregistered here (2026-09-21):
    its real handler runs a 300s MCP subprocess that BUILDS an index (a
    write). 2026-09-24 UPDATE: an independent security review found this
    exact gap live -- Governor.dispatch()'s own new authorization-boundary
    fix only gated FORBIDDEN/YELLOW/RED, leaving `index_codebase` (and 626
    other real DISTRICT_TASK_MAP capabilities) UNKNOWN and reachable
    unguarded via any direct Governor.dispatch() call, bypassing
    PermissionGateway.execute()'s own fail-closed UNKNOWN handling. All
    627 were traced to their real handler code and classified;
    `index_codebase` is now RED (real write confirmed, same as this
    docstring always said) rather than left UNKNOWN -- UNKNOWN was never
    the goal, it was a placeholder for "not yet classified."

Nothing here relaxes a tier: RED/YELLOW/FORBIDDEN membership from 2026-09-21
is asserted frozen (2026-09-24 additions from the classification above are
tracked separately in `_FROZEN_RED`/`_FROZEN_YELLOW` below, each dated).

Per .claude/rules/testing.md only external boundaries are mocked (LLM,
phone notification, `Governor.dispatch` = the district-agent boundary);
PermissionGateway tier + dispatch-allowlist logic and `command_endpoint`
run as real production code.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.city import governor
from core.city.governor import Governor
from core.city.intent_matcher import IntentMatcher
from core.config import CONFIG
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import Action, PermissionGateway


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _FakeCompletionResult:
    def __init__(self, content: str):
        self.content = content


def _mock_client(content: str):
    async def _chat(*args, **kwargs):
        return _FakeCompletionResult(content)
    fake = AsyncMock()
    fake.chat = _chat
    return fake


def _llm(task_type: str, district: str, confidence: float = 0.95) -> str:
    return (
        '{"is_action": true, "task_type": "%s", "district": "%s", "confidence": %s}'
        % (task_type, district, confidence)
    )


# ── 1/2. Verified real, read-only capabilities are executable from the owner
#        path (and retrieval capability required by T1) ─────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("action_type", ["git_status", "check_git", "git_log", "recent_commits", "search_arxiv"])
async def test_verified_readonly_capability_reaches_its_real_handler(action_type):
    payload = {"branch": "main", "modified": [], "staged": [], "untracked": []}
    dispatch = AsyncMock(return_value=payload)
    gw = PermissionGateway()
    assert gw._classify(action_type) == "GREEN"
    with patch.object(Governor, "dispatch", dispatch), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()):
        result = await gw.execute(Action(action_type=action_type, params={"query": "x"}, proposed_by="api_command"))
    assert result.level == "GREEN"
    assert dispatch.await_count == 1, f"{action_type} must be dispatched to its real district handler"
    assert dispatch.await_args.args[0]["type"] == action_type, "dispatched identity must equal authorized identity"
    assert result.result.get("status") != "not_implemented", result.result


# ── 3/4/5. Existing tiers unchanged; nothing lowered or added ──────────────

_FROZEN_RED = {
    'block_ip', 'browser_task', 'click_screen', 'code_debug', 'code_fix', 'code_generate', 'code_task',
    'content_publish', 'delete_files', 'deploy_production', 'desktop_task', 'download_file', 'execute_code',
    'financial_transaction', 'gui_task', 'hand_browser', 'hand_clip', 'hand_content', 'hf_train', 'kill_process',
    'launch_app', 'launch_terminal', 'overwrite_note_personal', 'pc_click', 'pc_launch_app', 'pc_type',
    'push_github', 'run_experiment_cycle', 'run_shell_command', 'send_email', 'send_message_routine',
    'solana_swap_execute', 'unblock_ip', 'vision_control', 'vt_backtest',
    # 2026-09-23: deliberate addition (permission-boundary audit fix) --
    # "web_task" is a real, live alias GUIAutomationAgent treats
    # identically to the already-RED "browser_task" (same capability,
    # same district per governor.py's DISTRICT_TASK_MAP), but it was never
    # classified anywhere, leaving it UNKNOWN and reachable with zero
    # gateway check. This is a tier fix this freeze test is not meant to
    # catch, so the frozen snapshot is updated to include it.
    'web_task',
    # 2026-09-24: deliberate addition -- closing the Governor.dispatch()
    # UNKNOWN-tier residual an independent review found (see the module
    # docstring's index_codebase update above). Each of these 16 is a
    # real DISTRICT_TASK_MAP capability confirmed by direct trace of its
    # real handler code to have a genuine hard-to-reverse side effect
    # (real trade/order execution, real code-index writes, real peer
    # broadcast, real infra deploy/restart/backup) -- see core/config.py's
    # own 2026-09-24 comment on this list for the per-route evidence.
    'vc_index', 'vc_update', 'vc_graph_build', 'index_codebase', 'str_replace',
    'execute_trade', 'place_order', 'solana_execute', 'solana_order',
    'hedge_trade', 'hedge_run', 'broadcast', 'delegate_task',
    'deploy', 'restart', 'backup',
    # 2026-09-24 (round 5, independent review finding -- HIGH): both were
    # classified GREEN in the first pass of the sweep above, but each is
    # real and dangerous on its own merits, independent of the
    # params.action dispatch-order bug fixed the same day in
    # code_conductor_agent.py/mlops_agent.py. See core/config.py's own
    # 2026-09-24 comment on this RED addition for the evidence.
    'code_conduct', 'hf_hub',
    # 2026-09-24 (round 6, independent review finding -- HIGH): exact
    # aliases of already-RED vc_index/vc_graph_build inside
    # code_intel_agent.py's own `elif task_type in (...)` branches, plus
    # vc_watch whose default params.action="start" immediately performs
    # the same real index-update write as vc_update. See core/config.py's
    # own 2026-09-24 round-6 comment for the evidence.
    'code_index', 'vc_graph', 'dependency_graph', 'vc_watch',
    # 2026-09-25 (Governor untiered-name closure):
    'cleanup_logs', 'delete', 'publish', 'upload', 'prune',
    # 2026-09-25: owner-approved tier proposals (PHASE4_TIER_COVERAGE_REPORT.md), 18 RED.
    'autonomous_chaining', 'autopilot_trigger', 'create_and_upload', 'cross_machine', 'delete_client',
    'escalate', 'execute_scheduled_uploads', 'github', 'hot_reload', 'prune_retention',
    'rollback', 'run_pending', 'schedule_upload', 'upload_instagram', 'upload_tiktok', 'upload_twitter',
    'upload_youtube',
}
_FROZEN_YELLOW = {
    'add_deadline', 'commit_code', 'create_calendar_event', 'create_project', 'finance_report', 'journal',
    'log_exercise', 'monthly_report', 'pc_screenshot', 'run_tests', 'set_reminder', 'weekly_journal',
    'write_note_personal',
    # 2026-09-23: deliberate addition (permission-boundary audit fix) --
    # home_control used to execute with ZERO gateway check at all (a real
    # RULE 3 violation, not a tier change this freeze test was meant to
    # catch); it is now correctly gated instead of ungated, so the freeze
    # intentionally admits this one new member.
    'home_control',
    # 2026-09-24: deliberate addition -- same Governor.dispatch()
    # UNKNOWN-tier residual as _FROZEN_RED above; these 30 are real but
    # lower-stakes/reversible writes (local code edits, drafts, generated
    # media not yet published, internal memory writes, calendar writes,
    # physical device control, a confirmed-real chained-dispatch
    # mechanism). See core/config.py's own 2026-09-24 comment on this
    # list for the per-route evidence.
    'git', 'refactor', 'minimal_change', 'context_artifacts',
    'draft_email', 'draft_reply',
    'make_video', 'site_video', 'website_to_video', 'video_pipeline',
    'animate_image', 'comfyui', 'lipsync', 'render_html', 'url_capture',
    'smart_home', 'chain', 'autopilot', 'incident', 'post_mortem', 'retry_check',
    'entity_add', 'knowledge_add', 'knowledge_relate', 'relation_add', 'remember',
    'calendar', 'deadline', 'class', 'schedule',
    # 2026-09-24 (round 6, independent review finding -- MEDIUM):
    # place_pin/intel_pin route to VectorIntelAgent's real
    # sb.place_pin() (ShadowBroker classifies it among its own
    # WRITE_COMMANDS) -- reversible/local-state mutation, not GREEN
    # read-only.
    'place pin', 'intel pin',
    # 2026-09-25 (Governor untiered-name closure):
    'backup_db', 'write', 'generate', 'create', 'create_branch', 'update_draft', 'generate_tests', 'merge',
    'add_call_contact', 'add_course',
    # 2026-09-25 proposals plus alert_anomaly, demoted after its persisted threshold mutation was traced.
    'acknowledge', 'acknowledge_alert', 'alert_anomaly', 'add_background_music', 'add_client', 'add_subtitles',
    'add_transitions', 'adjust_voice_speed', 'analyze_feedback', 'blocklist', 'build_storyboard', 'capture_url',
    'clone_voice', 'create_note', 'dead_code_cleanup', 'detection_rule', 'district_report', 'download_dataset',
    'export_report', 'extract_audio', 'fetch_trending', 'generate_batch', 'generate_captions',
    'generate_config', 'generate_highlight_captions', 'generate_in_my_voice', 'generate_response',
    'generate_subtitles', 'generate_tags', 'generate_voice', 'health_check', 'link_notes', 'log_step',
    'memory_store', 'merge_clips', 'network_scan', 'organize_notes', 'port_scan', 'preprocess_data',
    'process_event', 'refactor_clean', 'remove_metric', 'save_note', 'scan_artifact', 'scan_vulnerabilities',
    'start_run', 'title_thumbnail', 'tokenize_data', 'track_metric', 'translate_captions', 'trim_video',
    'update_client', 'yt_dlp',
    # 2026-09-28 (T9-fix-1, Codex external review finding): discard_draft/move were untiered agent-
    # declared capabilities on email_agent.py -- Governor._is_known_task_type() let them dispatch with
    # ZERO PermissionGateway involvement. Both are real local mailbox-state mutations (discard a draft,
    # move an email between folders), no external send -- YELLOW, not RED. See
    # VECTOR_TECHNICAL_KNOWLEDGE/T9_FIX1_CAPABILITY_TIER_GAP.md.
    'discard_draft', 'move',
    # 2026-09-29 SELF_DEV_P9_LEGAL_COMPLIANCE: owner-approved new district.
    # All ten advisory-only capabilities deliberately default to YELLOW
    # because their outputs can influence regulated legal/healthcare work.
    # No existing tier moved and no GREEN exception was made. See
    # VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P9_LEGAL_COMPLIANCE.md.
    'healthcare_service_brief', 'healthcare_service_check',
    'healthcare_marketing_brief', 'healthcare_marketing_check',
    'legal_billing_brief', 'legal_billing_check',
    'legal_intake_brief', 'legal_intake_check',
    'legal_document_brief', 'legal_document_check',
}


def test_red_and_yellow_tiers_are_frozen():
    perm = CONFIG["permission"]
    assert set(perm["red"]) == _FROZEN_RED, "RED tier membership must not change in T3"
    assert set(perm["yellow"]) == _FROZEN_YELLOW, "YELLOW tier membership must not change in T3"


def test_no_capability_was_added_to_green_and_representative_tiers_hold():
    perm = CONFIG["permission"]
    gw = PermissionGateway()
    for green in ("check_attendance", "search_web", "git_status", "search_arxiv", "script"):
        assert green in perm["green"] and gw._classify(green) == "GREEN"
    for yellow in ("commit_code", "set_reminder", "create_project"):
        assert gw._classify(yellow) == "YELLOW"
    for red in ("send_email", "execute_code", "push_github", "deploy_production", "delete_files"):
        assert gw._classify(red) == "RED"
    # 2026-09-24 UPDATE: index_codebase was classified as part of closing
    # the Governor.dispatch() UNKNOWN-tier residual (see module
    # docstring). It has a real write handler (CodeIntelAgent) -> RED, as
    # this file's own original docstring already said it should be if it
    # were ever classified.
    #
    # research_papers was BRIEFLY classified GREEN during that same sweep
    # (reasoning: no real handler at that exact string) and then reverted
    # -- tests/test_owner_paper_retrieval_routing.py:309 depends on
    # research_papers staying UNKNOWN as a deliberate security forcing
    # function: it's the mechanism that makes ALL paper-retrieval
    # requests go through `_fold_paper_retrieval_alias()`'s validated
    # recency/academic-cue/topic check before ever reaching search_arxiv,
    # rather than allowing a raw "research_papers" dispatch to slip
    # through a GREEN passthrough ungated. "No real handler" is not a
    # sufficient reason to classify GREEN when something else's security
    # design relies on the UNKNOWN fail-closed behavior itself.
    assert gw._classify("index_codebase") == "RED"
    assert gw._classify("research_papers") == "UNKNOWN"


# ── 6. Unknown / unimplemented stays UNKNOWN and blocked ──────────────────

@pytest.mark.asyncio
async def test_unknown_actions_remain_fail_closed():
    # 2026-09-24: "index_codebase" was this test's original UNKNOWN example
    # but is now correctly classified RED (see test_no_capability_was_added_
    # to_green_and_representative_tiers_hold's own 2026-09-24 update) --
    # swapped for a string with no real DISTRICT_TASK_MAP entry at all, so
    # this test still proves what it's meant to: a truly unclassified
    # action_type stays UNKNOWN and fail-closed.
    gw = PermissionGateway()
    for unknown in ("totally_made_up_action", "another_invented_action_xyz"):
        assert gw._classify(unknown) == "UNKNOWN"
    with patch.object(PermissionGateway, "_notify", new=AsyncMock()), \
         patch.object(Governor, "dispatch", new=AsyncMock(return_value={"status": "ok"})) as dispatch:
        result = await gw.execute(Action(action_type="totally_made_up_action", params={}, proposed_by="api_command"))
    assert result.level == "UNKNOWN" and result.approved is False
    assert dispatch.await_count == 0, "an UNKNOWN action must never reach a district handler"


# ── 7. Registered-but-unimplemented must not look executed ────────────────

class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "v1_trust_t3_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_v1_trust_t3")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


async def _run_endpoint(text, llm_json, isolated_episodic, dispatch_result=None):
    policy_calls = []
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()), \
         patch.object(Governor, "dispatch", new=AsyncMock(return_value=dispatch_result or {"status": "ok"})), \
         patch.object(commands_router, "update_policy", side_effect=lambda a, h, r: policy_calls.append((a, r))):
        response = await commands_router.command_endpoint(
            body=CommandRequest(text=text),
            ctx_engine=_FakeContextEngine(),
            decision_engine=DecisionEngine(),
            perm_gateway=PermissionGateway(),
            episodic_mem=isolated_episodic,
        )
    return response, policy_calls


@pytest.mark.asyncio
async def test_registered_but_unimplemented_action_is_not_reported_as_done(isolated_episodic):
    """`daily_review` is GREEN-registered but has no `_execute_action`
    handler on the owner path. It used to answer "Done — daily review
    completed." with action_taken=daily_review and a 0.8 reward while
    nothing ran."""
    response, policy_calls = await _run_endpoint(
        "please go over how the afternoon went for me", _llm("daily_review", "reflection"), isolated_episodic
    )
    assert "done" not in response.response.lower(), response.response
    assert response.action_taken is None, "a not_implemented execution must not be reported as action_taken"
    assert policy_calls and policy_calls[0][1] < 0.5, (
        f"an action that did not execute must not earn the 0.8 success reward, got {policy_calls!r}"
    )


# ── 8. Alias resolves to the canonical executable identity ─────────────────

@pytest.mark.asyncio
async def test_research_papers_alias_resolves_to_canonical_search_arxiv():
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(_llm("research_papers", "knowledge"))):
        result = await governor.classify_chat_intent("could you dig up some recent papers on this topic")
    assert result.get("type") == "search_arxiv", result
    assert result.get("district") == "research"
    assert PermissionGateway()._classify(result["type"]) == "GREEN", (
        "permission must apply to the canonical executable identity"
    )


# ── 9. Deterministic routing for the demonstrated code-status shape ────────

@pytest.mark.asyncio
async def test_codebase_change_question_routes_to_readonly_git_capability():
    """V4 shape (report §23). The LLM is armed to raise: the route must be
    deterministic and land on the exact read-only identity, not an invented
    label snapped to the (non-read-only) `index_codebase`."""
    boom = AsyncMock()
    boom.chat = AsyncMock(side_effect=AssertionError("LLM must not be consulted for a deterministic route"))
    with patch("core.inference.provider_client.get_client", return_value=boom):
        result = await governor.classify_chat_intent(
            "Is there anything worth flagging that's shifted in the codebase recently?"
        )
    assert result.get("type") == "recent_commits", result
    assert result.get("district") == "coding"


@pytest.mark.asyncio
async def test_codebase_opinion_question_is_not_captured_by_the_route():
    llm_json = '{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)):
        result = await governor.classify_chat_intent("What do you think of a monolithic codebase versus microservices?")
    assert result.get("type") == "answer_question"


# ── 10. The owner sees the real evidence, never just "Done" ────────────────

@pytest.mark.asyncio
async def test_git_status_response_contains_real_status_evidence(isolated_episodic):
    payload = {"branch": "feature-x", "modified": ["a.py", "b.py"], "staged": [], "untracked": ["c.md"], "ahead": 2, "behind": 0}
    response, _ = await _run_endpoint(
        "how does the working tree look at the moment", _llm("git_status", "coding"), isolated_episodic, payload
    )
    assert "feature-x" in response.response and "2" in response.response
    assert response.action_taken == "git_status"


@pytest.mark.asyncio
async def test_recent_commits_response_contains_real_commit_evidence(isolated_episodic):
    payload = {"commits": [{"hash": "abc12345", "message": "Fix the frobnicator", "author": "A", "date": "2026-09-20T10:00:00"}]}
    response, _ = await _run_endpoint(
        "anything new in the codebase lately", _llm("recent_commits", "coding"), isolated_episodic, payload
    )
    assert "abc12345" in response.response and "frobnicator" in response.response


@pytest.mark.asyncio
async def test_empty_evidence_is_reported_honestly_not_as_done(isolated_episodic):
    response, _ = await _run_endpoint(
        "how does the working tree look at the moment", _llm("git_status", "coding"), isolated_episodic, {}
    )
    assert "done" not in response.response.lower(), response.response


# ── Correction pass (live matrix RY3/UA3, GC1) ─────────────────────────────

@pytest.mark.asyncio
async def test_handler_rejected_action_is_not_reported_as_executed(isolated_episodic):
    """Live RY3/UA3: an approved RED `execute_code` with no code was
    rejected by its handler (`status: rejected, reason: no code provided`)
    but /command answered "Confirmed and executed: execute_code." — the same
    phantom-success class as `not_implemented`."""
    async def _fake_exec(self, action):
        return {"status": "rejected", "reason": "no code provided", "action": action.action_type}

    with patch("core.inference.provider_client.get_client",
               return_value=_mock_client(_llm("execute_code", "ops", 1.0))), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()), \
         patch.object(PermissionGateway, "_handle_red_tier", new=AsyncMock(return_value="defer")), \
         patch.object(PermissionGateway, "_wait_for_confirmation", new=AsyncMock(return_value=True)), \
         patch.object(PermissionGateway, "_execute_action", _fake_exec):
        response = await commands_router.command_endpoint(
            body=CommandRequest(text="Execute that script and run it now."),
            ctx_engine=_FakeContextEngine(), decision_engine=DecisionEngine(),
            perm_gateway=PermissionGateway(), episodic_mem=isolated_episodic,
        )
    assert "executed" not in response.response.lower().replace("nothing was executed", ""), response.response
    assert "no code provided" in response.response
    assert response.action_taken is None


@pytest.mark.asyncio
async def test_state_of_my_repo_phrasing_routes_to_git_status():
    boom = AsyncMock()
    boom.chat = AsyncMock(side_effect=AssertionError("LLM must not be consulted for a deterministic route"))
    with patch("core.inference.provider_client.get_client", return_value=boom):
        result = await governor.classify_chat_intent("What's the state of my git repository at the moment?")
    assert result.get("type") == "git_status", result
    assert result.get("district") == "coding"


# ── 7. 2026-09-25 owner-approved tier proposals ──────────────────────────────────────────────────────────────────────

_NEW_GREEN = ['active_alerts', 'alert_anomaly', 'analyze_competitor', 'analyze_financials', 'analyze_gaps', 'ast_analysis', 'calculate_indicators', 'check_pep8', 'check_valuation', 'client_summary', 'code_review', 'compare_to_sector', 'deep_code_review', 'dependency_trace', 'design_architecture', 'detect_anomalies', 'detect_patterns', 'dividend_analysis', 'estimate_compute', 'evaluate', 'extract_action_items', 'extract_concepts', 'get_at_risk_clients', 'get_client', 'get_comparison', 'get_metric_summary', 'get_price_data', 'get_progress', 'get_top_clients', 'get_trend', 'get_voices', 'hedge_status', 'identify_improvements', 'job_history', 'job_queue', 'job_status', 'list_alerts', 'list_clients', 'list_incidents', 'list_models', 'list_rules', 'list_skills', 'log_query', 'match_event', 'memory_query', 'obra_review', 'order_summary', 'portfolio_summary', 'prioritize_gaps', 'profile_competitor', 'progress_report', 'recommend', 'review_security', 'root_cause', 'security_code_review', 'session_report', 'siem_alerts', 'siem_stats', 'suggest_learning_path', 'suggest_prerequisites', 'summarize_transcript', 'text_to_ssml', 'transcribe_audio', 'upload_history']
_NEW_GREEN.remove("alert_anomaly")  # handler persists threshold changes and awards HP; it is not read-only


def test_owner_approved_proposals_classify_as_approved():
    gw = PermissionGateway()
    for name in _NEW_GREEN:
        assert gw._classify(name) == "GREEN", name
    for name in ['acknowledge', 'acknowledge_alert', 'add_background_music', 'add_client', 'add_subtitles', 'add_transitions', 'adjust_voice_speed', 'analyze_feedback', 'blocklist', 'build_storyboard', 'capture_url', 'clone_voice', 'create_note', 'dead_code_cleanup', 'detection_rule', 'district_report', 'download_dataset', 'export_report', 'extract_audio', 'fetch_trending', 'generate_batch', 'generate_captions', 'generate_config', 'generate_highlight_captions', 'generate_in_my_voice', 'generate_response', 'generate_subtitles', 'generate_tags', 'generate_voice', 'health_check', 'link_notes', 'log_step', 'memory_store', 'merge_clips', 'network_scan', 'organize_notes', 'port_scan', 'preprocess_data', 'process_event', 'refactor_clean', 'remove_metric', 'save_note', 'scan_artifact', 'scan_vulnerabilities', 'start_run', 'title_thumbnail', 'tokenize_data', 'track_metric', 'translate_captions', 'trim_video', 'update_client', 'yt_dlp']:
        assert gw._classify(name) == "YELLOW", name
    for name in ['autonomous_chaining', 'autopilot_trigger', 'create_and_upload', 'cross_machine', 'delete_client', 'escalate', 'execute_scheduled_uploads', 'github', 'hot_reload', 'prune_retention', 'rollback', 'run_pending', 'schedule_upload', 'upload_instagram', 'upload_tiktok', 'upload_twitter', 'upload_youtube']:
        assert gw._classify(name) == "RED", name


def test_mutating_green_proposals_demoted_after_tracing_their_handlers_are_yellow():
    gw = PermissionGateway()
    for name in ("alert_anomaly", "analyze_feedback", "district_report", "health_check", "generate_response"):
        assert gw._classify(name) == "YELLOW", name


def test_publishing_and_destructive_capabilities_are_red():
    gw = PermissionGateway()
    for name in ("upload_youtube", "upload_instagram", "upload_tiktok", "upload_twitter", "delete_client",
                 "prune_retention", "rollback", "github", "hot_reload"):
        assert gw._classify(name) == "RED", name


def test_pure_routing_labels_stay_unknown_and_blocked():
    gw = PermissionGateway()
    for label in ("budgeting", "tracking", "patterns", "audit"):
        assert gw._classify(label) == "UNKNOWN", label
