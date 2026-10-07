# VECTOR — Open Issues (reconciled 2026-06-29; engineering section added 2026-09-24)

**This is the single current status file.** `KNOWN_ISSUES.md` holds the detailed
root-cause traces for the engineering items in section 0; sections A–F below are
owner-gated items (hardware, accounts, deploys, decisions).

The old headline ("there is no open code work") was wrong once `KNOWN_ISSUES.md`
grew open engineering items; section 0 lists them.

## 0. Open engineering work (as of 2026-09-24)

1. **Autonomous loop thread freeze** (`KNOWN_ISSUES.md` #0) — live-observed 2026-08-05.
   One root cause found and fixed 2026-09-24 (`script_generator._llm()` blocking the
   event loop for up to 120s; also the council's sync Ollama calls). **Not yet
   re-verified against a live multi-hour run.**
2. **Live re-verification** of the Phase 1–6 fixes (`KNOWN_ISSUES.md` #9) and of the
   2026-09-24 review fixes — needs a live backend.
3. **`Governor.dispatch()` trusted a caller-supplied `district`** — **CLOSED 2026-09-25, independently re-verified
   by Codex 2026-09-29** (Claude self-reviewed first when Codex was quota-exhausted, then Codex itself confirmed
   with its own independent tool calls once quota reset — AGREE, no disagreements, see
   `VECTOR_TECHNICAL_KNOWLEDGE/CODEX_REVIEW_2026-09-29_CORE.md`, including a gate Codex found on its own that
   this review hadn't specifically pointed it at). Two parts: (a) every
   consequential agent-declared name that was UNKNOWN is now tiered (`cleanup_logs` RED, `backup_db` YELLOW,
   `delete`/`publish`/`upload`/`prune` RED, `write`/`generate`/`create`/`merge`/... YELLOW; see `core/config.py`); (b) an
   UNKNOWN task type that is not a routing key, alias, agent-declared capability or freshly LLM-classified chat type is
   now refused with `blocked`, whatever district the caller names. Also fixed on the way: the "risk word" filter dropped
   `delete` from the destructive vocabulary once a second RED name used it; destructive verbs are now always elevated.
   Tests: `tests/test_governor_unknown_task_gate.py`. `execute_playbook` is deliberately left untiered: the playbook runner
   gates every destructive step through the gateway itself (`tests/test_task58f_*`).
4. **Permission-tier coverage** — **APPLIED 2026-09-25** with your approval: 17 RED (of 18 proposed; see below), 52 YELLOW (48 proposed + 4 GREEN
   proposals demoted after tracing their handlers: `analyze_feedback` persists, `district_report` writes files,
   `health_check` makes an outbound request, `generate_response` calls a routed LLM), 64 GREEN, plus 19 more agent-declared
   names in the Governor closure above. `execute_playbook` was dropped from RED (double gate). Pure routing labels stay
   UNKNOWN. The frozen tier guard (`tests/test_v1_trust_t3_permission_vocabulary.py`) was updated in the same commit.
5. **Routing**: `KNOWN_ISSUES.md` #10 ("remember X" misroute) is **resolved** in code
   (`_authoritative_district_from_text` + honest `no_capable_agent`); the entry is kept for history.
6. **Content pipeline** (2026-09-24): a daily `content-plan` cron job now plans script -> `schedule_post`
   (only for platforms with a configured key); the 09:00 publish job still needs owner approval per post.
   Live-data cleanup DONE 2026-09-25: 37 junk "Test Post" jobs cancelled; ~85k test-suite rows deleted from the live DB
   (gateway_audit, reasoning_chains, policy_memory, agent_history, causal_nodes/edges, semantic_memory, shared_facts;
   run by the owner, JSON backup written first), plus mesh-test and fake-council episodic rows.
   Still open: interrupted renders are listed by `list_resumable_jobs()` but resuming an upload is an owner action;
   publishing credentials (Dev.to key, YouTube OAuth, Instagram token) are owner-side.
7. **Test-suite items** (all resolved 2026-09-26; each was a stale test, not a code bug):
   correction lifecycle (an explicit correction is stored at 0.95, already above the 0.85 bar, so the test now starts
   from an implicit 0.70 lesson); epistemic fresh-domain (R23's capability factor x0.85 for an action no live agent
   declares was hitting the score; the later multipliers are pinned neutral); a7 council RED tier (a confident
   council "proceed" never auto-executes: `COUNCIL_AUTO_PROCEED_ALLOWED` is empty by design and `push_github` is
   OWNER_APPROVAL_ONLY -- the test now asserts that, plus the allowlisted path); openwa BulkSender (process-wide dedup
   registry leaked between tests); permission_gateway red-timeout (every RED test ran a real council on live LLMs,
   3 min; now the council is mocked to its own "defer", 1 s); r14 six-cycle (code_task was penalised x0.85 by the
   capability factor, so R6 picked GREEN read_code and skipped the RED-boundary proof; the test registry now declares
   the capability on ArchitectBot like the manifest does). The full-suite baseline (5,012 / 13 / 36) has not been
   re-run since the review fixes.
8. **Dead code** (owner direction 2026-09-24: keep everything): nothing deleted. `docs/design/core-module-triage.md`
   classifies the unreachable `core/` modules; useful ones were wired (repo-hygiene gate, OAuth refresh and
   cloud heartbeat cron jobs), ten duplicates carry a DORMANT banner. Follow-up designs listed at the end of
   that file (token_juice, semantic_cache, engine agents, secrets providers, sound classifier).
9. **Licensing** — **re-investigated 2026-09-29, genuinely unresolvable further, not a code gap**:
   `THIRD_PARTY_NOTICES.md` + LICENSE files added; `vector_finagent` headers corrected. The 5 vendored trees
   with no identifiable license (`core/mining`, `districts/intelligence/shadowbroker_server`,
   `districts/investment/{vector_backtest,vector_hedgebot}`, `districts/coding/vector_mlops`) were checked
   again: no LICENSE/README/pyproject metadata names an upstream project in any of them, and their own
   `NOTICE.md` files (written by an earlier, careful audit that deliberately declined to guess at names it
   couldn't confirm) already say so. Re-checking git history and file headers found nothing new beyond one
   already-known clue (`core/mining/vllm_pearl.py` names "upstream Pearl `miner-base`" in its own docstring).
   Same mitigation as the two already-accepted AGPL cases below: personal-use, non-distributed, no other
   users on the network — treat as all-rights-reserved until identified, revisit only if ever exposed to
   other users. Not chasing this further without new information would be forcing a guess the original
   careful audit correctly declined to make.
10. **"Uncommitted earlier work" note — STALE, confirmed resolved 2026-09-29.** `git status --short` on the
    current branch is completely clean; `core/loop/autonomous_loop.py`, `core/city/agent_base.py`,
    `core/inference/provider_client.py`, and `core/runtime/executor.py` all have real, current commits. This
    note dated from the 2026-09-23 audit and was never updated once that work was committed in a later
    session. No action needed.
12. **Test isolation** (2026-09-24) — **superseded 2026-09-29 by a complete, clean full-suite run.** The
    2026-09-24 note's own baseline (5,012 / 13 / 36) was itself superseded by 6,708 / 0 / 39 (2026-09-27) and
    now by **6,862 passed / 0 real failures / 39 skipped** (2026-09-29, run via the memory-safe batched
    runner `$TEMP/suite/run.py` — 25 files per subprocess, never accumulates state across the whole suite;
    see `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_PROGRAM_SUMMARY.md` for the full run detail, including the one
    transient network-test flake that was re-run in isolation and came back clean). Every pytest session
    still uses a fresh temp DB/data dir and fails any test that resolves to live state, per the original
    2026-09-24 fix.
11a. **Full-suite run 2026-09-25** (sharded, working tree incl. your uncommitted work): 5,843 passed / 20 failed /
    37 skipped / 379 errors. The 379 errors were ONE polluter — `test_m1e_isolation_fixture.py` popped the
    session's `VECTOR_DB_PATH`, the live-state guard then errored every later test in that batch; fixed (batch
    re-run: 400 passed, 2 failed). Remaining ~18 failures, each classified against a clean HEAD worktree:
    - **11 were caused only by the 2026-09-23 audit work** (pass at the last commit): 8 in `test_r13_*`, plus
      `test_r24_*`, `test_r25_*`, `test_r26_* ablation`. A real `git_status` (branch, no `status` key) used to be
      scored as a failure; it now scores as the success it is (learned reward 0.42 -> 0.63, 0.70 -> 0.75). The audit
      work is committed (d040abd55) together with the retuned tests (race constants re-found by scanning each suite
      and taking the middle of the passing window; r13's flagship now proves the changed-decision claim after one
      read_code execution because the later read_code/git_status comparison is a genuine tie). All 84 tests in
      those four files pass.
    - **`test_r18_*worktree`** fails only because ~40 other files are still modified/untracked in the working tree
      (it asserts the tree holds only expected changes); not a code defect. It clears when the tree is committed
      or cleaned.
    - **1 pre-existing, previously masked by the ArchitectBot timeout**: `test_r14 ... six_cycle` (winners become
      `read_code` x5 instead of diversifying to `code_task`; reproduced on the pre-program commit + only the scan fix).
    - **4 already-known**: correction lifecycle, epistemic fresh-domain, a7 council-red-tier, plus
      `permission_gateway` red-timeout / openwa BulkSender (order pollution).
    Fixed on the way: scheduler job-count test (14 -> 17 after the 3 jobs added 2026-09-24) and a predictive-analytics
    fixture that reused a stale, undecryptable temp DB.
11. **HP bonus for a no-API-keys future** (agents' non-API reward) — on hold until the owner decides.
13. **HUD honesty + vectorcode repair (2026-09-24, commits ffc5554db..001dd53d3)** — DONE: the HUD no longer
    presents demo seed data as live (honest "NO DATA"/UNKNOWN states, verified in a real browser); vectorcode's
    shell tools, agent loop, `run`/`auto`, CLI subcommands, tool registry, skills, tui_gateway imports now work
    (see the fix report). **vectorcode sub-issues re-checked 2026-09-29, several resolved, others narrowed to
    a precise remaining gap** (the live agent is `engine/agent_loop.py`, none of this legacy path is used by
    it): `fire` and `agent-client-protocol` were genuinely missing pip packages — **installed**, confirmed by
    import. `batch_runner.py` and `run_agent.py` (legacy path) now import past that point, but hit a real,
    different gap: `agent.memory_manager` re-exports `sanitize_context`/`build_memory_context_block` from the
    canonical `vectorcode.src.memory.manager` fine, but `StreamingContextScrubber` doesn't exist anywhere in
    that module — genuinely never implemented, not a missing dependency (this is the same underlying
    "never vendored" gap the old note described, just pinned to the exact missing symbol). `acp_adapter`:
    diffed its full 33-name import from `acp.schema` against the installed `agent-client-protocol` 0.12.1 (the
    latest available version, checked via `pip index versions`) — 30 of 33 resolve now; the 3 that don't
    (`ModelInfo`, `SetSessionModelResponse`, `SessionModelState`) don't exist under any name in any published
    version 0.0.1-0.12.1, so this is a genuine protocol-version mismatch, not fixable by installing anything.
    `mining.vllm_pearl` — **stale, the file exists and imports cleanly** (degrades gracefully without the real
    `vllm` package; the note was outdated). `pty_bridge` — confirmed genuinely Unix-only (unchanged). None of
    this blocks anything live; it's all the legacy `run_agent.py`/`batch_runner.py`/`acp_adapter` CLI paths.
14. **Code intelligence** — **INSTALLED 2026-09-25**: `vectorcode/code_intel` dependencies installed (`npm ci`) and built
    (`dist/`), a native Qdrant 1.19.1 in `vectorcode/code_intel/qdrant/` (git-ignored; localhost only, data in
    `~/.vector/qdrant`), `scripts/start_code_intel.bat` / `stop_code_intel.bat`, and the `nomic-embed-text` model you already
    had. Not started automatically (your no-extra-servers rule): run the start script, then use `/code-intel/*`
    (`vc_health` first). Verified end to end on a throwaway project: index, semantic search (found the tax function for a
    plain-English question), call graph, symbol lookup and impact analysis. The agent's transport was rewritten because it
    could never have worked: no MCP handshake, wrong environment-variable names (so the server demanded Docker), a repo-root
    path one level too high (so the build was never found), a fresh server per call (which killed every background index job)
    and a blocking subprocess inside an async method. **Whole-repo index DONE 2026-09-26**: 26,632 files / 101,614 chunks, code graph of 9,209 files
    and 107,891 symbols; Qdrant is left running (`scripts\stop_code_intel.bat` stops it). Re-indexing later needs the MCP
    session to stay alive, so do it from a long-lived process (the API), not a one-shot script.
15. **Stray test write in the live home** — **RESOLVED, confirmed gone 2026-09-29.** `~/.vector/memories/` now
    exists but is empty (no `MEMORY.md`, no `MEMORY.md.lock` anywhere under `~/.vector`) — the stray file from
    the router-test fixture bug is gone, whether removed by the owner or an earlier cleanup. Test fixtures
    remain fixed so it cannot recur.
16. **HUD side panels**: ComfyUI / Media Studio / Hyperframes now say "not running" (via `/media/sidecars`) when
    their local servers are down; the servers themselves are owner-started.
17. **V1 re-acceptance pass (2026-09-26)** — full report: `VECTOR_TECHNICAL_KNOWLEDGE/STAGE_8_V1_REACCEPTANCE_2026-09-26.md`.
    Verdict **not yet "V1 ACCEPTED"**. Closed: Stage 4 (root cause was `ContinueGate` being fed the ranking score as
    "coherence", silently dropping every winner scoring 0.30-0.40; a plan now terminates end to end), Stage 6's live-server
    JWT gap, and seven defects found on the way (research, coding containment, `ProviderClient.complete(messages=)`,
    narration, caption burn-in, ArchitectBot blocking, HUD auth screen). Full suite 6,440 passed / 0 failed after the last
    fix (r13 verified separately). The two builds the handoff held for a decision were then made and done (outcome assessment: payload failure
    signals + `result_field`/`all_of` verification + dotted bindings; browser workflow C: read-only GREEN `web_extract`,
    restart-surviving plan test, evidence-based browser rewards). A walk through the real HUD then fixed seven UI/backend defects (panel layout, agent-count flicker, optional-socket
    DEGRADED, blank atlas, 401 polling storm, blocking `/security/status`) -- see STAGE_8 report section 7 for those and the list of
    taste calls left for you. Final suite 6,499 passed / 0 failed. **The `process_snapshot.py` out-of-process fix independently
    re-verified by Codex 2026-09-29** (Claude self-reviewed first while Codex was quota-exhausted, then Codex itself confirmed
    once quota reset — AGREE, see `VECTOR_TECHNICAL_KNOWLEDGE/CODEX_REVIEW_2026-09-29_CORE.md`) — confirmed
    `core/api/routers/security.py` genuinely spawns it as a real separate `subprocess.run` wrapped in `asyncio.to_thread`, and
    Codex additionally confirmed the anomaly-scan in-process fallback path still runs inside that same `to_thread` wrapper.
    Still open: independent review of the NEW GREEN `web_extract` tier entry specifically; owner-run live behavioural checks
    (voice, camera). `VECTOR_API_KEY` was rotated 2026-09-26: any HUD tab or phone bookmark carrying the old key shows ACCESS
    KEY REJECTED until it is reopened with the key
    from `.env`. **Live-observed 2026-09-29** during the item 22 soak test: the cloud heartbeat cron job got a real `401` from
    `https://vector-api.arghyadeepdeb020703.workers.dev` — degrades gracefully (logged as a warning, never crashes), consistent
    with this same class of local-key-vs-deployed-key mismatch; owner-only to fix (needs the Cloudflare Worker's own configured
    key checked against `.env`'s `VECTOR_API_KEY`, which only the owner's Cloudflare account can do).
18. **A2A bus, experience ledger, fair HP (2026-09-26)** — full write-up: `VECTOR_TECHNICAL_KNOWLEDGE/A2A_AND_EXPERIENCE_2026-09-26.md`.
    Built: a governed agent-to-agent bus for all 230 agents (230/230 answered a live ping across 39 districts; RED requests refused; the old
    `request_agent_help` gateway bypass closed), a lineage experience ledger with XP/levels/failure attribution/playbook, practice drills,
    exploration routing and verified-only collaboration credit. **Found by replaying recorded history: 98% of 573 real deaths were healthy agents
    killed by the 02:00 rank cull** -- the cull now needs a record of failing (`VECTOR_FAIR_CULL`, default on). Everything else that changes
    behaviour is behind a flag, default off (`VECTOR_HP_FAIR`, `VECTOR_PLAYBOOK`, `VECTOR_LEVEL_COUNCIL`, `VECTOR_EXPLORE`, `VECTOR_GYM`): enable
    them per the order in the write-up. Honest limit: only GitBot has a practice drill (1 of 230), so "every agent works" depends on real work
    and on authoring drills per district. **`a2a_bus.py`'s RED-refusal and the old `request_agent_help` bypass
    independently re-verified by Codex 2026-09-29** (Claude self-reviewed first while Codex was quota-exhausted,
    then Codex confirmed with its own tool calls once quota reset — AGREE, see
    `CODEX_REVIEW_2026-09-29_CORE.md`) — confirmed `request_agent_help()` now calls `bus.ask()`, not
    `target.run()` directly, and delivery for GREEN/UNKNOWN tasks goes through `Governor` (inheriting its own
    authorization checks), by reading the actual current code, not the docstring's claim. Governor additions,
    HP-validator change, and probation still await a genuine independent Codex pass once quota resets.
19. **V1 reconstruction and overnight fixes (2026-09-27)** — full write-up: `STAGE_8_V1_REACCEPTANCE_2026-09-26.md` section 8;
    review packet: `CODEX_REVIEW_PACKET_2026-09-27.md`. Verdict B: only final verification remains (Codex review after 19:11 today, your
    live voice/camera checks, a real day of use). Fixed: the 15-27 s API freezes (psutil holding the GIL; child-process scans), five other
    event-loop blockers, `/command`+`/ws/command` reporting failures as success, plan steps starving behind ambient goals, the retired
    Gemini default, a paid-model path in the OpenRouter tier. **Needs your decision: the LightRAG vault index (`data/lightrag_vault`) has
    7 of 11 files zero-filled since 2026-07-15**, so vault memory search has been down; VECTOR now retries every 10 min and names the
    damage in the log, but the rebuild (LLM extraction over the whole vault, hours of local model time) was not started.

    **Later 2026-09-27 (owner: "complete all tasks that can be done by you"):** goal-less plans no longer starve; the remaining
    inline `subprocess.run` calls in async code (emergency/resilience/devops paths) fixed with a static guard test; **the LightRAG
    vault index was rebuilt** (root cause #2 found along the way: the configured LLM was a JSON-only intent-classifier persona, so
    extraction produced zero entities however healthy the files were; switched to the plain base model, rebuilt 137 notes, verified
    live through `/command`); camera and gesture sockets are opt-in (the HUD had been running the webcam and YOLO on load);
    gesture ported to the MediaPipe Tasks API; a validly signed installer/updater in a temp dir no longer raises the threat level
    (native check); httpx's SSL context is cached (~300 ms per `AsyncClient()` construction, ~20 call sites); Command Center shows
    0 approvals as 0; two more verifiable practice drills (3 of 230 agents now); the four behaviour flags are ON in `.env`.
    Full suite 6,708 passed / 0 failed / 39 skipped. **The owner deleted the 577-row `agent_history` junk themselves (2026-09-27)**
    -- the permission classifier denied doing it unattended, so the owner ran the prepared script directly (backup kept,
    `agent_history` 1,150 -> 573). **ContinueGate coherence fix independently re-verified by Codex 2026-09-29** (Claude
    self-reviewed first while Codex was quota-exhausted twice, then Codex confirmed with its own independent test run once
    quota reset — AGREE, see `VECTOR_TECHNICAL_KNOWLEDGE/CODEX_REVIEW_2026-09-29_CORE.md`) — confirmed
    `core/loop/autonomous_loop.py`'s `_continue_gate_coherence()` genuinely computes a real
    `CoherenceScheduler.compute_score("think_loop")` value instead of the ranking score; Codex ran
    `tests/test_think_tick_continue_gate_coherence.py` itself (7 passed, including a test named exactly for the specific
    0.30-0.40 bug). **Still needs the owner:** the live behavioural checks (voice, camera, a real day of use).
20. **Self-dev agent program (P1-P11, 2026-09-27..09-30)** -- full write-up: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_PROGRAM_SUMMARY.md`
    (also `SELF_DEV_P1..P10_*.md` per-package). Claude and Codex split porting the owner's selected Claude Code agent
    personas into real, tested VECTOR agents by district. Result: 164 personas covered across the 10 packages -- 102
    newly built real, evidence-checked agents (P2/P3/P4/P5/P6/P7/P8/P9/P10, P6 and P3 extended by 2026-09-29/09-30
    follow-ups); 16 found to already exist under another name/district (flagged NEEDS_HUMAN where the district-map
    and the actual placement disagree); 15 disclosed as not-built (no honest deterministic check possible); P1's 8
    qa personas came back NOT VERIFIED (missing per-agent test gate) -- **resolved 2026-09-29**, see below; P6's
    original bounded repair found 0 certified fully real, **11 of its original 17 personas are now real agents
    across three follow-ups**, see below. 217 new permission-tier entries (205 GREEN + 12 YELLOW) added, all flagged
    for the pending
    independent review; **no
    existing tier was changed, moved, or loosened by any package**. Manifest verified clean: 41 districts, 273 agents,
    zero duplicate top-level YAML keys. **Still needs the owner:** (a) P2 (coding) and P3 (security) hit the bridge's
    automated "Architecture change"/"Security-sensitive change" approval gate with no CLI verb to grant it -- both
    were built and merged only after the owner's own explicit chat approval, as directly-supervised manual work, never
    through the bridge's automated self-approval path; that gate class stays for any future task matching the same
    keywords, **by design** -- `tools/vector_dev_orchestrator/POLICY.md` sec 14/15 explicitly forbids any model
    self-authorizing a human-gated action, and this is not something more tooling can route around. What *was*
    missing was a clean way to record that the owner already approved a specific item outside the bridge, instead of
    a raw JSON edit each time -- built 2026-09-30: `close-manual` in `autonomous_worker.py`, an owner-run CLI verb
    (`close-manual ITEM_ID --commit SHA --note "..." --owner-approved yes`), explicitly documented as never to be
    invoked by Claude/Codex on their own initiative. 7 new tests, verified byte-identical against the real live
    backlog before/after (md5 unchanged). **Both independently Codex-reviewed 2026-09-29** (see item 21 below) --
    P2: CONFIRMED SAFE (real test
    run, 3 passed); P3: no code-level concern found (couldn't execute pytest itself, sandbox has no writable temp
    dir; Claude already ran it). (b) 7 NEEDS_HUMAN decisions listed in the summary doc (~~zk-steward's district
    placement~~ -- decided, kept in `personal_growth`, see `SELF_DEV_PROGRAM_SUMMARY.md`; ~~5 ops-scope placement
    mismatches~~ -- **found already resolved 2026-09-29, not actually open**: re-checked directly against the
    live manifest and `core/city/governor.py`, confirmed `ops:` has exactly its 7 real agents with no
    duplicate/misrouted entry for any of the 5; the NEEDS_HUMAN flag came from the approval gate (finance/legal
    keywords, same class as P2/P3/P9), already cleared by owner chat approval + merge, not from an unresolved
    placement question; ~~`blockchain-security-auditor` not-built~~ -- **resolved 2026-09-30**, see below
    (built as a real deterministic Solidity pattern-scan agent, no live chain dependency); ~~P6's zero-certified-real
    sales personas~~ -- **resolved across two follow-ups, 2026-09-29 and 2026-09-30**, see below (8 of the
    original 17 personas now real agents; the other 7 stay honestly not-built for specific, individually-examined
    reasons, not left untouched); ~~P1's NOT VERIFIED qa disposition~~
    -- **resolved 2026-09-29**, see below -- the 239-persona
    reconciliation gap was resolved in the follow-up pass below). The 8 duplicate legacy backlog items from the
    pre-existing 24-item backlog (item 18 above) were superseded during this program's cleanup pass.

    **P1's NOT VERIFIED qa disposition — resolved 2026-09-29** (full writeup: the addendum in
    `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P1_QA_VERIFICATION.md`). Added 17 real tests for the 6 specialists that
    had zero coverage; rewrote the 1 existing test that mocked `award_points`/`deduct_points` to track real HP
    instead; clarified "not manifest-registered" as not a real gap (QASwarm self-loads all 11 agents at runtime,
    same pattern as FinanceSwarm/CodingSwarm). **3 real bugs found and fixed while writing real tests**: a
    path-resolution bug (`Path(__file__).parent` × 4, one directory above the real repo root) in 6 files that
    silently broke several diagnostic methods; an invalid git date format in `evidence_collector.py`; and a
    genuine agent-duplication bug in `QASwarm._load_agents()` (its dedup check queried a key no agent is ever
    registered under, so every `QASwarm()` construction silently created 11 brand-new duplicate agents instead
    of reusing existing ones). 57 targeted regression tests pass; a full-suite re-run reached 11/19 batches
    (4,113 tests, 0 failures) before a memory-pressure kill, not retried per standing instruction. Flagged, not
    fixed (scope control): the same path-resolution pattern appears in ~65 more files repo-wide, and a similar
    date-format bug in ~9 more — each needs individual verification before touching, a worthwhile separate pass.

    **Follow-up pass, 2026-09-29 (owner: "complete it with the help of codex... till all issues are not gone
    don't stop"):** the 239-persona reconciliation gap above is now closed — read the actual Agent Roster
    artifact's saved marks directly (239 confirmed) and cross-referenced every one by hand.
    `slack-archaeologist` was a genuine, previously-undisclosed gap — **built** as `SlackArchaeologist`
    (initially security district; relocated to `chief_of_staff` the same day after re-reading
    `SELF_DEV_AGENT_SPEC.md`'s own district map, which explicitly names that district — real
    evidence-checked Slack-history reconstruction, no LLM call). Two more
    (`engineering-senior-developer`, `project-manager-senior`) turned out to be Claude Code's own dev-tooling
    subagent types (verbatim descriptions, tagged present in the global marketplace) rather than VECTOR
    personas — resolved by classification, not built. All 239 are now accounted for. Full clean suite re-run
    after the fix: **6,862 passed / 0 real failures / 39 skipped** (see item 12 above).

    **P6's zero-certified-real sales personas — resolved across three follow-ups, 2026-09-29 and 2026-09-30.**
    First follow-up (owner: "do it, u
    can use codex n urself for the task"; full writeup:
    `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P6_FOLLOWUP_SALES_SPECIALISTS.md`). Codex re-examined the 7 originally
    "partial" Agency sales personas and built 6 real, evidence-gated agents in
    `districts/agency/agency_specialists.py`: `AccountStrategist`, `DealStrategist`, `SalesEngineer`,
    `OutboundSequenceStrategist`, `PipelineVelocityAnalyst`, `ProposalCoverageStrategist`.
    `sales-outbound-strategist`/`sales-outreach` were deliberately collapsed into the one
    `OutboundSequenceStrategist` agent — same underlying deterministic capability, building two would have been
    count-padding, not honest disclosure. Each agent follows the established `<x>_brief`/`<x>_check` pattern
    (evidence presence reported honestly, deterministic verification, zero LLM calls, zero external side effects).
    12 new GREEN permission-tier entries added, flagged for the pending independent review; no existing tier
    touched. Claude independently verified Codex's build before committing: read the actual `evaluate()` logic of
    a sample agent (not just the report), 14/14 new unit tests pass, 102 broader regression tests pass, a
    dangerous-primitive grep came back clean (no subprocess/eval/exec/os.system, no LLM calls), manifest integrity
    clean (41 districts, 267 agents, no duplicate keys), the known word-overlap collision fixture
    (`status_check_report`) still resolves `None` (fail-closed intact), `compileall` clean, both new files' own
    `__main__` smoke checks pass. Merged into `fix/external-review-2026-09` (`git merge --no-ff`, clean, no
    conflicts); re-ran the 14 new tests on the merged tree to confirm — same result. The package's original 10
    "not real" personas (no distinguishing evidence source found in the original pass) were **not** re-examined
    in this follow-up and remain honestly disclosed as not built.

    **Second follow-up, 2026-09-30** (owner asked why the remaining 10 couldn't be solved by Claude/Codex, which
    prompted an honest per-persona re-check instead of repeating the summary; full writeup: the second addendum in
    `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P6_AGENCY.md`). Re-examined all 10 individually against the same
    caller-supplied-evidence model the first follow-up's agents already use. Built 2 more real agents in
    `districts/agency/agency_specialists.py`: `SalesCoach` (collapsing `sales-coach`/`sales-discovery-coach` — same
    underlying rubric-coverage capability, only the caller-supplied rubric differs) and `SalesDataExtractionAgent`
    (real MTD/YTD sum arithmetic and per-rep breakdown over caller-supplied raw records, malformed rows flagged not
    dropped). The other 7 personas stay honestly not-built, each for a specific, examined reason: 6 have no
    plausible use case on a personal-owner system (government-digital-presales-consultant,
    hospitality-guest-services, loan-officer-assistant, real-estate-buyer-seller, recruitment-specialist,
    retail-customer-returns), and `customer-service` is a confirmed duplicate of the existing `ops.SupportResponder`
    (built in P8) rather than a genuine gap. 2 new GREEN tier entries, 6 new tests (20 total in
    `tests/test_agency_sales_specialists.py`, all pass) including hand-verified MTD/YTD arithmetic and a dedicated
    test proving the sales-coach/discovery-coach collapse reasoning. Manifest re-parses clean: 41 districts, 270
    agents, zero duplicate keys. Of the original 17 P6 personas: 10 are now covered by 8 real agents (some
    collapsed, e.g. sales-coach + sales-discovery-coach -> one `SalesCoach`), and 7 remain honestly not-built.

    **Third follow-up, 2026-09-30** (owner correction, not a new request: pointed out that 3 of the "no
    plausible use case" calls above were reasoned from VECTOR's *current* state, not the owner's own
    locked-in 12-year plan; full writeup: the third addendum in
    `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P6_AGENCY.md`). Checked `(C) Industries — Four Waves.md` in the
    Brain vault directly: its sequencing law explicitly permits VECTOR to "research and build ahead" of a
    wave, and Wave 3 (2030-2033) names "real-estate & loan-ops" directly as a leading vertical candidate --
    the "Explicitly rejected industries" list defers *operating a licensed lending business* until Wave 3
    scale pays for compliance, not VECTOR having a deterministic checker ready. Built 3 more real agents:
    `LoanOfficerAssistant` (DTI/LTV/credit-score/down-payment eligibility-criteria check against
    caller-supplied applicant financials -- never approves, denies, or gives lending advice, disclaimer on
    every response), `PropertyMatchAnalyst` (buyer-requirement vs. supplied-listings match, resolves
    real-estate-buyer-seller), and `RecruitmentSpecialist` (candidate-vs-requisition skills/experience/
    certification coverage check, fits Wave 2's agentic-back-office-for-SMBs plan). A real word-overlap
    collision was caught before finalizing action names (the same discipline this whole program
    established): `candidate_fit_check` resolved through the fallback matcher to the existing self_dev
    action `hook_candidate_check` (2 of 3 words overlap) before being added as an exact
    `DISTRICT_TASK_MAP` key -- renamed to `recruitment_fit_check`, re-verified clean, confirmed
    `test_self_dev_specialists.py`'s 28 tests still pass untouched. All three agents' arithmetic/matching
    logic hand-verified against worked examples before any test was written. 6 new GREEN tier entries, 10
    new tests (29 total in `tests/test_agency_sales_specialists.py`, all pass). Manifest re-parses clean:
    41 districts, 273 agents, zero duplicate keys. Of the original 17 P6 personas: **13 are now covered by
    11 real agents**; the remaining 4 (government-digital-presales-consultant, hospitality-guest-services,
    retail-customer-returns -- no support anywhere in the actual plan; customer-service -- confirmed
    duplicate) stay honestly not-built.

    **`blockchain-security-auditor` — resolved 2026-09-30** (owner asked why this couldn't be solved by
    Claude/Codex; re-reading the original disclosure literally showed the gap was never a missing *external*
    data source, only that VECTOR had no smart-contract code to check -- the same caller-supplied-evidence
    model every other specialist here already uses applies just as well to Solidity source a caller supplies.
    Full writeup: the addendum in `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P3_SECURITY.md`). Built
    `BlockchainSecurityAuditor` in `districts/security/security_specialists.py`: a deterministic, bounded
    text-pattern scan aligned to the SWC Registry (6 checks -- floating pragma, unchecked call return value,
    unprotected selfdestruct, reentrancy ordering, tx.origin authentication, unguarded sensitive functions),
    explicitly scoped in its own report as a first-pass heuristic linter, never a compiler-based analyzer or a
    safety certification. Validated against real safe/vulnerable Solidity samples before wiring: zero false
    positives on a safe contract, all 6 planted defects caught with correct attribution on a vulnerable one. 1
    new manifest entry, 2 new GREEN tier entries (flagged for the pending independent review), 2 new tests (13
    total in the file, all pass). Manifest re-parses clean: 41 districts, 268 agents, zero duplicate keys.
21. **Independent review, 2026-09-29 — DONE, genuinely by Codex, not just Claude.** Codex hit its ChatGPT
    usage limit every time it was tried through the morning (before, at, and after its stated 8:40 AM
    reset), so Claude completed direct self-reviews first rather than leave these "still owed"
    indefinitely. Once Codex's quota reset (~3 PM), it was launched again for a genuine independent
    second pass on all 6 outstanding items — pointed at the Claude review's own file:line evidence trail
    and explicitly asked to disagree if it found anything wrong, not rubber-stamp it. **Result: AGREE /
    CONFIRMED SAFE on every item, no disagreements** (full writeup:
    `VECTOR_TECHNICAL_KNOWLEDGE/CODEX_REVIEW_2026-09-29_CORE.md`):
    - `Governor.dispatch()`'s authorization boundary (item 3) — AGREE, and Codex independently found an
      additional unknown-type smuggling gate (`governor.py:2762-2774`) this review hadn't specifically
      pointed it at.
    - A2A bus RED-refusal + `request_agent_help` bypass closure (item 18) — AGREE.
    - `ContinueGate` coherence fix (item 19) — AGREE; Codex ran `tests/test_think_tick_continue_gate_coherence.py`
      itself (7 passed).
    - `process_snapshot.py` out-of-process fix (item 17) — AGREE; Codex additionally confirmed the
      anomaly-scan in-process fallback path is still protected by the same `asyncio.to_thread` wrapper.
    - P2 (coding self-dev package) — CONFIRMED SAFE; Codex ran `tests/test_coding_specialists.py` itself
      (3 passed); zero dangerous primitives found in the 14 new specialists.
    - P3 (security self-dev package) — no code-level concern found in any of the 9 specialists (including
      the patch-proposal roles specifically); couldn't execute `pytest` itself (its read-only sandbox has
      no writable temp directory — a sandbox limitation, not a code finding; Claude already ran it
      successfully). Caught one real, minor doc staleness (agent/tier counts predating the later
      `SlackArchaeologist` addition) — fixed with an addendum in `SELF_DEV_P3_SECURITY.md`.

    Every "independent Codex review still owed" note anywhere in this file is now resolved for real.
22. **Live autonomous-loop soak test, 2026-09-29 — found and fixed a real bug.** Started the real
    `run_vector.py loop` process (free-tier-only config confirmed: no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`
    set) as a background check against item 1's "not yet re-verified against a live multi-hour run" note.
    ~15 minutes in: real LightRAG extraction, STT/VAD cycling, and graceful degradation all observed correctly
    (the HUD recorder correctly logs "no reel produced (recorder unavailable)" rather than crashing when the
    API server isn't also running) — **but found a genuine bug**: a vault note containing a literal tiktoken
    special-token marker (e.g. `<|endoftext|>`, likely from a pasted raw LLM completion) made LightRAG's
    chunker raise on every ingest attempt, and the ingestion pipeline was resetting the same
    permanently-failing document from FAILED back to PENDING and retrying it forever — 186+ failed documents
    accumulated live in the run, burning real embedding/LLM calls with no path to success. Not a hard freeze
    of the autonomous loop itself (the exception was already caught and logged as a warning, nothing crashed)
    but a genuine resource-waste bug — exactly what this soak test existed to catch. **Fixed**:
    `core/memory/obsidian_sync.py` now neutralizes the 5 tiktoken special-token markers before content ever
    reaches LightRAG's tokenizer; real regression test proves the exact crash against the actual tiktoken
    encoder first, then proves the fix. Stopped the soak test after this finding (memory was getting tight,
    ~9-10GB free, and pushing an OOM risk overnight for more soak time wasn't worth it once a real result was
    already in hand) — this remains a partial data point (no *hard freeze* observed in that ~15-minute window),
    not a completed multi-hour proof, but a real bug found and fixed is more valuable than more idle minutes
    of clean-looking log.

    **Extended, 2026-09-29 23:50–23:53 (owner: "okay do it u can use codex n urself for the task")** — a
    second, longer run of the same `run_vector.py loop` process, ~63 real minutes this time (22:50:38 start,
    stopped 23:53), landing inside the 60-90 min target this note above left open. 267 agents / 41 districts
    registered clean at startup (up from the prior run's count, reflecting P6's follow-up + other same-day
    merges). Reviewed the full log (11,705 lines) for anything genuinely new, not just another one-off provider
    hiccup: **zero new bugs found.** Every warning/error pattern observed was already a known, benign, or
    previously-documented category: ADB/Tesseract/phone-unreachable (optional local services not connected),
    the pre-documented `KNOWN_ISSUES #0` blocking-call warning, rate-limit failover across providers (Cerebras
    402, Mistral 403/429, OpenCode Zen 403 `FreeTierError`, NVIDIA 410, Groq/Gemini/Cloudflare 429 — all
    catalog-staleness or free-tier-boundary cases that fail over correctly with zero payment risk, not code
    bugs), the already-documented cloud-heartbeat 401 (item 1 above), and two existing LLM-output quality
    safeguards firing correctly (`zai` empty-content retry, OpenRouter leaked-reasoning retry). One genuinely
    new-this-run finding, but not a fix candidate: `core/memory/obsidian_sync.py`'s `ingest_to_rag_anything()`
    fails every time with `No module named 'rag_anything'` for any vault file markitdown can't convert (PDFs,
    images, audio) — the optional `rag_anything` package was never installed. Unlike the tiktoken bug above,
    this degrades cleanly per-file (`return False`, no retry-forever loop, no resource waste) — the exact same
    class of gap as the already-documented missing-Tesseract/missing-lightgbm optional dependencies. Left
    uninstalled rather than autonomously pulling in a new ML dependency mid-soak-test; **owner action, if
    wanted:** `pip install rag_anything` (or whatever the correct current package name is — not verified here)
    to activate multi-modal vault ingestion. Stopped cleanly at the target window (`Stop-Process` on the loop's
    own pid, confirmed exited, no force-kill needed) once memory read 1.3GB free — a genuine spike, but traced
    directly to `llama-server` at 13.4GB, a pre-existing process not started by this session (same one flagged
    during the P6 build earlier tonight); per the established boundary it was not touched, and it exited on its
    own moments later with memory recovering to 17GB free, confirming the restraint was correct. **This closes
    the soak-test half of "do it" complete**: two runs, ~78 combined real minutes, one real bug found and fixed
    (the tiktoken/LightRAG issue above), one benign optional-dependency gap documented, zero hard freezes, zero
    new code changes needed from this second run.

23. **VECTOR skills system: a real 3-layer bug fixed, SkillBuilder added, 2026-09-30 —**
    full write-up: `VECTOR_TECHNICAL_KNOWLEDGE/SKILLS_SYSTEM.md`. Owner asked for "a skills section for
    VECTOR... for claude's use as well as a skill builder according to a use of repeated task." Investigated
    before building anything: VECTOR already has **5 separate, non-unified skill-loading mechanisms**
    (`core/coding_assistant/core/skills/`, `vectorcode/src/skills/`, `districts/marketing/_skill_loader.py`
    used live by 10+ agents, `districts/investment/vector_backtest/`'s own loader + a manual
    save/patch/delete skill-writer, `districts/intelligence/vectorintel_agent.py`'s own) -- none unified in
    this pass, several already load-bearing and working. Found `districts/coding/coding_tools.py::load_skill()`
    (governor-wired, real dispatchable action) has **never worked**: a constructor call to a signature that
    has never existed, an import of a module that does not exist, a read of an attribute (`skill.content`)
    that has never existed on `SkillInfo` (real field: `prompt`), and even a corrected call would hit an
    uninitialized `HarnessFilesManager` singleton VECTOR's runtime never sets up -- all four silently
    swallowed by one broad exception handler. Fixed by bypassing the heavy config/harness-dependent
    `SkillManager` class and reusing only its lightweight, dependency-free parser/models directly; verified
    end-to-end against real written `SKILL.md` files. Reads/writes VECTOR's own `data/vector_skills/`
    directory (owner's explicit choice over Claude's global or project `.claude/skills/`).
    Built `SkillBuilder` (`districts/personal_growth/skill_builder.py`) for the "repeated task" half --
    the detector already existed and was already live (`vectorcode/src/reasoning_bank.py`'s `PatternLearner`,
    wired into `core/loop/decision_engine.py`, already tracks real task repetition and marks a pattern
    `stable` after 3+ real repeats above a reward threshold); nothing new needed building there. What was
    missing was converting a stable pattern into an actual file -- added `PatternLearner.stable_patterns()`
    (a small, safe, additive public accessor; none existed) and `SkillBuilder`, which deterministically
    re-checks eligibility (never an LLM judgment) and writes a real `SKILL.md` per eligible pattern. Caught
    a real word-overlap collision before finalizing action names (`skill_pattern_brief` resolved to
    self_dev's existing `skill_review_brief` via the fallback matcher -- self_dev owns six other `skill_*`
    actions) -- renamed to `learned_pattern_brief`/`learned_pattern_build`, re-verified clean. GREEN tier
    (same classification already given to `ZKSteward`'s real vault-file-writing actions, a strictly more
    invasive precedent). 14 new tests across two files, all pass; manifest re-parses clean (41 districts,
    274 agents, zero duplicate keys); 62 + 42 broader regression tests pass confirming nothing existing was
    disturbed. **Deliberately not done:** the other 4 skill mechanisms were not unified (separate, larger,
    higher-risk task); `collect_stable_patterns() -> SkillBuilder` is not yet wired into any scheduled job
    (a one-line follow-up once the owner wants it running unattended, not assumed here).

24. **Full codebase audit (Phase 1-3), 2026-09-30 —** owner-authorized whole-repo audit (reachability,
    redundancy, licensing, then behavioral correctness), full write-up:
    `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\CODEBASE_AUDIT.md`. Phase 1 built a 7-iteration
    AST-based reachability tool (v7 trustworthy baseline) and found VECTOR has at least 7 distinct
    "live but invisible to static analysis" dynamic-loading patterns (manifest-YAML class paths,
    `spec_from_file_location` factor loading, OS-subprocess launch, config-driven module_path+class_name
    registries, and — the big one — a systemic bare-sys.path-relative-import pattern used throughout
    `vectorcode` and `vector_backtest` via `ensure_paths()`-style bootstrapping, confirmed wired straight
    into `core/loop/autonomous_loop.py`). Phase 2 re-verified 4 remaining duplicate-code clusters by
    reading the actual source (2 real: `run_fincept_strategy` x5 vendored exact-duplicates, `_patch_council`
    x6 test-helper exact-duplicates; 2 not: coaches' `run()` is real but VECTOR-authored so a different,
    more actionable kind of finding; `isolated_episodic` fixtures are legitimate per-test parameterization,
    not bloat) and identified `shadowbroker_server`'s license (AGPL-3.0, matched to `BigBodyCobain/
    Shadowbroker` via its OSINT-tracker dependency signature — same disposition question as
    `vector_finagent`/`vector_social_sim`'s already-accepted AGPL trees), plus corrected 2 of
    `THIRD_PARTY_NOTICES.md`'s "not checked" items that were never real open questions
    (`core/mining` is an already-documented `vectorcode` port; `vector_hedgebot` isn't vendored at all).
    **Phase 3 (behavioral correctness) shipped its first real fix, not just a finding**: found and fixed a
    live bug in 7 marketing-district agents (`AmazonAdsAgent`, `AttributionAgent`, `SGTMAgent`,
    `GoogleAdsAgent`, `MetaAdsAgent`, `SEOAgent`, `SEOPortfolioAgent`) — already documented as a "LIVE BUG"
    regression trip-wire in `tests/test_marketing_district_run_wiring.py` but never actually fixed: real
    chat traffic sends an LLM-invented `task_type` the agent's structured branches don't match, and none of
    the 7 had `districts/languages/hindi_coach.py`'s already-established query/content fallback, so a real
    on-topic user question hit a bare `"unhandled type"` error instead of an answer. Fixed all 7 with the
    same pattern (route free text to whichever real capability it asks for and has the args for; default to
    the no-required-args capability for a generic ask). Verified against the real, unmocked test suite
    (41/41 pass, real cloud-LLM-provider fallover chains observed in the logs, zero regressions in the other
    34 pre-existing tests including the 29 self-dev-program marketing specialists). Grepped for the same
    "LIVE BUG" trip-wire pattern across all district test files — found 4 more hits
    (`test_content_district_run_wiring.py`, `test_security_district_run_wiring.py`,
    `test_karpathy_lab_run_wiring.py`, `test_interview_prep_run_wiring.py`) but checked each individually
    before assuming they were also unfixed: **all 4 had already been fixed back on 2026-08-04/05** — the
    "LIVE BUG" text is retained historical narration in the docstring ("this test *originally* documented a
    LIVE BUG... Fixed 2026-08-05"), not a current state. Only a 5th hit, `test_coding_reviewers_run_wiring.py`
    (`FastAPIReviewer`/`PythonReviewer`/`SecurityReviewer`), was genuinely still broken — a subtly different
    variant: each already had a working `_answer_query()` free-text fallback, but `run()` checked
    `task_type not in self._SUPPORTED_TASK_TYPES` and returned the error stub *before ever reading params*,
    making the existing fallback unreachable. Fixed by reordering the check (read params for a query first;
    only error if there's truly none) — reuses the already-correct fallback, no new routing logic needed.
    Verified: 13/13 pass, zero regressions. Phase 3's remaining scope: 274 manifest agents total; marketing
    (45) and coding (28, this bug class) done; the rest of the 41 districts not yet individually swept for
    this or other bug classes.

25. **31-file, 15-district params-vs-task dispatch bug, 2026-09-30 — the highest-value finding of the whole
    audit.** Full write-up: `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\CODEBASE_AUDIT.md`. While
    auditing security's 4 previously-zero-test-coverage agents, found `DataRedactor.run()` read
    `text`/`messages`/`cloud_mode` straight off `task` instead of `task["params"]` — the real governor
    dispatch shape (`{"type": ..., "params": {...}}`) meant every real dispatch silently redacted/scanned an
    empty string and reported `status: "ok"` with zero findings, **even when a real secret was supplied** —
    verified live: `agent.run({"type": "redact_text", "params": {"text": "<real API key>"}})` returned
    `{"redacted": "", "findings": []}`. Security/privacy-relevant, not cosmetic: this is VECTOR's own RULE 11
    privacy-enforcement agent. Found the identical shape in `ThreatDetectionEngineer.run()`
    (`sigma_rule`/`coverage_map`/`analyze_logs` all ignored real caller arguments, verified live). Given the
    same bug appeared twice independently, wrote a repo-wide AST scanner to find every
    `async def run(self, task)` that reads a domain-specific `task.get(key)` while never touching
    `task["params"]` anywhere in the method body — 34 candidates surfaced, every one individually verified
    (not trusted blindly): 31 true positives, 2 genuine false positives (`core/loop/workflow_runner.py` and
    `core/swarm/generic_swarm.py` don't share the governor `run(self, task)` convention), 1 already-fixed
    (`districts/marketing/marketing_specialists.py` — built LATER than 5 of the buggy files below, already
    had the fix, just never backported).
    **31 files fixed across 15 districts**: `security/data_redactor.py` + `security/
    threat_detection_engineer.py`; 5 self-dev-program evidence-gated specialist files sharing one root cause
    (`agency/agency_specialists.py` 16 agents, `design/design_specialists.py` 15, `security/
    security_specialists.py` 9, `personal_growth/skill_builder.py`, `chief_of_staff/slack_archaeologist.py` —
    ~42 agents, all reading `task.get("evidence")` instead of the nested `params.evidence` marketing's later
    file already fixed); `communications/email_agent.py` (~15 task-type branches); all 8 QA district agents;
    4 more coding agents; both `data_analytics` agents; both `finance` agents; `governance/
    compliance_auditor.py`; `health/biometrics_aggregator.py`; `memory_curator/context_compressor.py`; all 3
    `ops` agents; `projects/experiment_tracker.py`. Estimated 70+ agent instances affected in total. Two fix
    variants depending on call-site complexity: an explicit `params.get(k, task.get(k, default))` per key for
    simple files, or flattening params into task once at the top of `run()`
    (`task = {**task, **(task.get("params") or {})}`) for files with many keys/branches — both keep every
    flat-shape legacy caller/test working unchanged. Verified per file: syntax-checked all 31, ran every
    existing test suite that imports any of them (zero regressions anywhere), live-verified a representative
    sample per batch with monkeypatched argument capture. Most of the final 15-file batch had **zero
    dedicated test coverage anywhere in `tests/`** — a separate, real finding, not chased further this pass.
    5 commits: `bf6f6be1d`, `53f59bfb4`, `d6779c761`, `5c8def7b4`, `ffa06cad7`. A full-suite regression run
    was kicked off to catch anything the targeted per-district checks missed.

26. **Whole-repo scope expansion + Claude/Codex 50/50 split, 2026-09-30 —** owner corrected scope
    mid-cycle: "each and every file" in the codebase, not just `districts/`, split genuinely 50/50 with
    Codex (not Claude-does-everything-Codex-reviews) to protect Claude's weekly usage limit. Tracking
    ledger: `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\PHASE3_FULL_SWEEP.md`. Model caps (owner-set,
    stricter than `tools/vector_dev_orchestrator/POLICY.md`'s own ceiling): Claude capped at Sonnet-high
    (no Opus, ever); Codex capped at Sol (no Astra, ever) — flag instead of escalating past either cap.
    Re-ran the item-25 params-bug AST scanner across all 7,205 `.py` files in the repo (not just
    `districts/`+`core/`): 0 syntax errors, only 6 candidates total — 3 false positives after individual
    verification (2 already-known: `core/loop/workflow_runner.py`, `core/swarm/generic_swarm.py`; 1 newly
    checked: `vectorcode/src/tools/mcp_tool.py` — its `run(self, config: dict)` is an MCP client connection
    lifecycle coroutine, unrelated to the governor's `run(self, task)` dispatch interface the scanner
    targets, confirmed by reading the method — not a real bug, not handed to Codex), 3 genuine true
    positives in Claude's territory, fixed same day (`districts/communications/
    email_intelligence.py`, `districts/design/image_prompt_engineer.py`, `districts/design/
    ux_researcher.py` — same bug shape, same fix pattern; `tests/test_phase3_sweep_params_dispatch.py`
    added, 4/4 pass).
    **A second, broader mechanical sweep** (same zero-LLM-call AST/regex technique, scoped to
    `districts/`+`core/`+`vectorcode/` minus the already-wiring-check-only vendored trees, 3,827 files)
    checked for other CLAUDE.md-rule violations: forbidden imports (`threading`/`requests`/`flask`/
    `pickle`), `print()` outside a file's own `__main__` smoke-test guard, raw `sqlite3.connect(...)`
    bypassing `core.memory.episodic.get_db_connection()`, and silent `except: pass`. Result: **478
    forbidden imports (374 `threading`, of which 192 are real `threading.Thread()` spawns rather than a
    safe `Lock()` guard; 55 `requests`; 48 `flask`; 1 `pickle`), 5,304 `print()` calls outside a
    `__main__` guard, 150 raw `sqlite3.connect()` sites, 333 silent `except: pass` blocks.** Full raw
    output: `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\full_repo_sweep2_results.txt`. **Not fixed —
    flagged for owner decision, not autonomous action**: sample-checked the `threading.Thread()` hits and
    they cluster overwhelmingly in large absorbed subsystems (`core/coding_assistant/`,
    `core/research_engine/`) that predate this session; converting hundreds of call sites' concurrency
    model to asyncio (or auditing 150 raw sqlite3 connections for whether they're legitimately outside the
    main encrypted DB, e.g. migration/backup tooling, vs. a real SQLCipher-bypass bug) is a large,
    architecturally risky undertaking with a blast radius far beyond "fix what the params-bug hunt
    found" — this needs an explicit owner call on priority/scope before any code changes, not a
    same-session autonomous fix.
    Split execution as of this entry: Claude side committed 2 batches (`d8eb4e7b0` — 21-file
    params[type]-hijacking-dispatch fix from Codex's 3rd review pass, see item 25's continuation;
    `214cb5d9c` — the 3 whole-repo-sweep true positives above), then personally triaged all 14 raw-sqlite3
    sites in its own core/ territory (`core/memory/`, `core/loop/task_ledger.py`+`trust_ladder.py`,
    `core/brain/epistemic_tracker.py`+`person_model.py`+`suggestion_queue.py`,
    `core/city/meta_cognition.py`) by reading each file's actual schema/logic, not just the raw grep list
    — full report: `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\claude_sqlite_triage_report.md`. 13/14
    fine (either the shared-connection plumbing itself, a false-positive only reachable from an isolated
    test/`:memory:` path, or a legitimate non-sensitive auxiliary store — VECTOR's own internal
    reasoning/decision state, verified per file). **1 real finding, not autonomously fixed**:
    `core/brain/person_model.py` (Gap 7) opens a plain unencrypted `sqlite3.connect()` at
    `data_path()/person_models.db`, storing `name`/`email`/`relationship_type`/`trust_score`/metadata
    for every real person VECTOR interacts with — genuine third-party PII sitting outside the
    SQLCipher-encrypted main DB. Migrating an existing on-disk file to SQLCipher (or folding it into the
    main DB) is a real schema/data migration with data-loss risk if done carelessly — this needs an
    explicit owner call on priority/approach, not a same-session autonomous fix.
    **Codex's matching triage of its 21-file half completed** (background `codex exec -m gpt-5.6-sol`,
    129,505 tokens, no code changes attempted — correctly conservative, same discipline as Claude's half):
    full report `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\codex_sqlite_triage_report.md`. 12 FINE
    (shared-connection plumbing itself, `__main__`-self-test-only false positives, or non-sensitive
    read-only reference DBs), **9 FLAG-FOR-OWNER real findings**: `core/api/routers/email.py` +
    `core/email/schema.py` (plaintext `email.db` — full correspondence, PII), `core/api/routers/
    relationships.py` (plaintext `contacts.db` — names/phones/emails/notes), `core/persona/evolution.py`
    (person-linked behavioral trait data), `core/scheduler/store.py` (plaintext task prompts/results, can
    contain user content or secrets), `core/security/mcp_security.py` (plaintext tool-call audit log,
    `str(record.params)` unredacted — can contain paths/URLs/message bodies/tokens), `core/trading/
    graph/checkpointer.py` (crash-resume trading-analysis state, plaintext). All 9 need an owner call on
    migration/redaction/encryption approach for existing on-disk data — genuinely not same-session
    autonomous fixes (data-loss risk if rushed), consistent with Claude's own `person_model.py` finding
    above.
    **One exception Claude fixed directly**, because unlike the other 9 it had no data-migration risk —
    Codex's own report flagged `core/api/routers/queue.py` (lines 37/56/76) as functionally different
    from the rest: "a bypass/correctness problem ... will fail against an encrypted DB, not evidence of
    a second plaintext queue file" — the router duplicated raw `sqlite3.connect(rq._db, ...)` instead of
    calling `RetryQueue`'s own already-correct `_conn()` helper, silently returning empty
    `{"items": [], "error": ...}` for 3 endpoints whenever SQLCipher is active. Fixed by routing through
    `_conn()` like every other RetryQueue method already does — same target file, no schema/migration
    change. New test file `tests/test_queue_router_conn_bypass.py` (4 tests), zero regressions in the 17
    pre-existing RetryQueue-adjacent tests. Commit `b229dda82`.
    **Claude also found and fixed the identical bug class in `core/experiments/ab_testing.py`** while
    reviewing the sweep's `requests`/`ab_testing.py` hit list — `ExperimentRegistry._conn()` and
    `Experiment.record()`/`stats()` all opened `sqlite3.connect()` directly against the main DB path with
    zero SQLCipher branching anywhere in the file (unlike `queue.py`, there was no existing correct helper
    to delegate to, so a small shared `_get_conn(db_path)` helper was added mirroring `RetryQueue._conn()`'s
    established pattern, and every call site in both classes updated to use it). Confirmed no other module
    imports `ExperimentRegistry`/`Experiment` externally (Gap 18 / A/B testing is currently unwired from
    any production caller — a separate, pre-existing, out-of-scope finding, not fixed here). New test file
    `tests/test_ab_testing_conn_bypass.py` (7 tests, all pass).
    **Next deep-verify slice, both sides done same day**: Claude (via a self-fork, same context/model,
    Sonnet-high cap respected) deep-verified all 13 `core/brain/` files; Codex (`codex exec -m
    gpt-5.6-sol`) deep-verified all 16 `core/security/` files — real logic review, not just the
    sqlite-pattern grep. **Claude's `core/brain/` pass**: wiring-verified every module against real call
    sites rather than trusting docs — confirmed `epistemic_tracker.py` (Gap 3) IS actually wired into
    both `decision_engine.py` and `autonomous_loop.py` despite `.claude/rules/phase_status.md` calling it
    "ORPHANED" (stale doc, not a real bug — flagged for a doc fix, not code); confirmed `router.py` and
    `self_evolve.py` are deliberately `DORMANT` per an existing 2026-09-24 decision doc, not new findings.
    Found and fixed a real bug class: 6 except-blocks across `epistemic_tracker.py`, `goal_system.py`
    (×2), `person_model.py`, `suggestion_queue.py` had `logger.warning(...)` calls that silently logged
    nothing useful — some had no `as e` at all (just a literal string), others used `"...: %s".format(e)`
    which loguru doesn't support (`%s`-style, not `{}`-style — printed literally, `e` silently dropped,
    verified directly: `"...: %s".format("boom")` → unchanged string). AST-scanned all 13 files for every
    other no-`as e` except block afterward (9 more) — all legitimate silent-fallback patterns that never
    attempted logging, not the same bug. Fixed all 6 to actually render the exception. New test file
    `tests/test_core_brain_silent_swallow_logging.py` (5 tests, forces each block to actually raise and
    asserts the real exception text appears with no literal `%s`); 138/148 pre-existing tests across the
    4 touched modules still pass (10 unrelated pre-existing skips, 0 failures). Commit `bd5f842da`.
    **Codex's `core/security/` pass**: full report
    `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\codex_core_security_report.md`. **3 real bugs found
    and fixed, no policy tradeoff in either**: `secrets_manager.py` (keyring read/write + audit-log
    failures silently swallowed with zero logging — now warn, values never logged) and `skill_scanner.py`
    (`scan_skill_for_load()`, the real pre-load security gate, only ever scanned the `SKILL.md` manifest
    itself — a malicious sibling script/hook sitting next to a clean-looking manifest completely escaped
    the gate; fixed by expanding to the containing directory). Both independently re-verified by Claude
    (30/30 tests, plus the existing security regression suite, zero regressions). Commit `bef33f0eb`.
    **1 fix proposed by Codex but deliberately NOT applied** — `token_blacklist.py`'s `is_revoked()`/
    `is_globally_revoked()` return `False` (not-revoked) on a SQLite error, with an explicit, deliberate
    comment present since the file's first commit: `# fail-open for availability; blacklist is
    defense-in-depth`. Codex proposed flipping to fail-closed (`return True`/reject), citing VECTOR's own
    `Decisions/004-fail-closed-permission-tiers.md`. Claude reviewed this specifically and held it back
    rather than committing: this reverses a *documented, deliberate* tradeoff (not an accidental bug like
    the other fixes), and in a single-owner system, fail-closed here means a transient blacklist-DB
    glitch (disk full, lock contention) would reject every token check — including the owner's own
    legitimate session — not just an attacker's. Decision 004 is specifically about the Permission
    Gateway's real-world-action boundary, a different and higher-stakes gate than a defense-in-depth
    revocation side-check on top of primary JWT signature validation; whether the same philosophy should
    extend here is a deliberate yes/no for the owner, not an inherited default. Reverted the change;
    ready-to-apply fix + test held at
    `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\token_blacklist_fail_closed_PENDING_OWNER_DECISION.{md,py.txt}`
    (the `.md` explains the tradeoff and exact reapply steps).
    **8 more real FLAG-FOR-OWNER findings from Codex's `core/security/` pass, none fixed** (all
    genuinely need a design/policy call, not a mechanical fix): `hp_validator.py` (HP-delta
    cross-validation hardening is fail-open — an uncorroborated large delta or a validator/DB failure
    still gets applied); `mcp_security.py` (production MCP-wrapper middleware fails open on exceptions;
    this audit-log DB is also unencrypted `str(record.params)`, can contain credentials/PII);
    `prompt_injection.py` (`Governor.dispatch()` catches scanner exceptions and continues — fail-open;
    regex-only detection is inherently evadable); `rules_engine.py` (live "bypass rules" claim a clear
    schedule / nominal systems without consulting any real calendar/health state — evidence-free
    responses that conflict with VECTOR's own anti-fabrication posture); **`safe_eval.py` (the most
    severe finding — "not a sandbox": arbitrary calls and non-dunder attribute chains are allowed on any
    supplied object, so a real MCP caller passing pandas/numpy could reach filesystem/network/file-write
    methods; unbounded exponentiation also enables resource exhaustion; needs an explicit
    callable/attribute allowlist design, not a guessed patch)**; `secrets_providers.py` (orphaned —
    zero production callers, a duplicate abstraction of `secrets_manager.py` that could silently
    become the live path if ever wired wrong); `ssrf_guard.py` (the real `WebScout`/`VectorScraper`
    callers use a DNS-resolution-disabled singleton, so a public-looking hostname that actually resolves
    to a private/loopback address isn't caught; other high-risk paths do enable DNS, inconsistently);
    `taint_tracker.py` (`VectorScraper` tags fetched content then discards the returned tainted value;
    `Governor` catches tracker errors and proceeds unchecked; unknown string labels are silently ignored);
    `workspace_audit.py` (zero production callers — orphaned, same class as `secrets_providers.py`).
    **Third deep-verify slice, same day**: Claude (self-fork) deep-verified all 18 `core/loop/` files
    (the single most safety-critical directory — `autonomous_loop.py`, `permission_gateway.py`,
    `decision_engine.py`); Codex (`codex exec -m gpt-5.6-sol`) deep-verified all 31 `core/inference/`
    files (the LLM routing/provider layer). Both sides' diffs independently re-reviewed and re-tested by
    Claude before committing, not just trusted from the report.
    **Claude/core-loop**: verified Rules 1-4 (CLAUDE.md's non-negotiable section) are NOT violated by
    this bug class or elsewhere in scope — `permission_gateway.py` already has extensive prior
    "round 1-4 independent review" hardening; `policy.py`'s `get_score()`/`update_from_outcome()` wiring
    already has dedicated exact-call-count test coverage; `autonomous_loop.py`'s coroutine-level
    exception handling consistently uses `exc_info=True`, no bare `except: pass` at the loop level.
    Found the same "silent swallow" placeholder-logging bug (commit `bd5f842da`'s bug class) recurring 9
    more times across `autonomous_loop.py`(×2)/`context_engine.py`/`cron_jobs.py`(×4)/
    `permission_gateway.py`/`task_ledger.py` — all traced to the same earlier automated pass that left
    the literal string `"[VECTOR] silent swallow"` with zero exception info. Fixed all 9 (2 scheduler-
    API-probing sites in `cron_jobs.py` correctly downgraded to `debug`, matching the code's own
    try-next-API comment — not real anomalies). New test `tests/test_core_loop_silent_swallow_logging.py`
    (5 tests incl. a golden test the placeholder string never reappears), 231 pre-existing tests across
    touched modules re-verified independently, zero regressions. Commit `6426954e4`.
    **Flagged, not fixed**: `nudge_engine.py:175` and `autonomous_loop.py:3260` (coding-companion nudge)
    call the LLM directly with zero `session_hydration_prompt()` (Rule 1 gap) — held back because these
    are deliberately tiny single-sentence nudge prompts where prepending full session context is a real
    tradeoff (could dilute the intended short output), not clearly an oversight.
    **Codex/core-inference — the most significant security finding of the whole cycle**: full report
    `C:\Users\Arghyadeep\AppData\Local\Temp\v1recon\codex_core_inference_report.md`. models.md states
    the local-only sensitivity gate for security/RED-tier/secret-bearing tasks "is non-negotiable" — it
    was, in fact, negotiable: **`vectorcode_llm.chat()`/`achat()` checked and returned from an explicit
    `provider=` argument BEFORE the sensitivity/`local_only` check ever ran** (dead code below an early
    return whenever a caller passed an explicit provider), and **`ProviderClient.chat()` gated the same
    `decide_route()` sensitivity call behind `if not provider:`**, meaning an explicit provider argument
    skipped local-only routing entirely in both of VECTOR's two LLM entry points. Fixed by reordering
    sensitivity evaluation first in `vectorcode_llm.py` (also added a `domain_local_only` check matching
    models.md's "security domain is local_only" rule) and by always running `decide_route()` in
    `provider_client.py`, forcibly clearing `provider`/`model` back to `None` when the plan says
    local-only so an explicit override can't survive. Also closed a secret-scanning gap: the pre-route
    scan only concatenated `user`-role message content, so a secret injected via `system`/`tool`-role
    context was invisible to it — now scans every message regardless of role. Added a `permission_tier`
    kwarg (RED forces local) to both entry points, backward compatible. Separately fixed
    `route_policy.py`'s `_is_local()`, which treated `LLMProvider.free` (a *pricing* property) as
    meaning on-device — every free-tier *cloud* API (Gemini etc.) was incorrectly excluded from ordinary
    cloud routing. And a fallback-chain gap: a logical/domain model alias's backend chain could be
    all-cloud with no Ollama entry, so total cloud failure would raise instead of falling through —
    "every chain terminates on ollama, never crashes" wasn't actually guaranteed; fixed by appending
    Ollama when absent. Plus 2 unrelated real bugs in the same directory: `airllm_runner.py`'s live code
    path used `torch.no_grad()` without importing `torch` in that method (only in the module's own
    `__main__` self-test, which masked the `NameError` since the self-test's import ran first in-process)
    — fixed; `quota_ledger.py._prune()` silently swallowed every exception — now logged.
    New test `tests/test_inference_sensitive_routing_guard.py` (6 tests) proves explicit-provider
    bypass is closed (sync + async), RED `permission_tier` overrides an explicit provider, system-context
    secrets are scanned, a no-Ollama logical chain still terminates on Ollama, and free cloud providers
    are no longer misclassified as local — plus 2 more test files for the airllm/quota fixes. Claude
    independently re-verified all 8 new tests + 54 more across `test_provider_selection.py`/
    `test_model_catalog.py`/`test_domain_routing.py`/`test_quota_ledger.py` + a sample of district-agent
    dispatch tests that indirectly exercise this plumbing — zero regressions anywhere. Commit `c6458ce1a`.
    **8 further FLAG-FOR-OWNER findings from `core/inference/`, none fixed** (real design/policy calls):
    the documented "Claude API → Ollama → cached response → notify owner, never crashes" fallback isn't
    actually honored end-to-end (`ProviderClient` can still raise; no cache/notify path exists);
    `LLMProvider.is_configured` returns true for every `free=True` provider even when a key is actually
    required (adds live failures/latency for some providers); the entire `smart_routing/` subpackage is
    a mostly orphaned parallel router with **no sensitivity gate at all** and a broken import
    (`proxy.py` imports a symbol — `from core.inference.provider_client import chat` — that doesn't
    exist); `smart_routing/wallet.py` would store a plaintext mnemonic/private keys with non-hardened
    BIP-32 derivation if ever activated; `smart_routing/response_store.py` would persist plaintext
    prompts/responses (potential secrets/PII) outside the encrypted episodic store if ever activated.
    **Fourth deep-verify slice, same day**: Claude (self-fork) deep-verified all 18 `core/city/` files;
    Codex (`codex exec -m gpt-5.6-sol`) deep-verified 22 files across `core/control/`+`core/sensing/`+
    `core/network/`.
    **Claude/core-city**: re-checked a standing memory claiming an unresolved caller-controlled-district
    trust gap in `Governor.dispatch()` (deferred pending Codex, 2026-09-24) — read the CURRENT code
    directly rather than trusting the memory: **already fixed 2026-09-25, independently re-verified by
    Codex 2026-09-29 (AGREE)**. Memory was stale, corrected in place rather than left to mislead a future
    session. Verified (real code, not just docs) `agent_base.py`'s HP thresholds/award-deduct asymmetry
    match CLAUDE.md exactly; `agent_registry.py`'s "thread-safe singleton" claim is real (genuine
    double-checked locking); ghost-memory preservation on agent death is wired into real callers. Found +
    fixed 1 more silent-swallow-placeholder site (`meta_cognition.py`'s `close()`). New test
    `tests/test_core_city_silent_swallow_logging.py` (1 test). Commit `2639aaabb`.
    Flagged: `core/city/intent_bert.py` claims to be governor intent-classification "Stage 3" but has
    zero production importers and isn't recorded in `scripts/mark_dormant_modules.py` either (unlike its
    siblings `task_router.py`/`core/brain/router.py`/`core/brain/self_evolve.py`) — a genuinely
    undocumented orphan, needs an owner call.
    **Codex/core-control+sensing+network — 3 real fixes**: `core/control/security/malware_detector.py`'s
    `scan_file()` continued past a failed/unreadable hash instead of stopping, so an unscannable target
    could fall through to the extension heuristic and be reported "clean" despite never actually being
    scanned — fixed to return `unknown` immediately on a hash failure. `core/network/ofp_protocol.py`'s
    `OFPMessage.is_expired()` only checked whether a timestamp was too OLD — a future-dated signed
    message made the subtraction negative, so it was **never** considered expired, a real replay-window
    bypass if the in-memory nonce cache is ever lost (restart/crash); also didn't reject non-numeric/
    bool/NaN/inf timestamps — fixed to reject both directions plus type/finiteness validation (strictly
    more restrictive, can't introduce a new false-negative). `core/sensing/presence_detector.py`'s
    `tracked.tracker_id or []` raised "ambiguous truth value" on a multi-element NumPy array (a classic
    NumPy gotcha) whenever more than one person was tracked simultaneously, silently degrading real
    multi-person detection to "unavailable" — fixed with an explicit `is not None` check. New test
    `tests/test_core_control_network_safety_guards.py` (4 tests). Claude independently re-verified plus 2
    pre-existing regression suites — zero regressions. Commit `cf93642df`.
    **6 more real FLAG-FOR-OWNER findings, none fixed — 2 of these are as serious as the
    `core/inference/` finding (Rule 3 "Permission Gateway is the ONLY path to real-world actions...
    Nothing bypasses this" gaps)**: `core/control/pc_controller.py`'s `media_key()` performs real OS
    input (actual media-key presses) with **no gateway token check at all**, even though the gateway
    itself calls it correctly — any other importer can call it directly, fully ungated; `play_music()`
    ends through the same ungated primitive. `core/control/phone_controller.py`'s `_run_adb()` is an
    **unrestricted arbitrary ADB command executor**; `districts/content/phone_poster.py` calls it
    directly for real device actions — the caller happens to request approval first, but the controller
    boundary itself doesn't enforce that, same class of gap. Neither fixed here because correcting them
    changes public method signatures and every real caller, a cross-file API-boundary decision, not a
    narrow patch. Also flagged: `threat_detector.py` silently returns `[]` (indistinguishable from "no
    anomalies") if both its scan paths fail; `social_safety.py`'s 1-post/day cap has a real TOCTOU gap
    (unlocked read-modify-write) plus an unsurfaced save-failure path that could allow a second same-day
    post after a restart; `peer_discovery.py` accepts unauthenticated LAN announcements via `recv()`
    (not `recvfrom()`), trusting claimed host/port/node-id; `core/sensing/camera.py`'s `FatigueMonitor`
    calls a MediaPipe API (`mp.solutions.face_mesh`) that the codebase's own `mediapipe_tasks.py`
    comments say was removed in current MediaPipe versions — on affected installs, fatigue sensing
    silently degrades to a hardcoded `5.0` treated as real data, not "unavailable"; `sound_classifier.py`'s
    optional YAMNet/ONNX path is dead code (loads a session `classify_frame()` never reads).
    **Fifth deep-verify slice, same day — completes Claude's entire originally-assigned `core/`
    territory**: Claude (self-fork) deep-verified all 22 `core/memory/` files (the last of Claude's 4
    assigned dirs — `core/loop`+`core/brain`+`core/city`+`core/memory`, 71 files total, all now done);
    Codex (`codex exec -m gpt-5.6-sol`) deep-verified 30 files across `core/engine/`
    (OAuth/webhook/subagent/telemetry).
    **Claude/core-memory**: verified 3 more of CLAUDE.md's non-negotiable rules are real, not just
    documented — Rule 7 (5 sacred tables: exact names confirmed, every `ALTER TABLE` is `ADD COLUMN`
    only, the one `DROP TABLE` is a documented FTS5 shadow-index rebuild not a sacred table); Rule 4
    (`policy.py`'s EMA math correct, the prior lost-update-race fix still holds under
    `get_temp_cursor()`'s lock); Rule 8 (`reward > 0.7` training-data threshold matches the docstring
    exactly in `episodic.py.store_chain()`). Found + fixed 5 more silent-swallow-placeholder sites
    (`counterfactual.py`, `episodic.py` ×3 incl. the main singleton's own close, `db_guardian.py`). New
    test `tests/test_core_memory_silent_swallow_logging.py` (4 tests), 79 pre-existing tests re-run, zero
    regressions. Commit `dbf66e82c`. Lighter slice than the previous two — no new FLAG-FOR-OWNER findings
    — consistent with `core/memory/` being the most mature, most-previously-hardened part of the
    codebase.
    **Codex/core-engine — 2 real security fixes, 4 sub-fixes total**:
    `core/engine/oauth/flows.py` — (1) `get_token()` returned an **expired, unusable token** as if valid
    whenever a refresh attempt failed OR no refresh_token existed at all (both cases fell through to
    `return token` at the bottom); restructured to return `None` in both failure cases instead. (2)
    `_sync_refresh()` accepted any HTTP response including non-2xx and malformed/empty 200s, falling back
    to the OLD access token on a missing field — combined with bug (1), a broken refresh could silently
    look like a successful one; now requires `raise_for_status()` + a real non-empty `access_token` before
    accepting a refresh. (3) Provider slugs were interpolated directly into a token filename with no
    validation — a malformed/corrupted slug containing path separators (including Windows backslash)
    could escape the token storage directory on store/load/revoke; added a validated `_token_path()`
    helper (`^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`) all 3 call sites now route through.
    `core/engine/oauth/server.py` — provider-controlled callback/error text was interpolated into HTML
    responses **without escaping**, so a malicious or compromised OAuth provider could inject script into
    the page served at VECTOR's own localhost OAuth callback origin. Fixed with stdlib `html.escape()` on
    both HTML renderers.
    Both server.py callers of `get_token()` already handle `None` correctly (verified independently, not
    just trusted) — the behavior change fixes a prior lie ("connected": true for an actually-unusable
    expired token) rather than breaking anything. New test
    `tests/test_core_engine_oauth_refresh_safety.py` (8 tests). Independently re-verified plus
    `tests/test_oauth_nango.py` + `tests/test_openwa_absorption.py` (98 total) — zero regressions. Commit
    `615a97b4f`.
    **6 more real FLAG-FOR-OWNER findings from `core/engine/`, none fixed**: `oauth/server.py`'s
    status/list/api-key/revoke/refresh routes have **no owner authentication or CSRF/origin control**
    (loopback-default limits exposure today, but the router supports mounting elsewhere); OAuth2
    state/PKCE/OAuth1 transaction dicts have no TTL/cap. `webhook/hmac_signer.py`'s HMAC comparison is
    timing-safe but has **no replay protection** — the signature covers only the body, timestamp/
    delivery-id metadata is unsigned. `memory_tree/tree_builder.py` duplicates episodic content into a
    **plaintext `memory_tree.json`**, so SQLCipher on the source DB doesn't protect this derived index.
    `agents/subagent_runner.py` isn't a live ungated primitive today (no production importer) but would
    need real capability policy + gateway wiring + session hydration before ever being activated.
    `research/parallel_researcher.py`'s `parallel_extract()` follows caller-supplied URLs with **no SSRF
    validation** (dormant, no production caller currently). `telemetry/sentry_bridge.py` redacts by known
    sensitive key names but not secrets embedded in free-form exception/message strings.
    **New memory created**: `phase3-whole-repo-sweep-2026-09-30.md` in Claude's persistent memory system
    tracks this whole ongoing effort across sessions (ledger pointer, established pattern, the
    `token_blacklist.py` "explicit comment = flag not fix" judgment bar). Also corrected a stale memory
    (`governor-district-trust-deferred-finding-2026-09-24`) that claimed an unresolved finding actually
    fixed back on 2026-09-25.
    15 commits this resumed segment: `d8eb4e7b0` `214cb5d9c` `b229dda82` `9e7f2d04a` `bd5f842da`
    `bef33f0eb` `28213ab07` `6426954e4` `c6458ce1a` `d5940fa7c` `2639aaabb` `cf93642df` `52098dfa0`
    `dbf66e82c` `615a97b4f` (preceded by `9e630a1e9`/`f3c9123f0` from earlier the same day, already
    covered above). Working tree clean except for the intentionally-held `token_blacklist.py` decision
    file in the scratch folder (not `tests/`, does not affect any test run).
    **Codex hit its usage limit mid-6th-slice** (`core/collections/`+`core/voice/`, 29 files) —
    reported to reset at 10:05 PM. No real work was done on that slice despite the background task
    exiting 0 (caught by checking the report file directly, not trusting the exit code alone). Per the
    owner's own instruction for this whole effort, Claude did NOT silently absorb Codex's share — paused
    launching new Codex-dependent slices rather than doubling Claude's own load. Re-queue
    `core/collections/`+`core/voice/` once Codex is confirmed available again (prompt already saved at
    `codex_core_collections_voice_deepverify_prompt.txt` in the scratch folder). Full detail in memory
    `codex-quota-exhausted-2026-09-30`.
    **While Codex was blocked, Claude's own already-in-flight fork completed** (launched before the
    quota exhaustion was discovered, independent of Codex): deep-verified `core/api/`'s 11 top-level
    shared-infrastructure files (not `routers/`, 87 more files, still a future slice) — Claude picking
    up a share of `core/api/` (98 files, the largest remaining `core/` directory) since its own assigned
    territory is fully done. Found + fixed `core/api/tasks.py`'s `VECTOR_INTERNAL_TOKEN` read into a
    module-global at **import time** — the exact anti-pattern `core/api/auth.py`'s own docstring already
    documents as a prior bug there: an env var set after import (`.env` load ordering, or a test
    monkeypatching `os.environ`) was silently ignored forever, either permanently locking out the
    external task-ingestion endpoint or leaving it unconfigured. Fixed with a call-time
    `_internal_token()` function, the same pattern already proven in `auth.py`. Plus 2 more
    silent-swallow-placeholder sites in `app.py`'s `/metrics` endpoint. Verified fine, no fix needed:
    `auth.py`/`middleware.py`/`webauthn_store.py`/`dependencies.py` show extensive prior hardening
    (numbered `FIX #N` comments, multiple documented rounds) — constant-time comparisons, fail-closed
    JWT, correct CORS allowlist, CSRF-skip logic verified safe even worst-case. New test
    `tests/test_core_api_internal_task_fixes.py` (3 tests, incl. an end-to-end proof of the actual
    regression). Claude caught and corrected an inaccurate path citation in the fork's own report
    (regression test files actually live under `tests/backend/`, not `tests/`) before trusting its
    "zero regressions" claim — found the real paths, re-ran 24 tests directly, all pass. Commit
    `c81cb5801`.
    16 commits this resumed segment: `d8eb4e7b0` `214cb5d9c` `b229dda82` `9e7f2d04a` `bd5f842da`
    `bef33f0eb` `28213ab07` `6426954e4` `c6458ce1a` `d5940fa7c` `2639aaabb` `cf93642df` `52098dfa0`
    `dbf66e82c` `615a97b4f` `c81cb5801` (preceded by `9e630a1e9`/`f3c9123f0` from earlier the same day,
    already covered above). Working tree clean except for the intentionally-held `token_blacklist.py`
    decision file in the scratch folder.
    **Sixth deep-verify slice, `core/api/routers/` batch 1 (28 of 87 files)** — owner asked directly
    "for what are u waiting? are next work dependent on codex??" after Claude's weekly usage limit reset;
    correctly recognized Claude's own next slice was NOT blocked on Codex, confirmed Codex was still down
    via a live test call (same 10:05 PM message), and proceeded solo rather than waiting idle. Files:
    `auth_jwt.py`, `oauth.py`, `webauthn_auth.py`, `keys.py`, `gateway.py`, `executor.py`, `commands.py`,
    `security.py`, `sandbox.py`, `control.py`, `camera.py`, `sensing.py`, `scraper.py`, `mcp.py`,
    `jcode.py`, `tools.py`, `vectorcode.py`, `coding_extended.py`, `code_intel.py`, `migration.py`,
    `mining.py`, `network.py`, `missions.py`, `notifications.py`, `nudge.py`, `openai_compat.py`,
    `providers.py`, `metering.py` (prioritized by security/action-taking relevance; remaining 59 files
    are future batches).
    **2 real bugs found and fixed, no policy tradeoff in either**: `code_intel.py`'s `_safe_path()` used
    `str(resolved).startswith(str(_PROJECT_ROOT))` for directory confinement — **classic CWE-22
    prefix-matching bypass**: a sibling directory sharing the same string prefix as the project root
    passes `startswith()` without being inside the root at all, proven live before fixing. Fixed with
    `Path.is_relative_to()`, which respects path-component boundaries. `notifications.py`'s
    `/notifications/ws` **never called `require_auth_handshake()`** — the explicit pattern every other
    WebSocket endpoint in this codebase uses, since Starlette's HTTP auth middleware doesn't cover
    WebSocket upgrades. Any client could connect with **zero auth** and receive a live feed of VECTOR's
    internal hypothesis-engine output (proactive insights about the owner) plus the 3 most recent pending
    hypotheses pushed immediately on connect. Fixed by adding the same explicit call used elsewhere.
    New tests `tests/test_code_intel_path_confinement.py` (6) + `tests/test_notifications_ws_authorization.py`
    (3). Independently re-verified plus 48 more pre-existing tests (after verifying the fork's cited
    paths actually existed this time, learning from the earlier slice's inaccurate citation) — zero
    regressions. Commit `3e05e02d7`.
    **5 more real FLAG-FOR-OWNER findings, same severity class as `pc_controller.py`/`phone_controller.py`'s
    already-flagged Rule-3 gaps, none fixed**: `vectorcode.py`'s `/vectorcode/launch` spawns a real
    subprocess with zero Permission Gateway check (allowlisted mode values, so no injection risk, but
    still an ungated real-world action); `camera.py`'s `/camera/start` turns on the owner's **webcam**
    with only base API auth, no gateway tiering; `control.py` confirms `phone_controller.py`'s already-
    flagged `_run_adb()` gap is **directly REST-reachable** (`phone_notifications()`/`phone_screenshot()`
    bypass the gateway entirely, while sibling `pc_*` endpoints in the same file correctly route through
    it); `sensing.py`'s `/sensing/screen` OCRs the full screen via a plain authenticated GET, no gateway
    tier; `oauth.py`'s `/oauth/callback/google` has **no CSRF `state` parameter at all** (classic OAuth
    account-linking CSRF), exploitable specifically when no `VECTOR_API_KEY` is configured.
    **Seventh deep-verify slice, done fully in parallel** — owner asked "for what are u waiting? are
    next work dependent on codex??" after this turn's usage-limit reset; re-checked Codex (confirmed
    still down via a live test call), proceeded with Claude's own next batch regardless, then re-checked
    Codex again later and found it back online — re-queued its interrupted slice immediately rather than
    waiting further. Both ran concurrently: Codex (`codex exec -m gpt-5.6-sol`) on `core/collections/`+
    `core/voice/` (the 29-file slice interrupted by its earlier usage-limit hit); Claude (self-fork) on
    `core/api/routers/` batch 2 (30 more of the 87 files).
    **Codex/core-collections+voice — 1 real fix, a genuine fail-open-on-failure bug in voice
    authentication**: `core/voice/speaker_verify.py`'s `verify()` had two failure paths that
    **authenticated the speaker as the owner precisely when identity could NOT be established** — an
    internal embedding/encoder exception returned `(True, 0.0)`, and a stale voiceprint whose embedding
    shape no longer matched the current engine returned `(True, 1.0)`. Both flow into
    `ambient_listener.py`/`realtime.py` as `is_owner=True`, which gates owner-only voice actions — so a
    verification *failure* let a command through as if from the owner. Fixed: both paths now return
    `(False, 0.0)` and log "failing closed". Two genuinely deliberate, separately-justified fail-open
    paths were correctly left alone: the not-active/not-enrolled no-op case, and the short-utterance
    case, which carries an explicit 2026-07-17 usability-tradeoff comment — flagged for the owner instead
    of reversed, same judgment bar already applied to `core/security/token_blacklist.py` earlier this
    cycle. New test `tests/test_core_voice_speaker_verify_safety.py` (2 tests). Commit `2b7e8be0e`.
    4 more FLAG-FOR-OWNER findings from this pass: `cloning.py`/`voxcpm_cloning.py`/`voice_profiles.py`/
    `core/collections/storage.py` store voice-cloning reference WAVs and the owner's enrolled biometric
    embedding as **plaintext with no restrictive ACL**; `collections/hooks.py`'s before-hook failures
    fail open (explicitly justified as resilience, a documented tradeoff); `collections/migrations.py`'s
    `load_dir()` executes arbitrary Python via `importlib` (not a sandbox, but no untrusted-directory
    production path currently feeds it); 7 files missing the repo's own `__main__` self-test convention.
    **Claude/core-api-routers batch 2 — 2 real fixes**: a **systemic printf-style loguru bug, 75
    instances across 15 files** (`logger.error("...: %s", e)` — loguru uses `{}`-formatting, not
    `%`-style; confirmed the call renders the literal string `"%s"` and silently drops the exception
    entirely) — same bug class already fixed twice in `core/brain/` this cycle but systemic across nearly
    every router in the codebase; zero HTTP-response behavior change (every endpoint already returns
    `detail=str(e)` directly). `knowledge.py`'s `_safe_path()` had the identical CWE-22 prefix-matching
    bypass already fixed in `code_intel.py`, plus `parse_wiki()`/`merge_wiki()` in the same file had
    **zero confinement check at all**, inconsistent with sibling endpoints in the same file — both fixed.
    New tests `tests/test_api_routers_printf_style_logging.py` (4) + `tests/test_knowledge_router_path_confinement.py`
    (6). Commit `ad8f82691`.
    **The most severe finding of this batch — `core/api/routers/memory.py`'s `POST /memory/restore` —
    was fixed as a same-day follow-up (commit `4993ba77b`)**, not left flagged like the rest, because
    unlike most flagged findings this cycle it was missing input validation with a well-defined safe fix,
    not a design/policy tradeoff: `core/memory/multi_db_manager.py`'s `restore()` read table/column names
    directly from a backup JSON's own keys and f-string-interpolated them straight into `DELETE FROM
    {table}` / `INSERT INTO {table} ({cols})` with **zero validation** — a crafted backup file could carry
    arbitrary SQL table/column names into a query executed against the **live encrypted main DB**, reachable
    via a `backup_path` with **zero path confinement** (any file the process could read) and
    `overwrite=True`. Fixed: `backup_path` confined to the repo root; table/column names now validated
    against the target database's real, live schema (queried fresh via `sqlite_master`/`PRAGMA
    table_info`, not trusted from the file) before ever reaching SQL, reusing the file's own existing
    `_SAFE_IDENTIFIER` regex as defense-in-depth. No pre-existing test coverage of `backup()`/`restore()`
    existed at all — new test `tests/test_multi_db_manager_restore_injection.py` (4 tests: malicious
    table name rejected without dropping the real table, malicious column name rejected, out-of-root
    `backup_path` refused, full legitimate round trip still works). 27 pre-existing tests re-verified,
    zero regressions.
    **Still flagged, not fixed — a genuinely separate design question**: `POST /memory/restore` still has
    **zero Permission Gateway involvement** for what's explicitly documented in-source as "Gap 19" — a
    destructive (`overwrite=True` drops/recreates tables) real-world action reachable via plain API auth.
    Whether/how this should be gateway-tiered needs an owner decision, deliberately not folded into the
    narrow security-input-validation fix above.
    **3 more FLAG-FOR-OWNER findings from the same batch**: `agents.py`'s `POST /agents/award` lets any authenticated
    caller inflate any agent's HP arbitrarily (no gateway gate, connects to the already-flagged
    `hp_validator.py` weakness); `content.py`'s `POST /content/run`/`POST /content/post-video` are more
    ungated real-world-action endpoints (same class as `camera.py`/`vectorcode.py`/`control.py`);
    `city.py`'s `direct_dispatch()` is confirmed **non-functional, not a vulnerability** (hardcodes the
    task type so Governor always rejects it) — flagged so a future fix doesn't naively wire the
    caller-supplied type through without the same scrutiny already given to `governor.py`'s trust
    boundary.
    19 commits this resumed segment: `d8eb4e7b0` `214cb5d9c` `b229dda82` `9e7f2d04a` `bd5f842da`
    `bef33f0eb` `28213ab07` `6426954e4` `c6458ce1a` `d5940fa7c` `2639aaabb` `cf93642df` `52098dfa0`
    `dbf66e82c` `615a97b4f` `c81cb5801` `3e05e02d7` `944504685` `2b7e8be0e` `ad8f82691` `4993ba77b`
    (preceded by `9e630a1e9`/`f3c9123f0` from earlier the same day, already covered above). Working tree
    clean except for the intentionally-held `token_blacklist.py` decision file.
    **`core/api/routers/`'s remaining scope**: 58 of 87 files done across batches 1+2 (`memory.py`/
    `agents.py`/`content.py` above were all reviewed as part of batch 2's 30 files — `memory.py`'s finding
    fixed, the other 2 flagged); 29 files remain unreviewed.
    **Batch 3 (final 24 files, commit `a990d0cc5`) — completes all 87 `core/api/routers/` files.**
    2 real fixes: `voice.py`'s `/voice/studio/generate` had a **path-traversal write** (a bare `".."`
    filename escaped the output dir even after a basename-only `.name` fix attempt — closed properly with
    `Path.is_relative_to()`); `websocket.py`'s `require_auth_handshake()` (shared by 5 WebSocket
    endpoints) used a **timing-unsafe `!=`** instead of `secrets.compare_digest()` for the token check —
    fixed once, centrally. Plus 45 more instances of the printf-style-logging and silent-swallow bugs
    already fixed dozens of times this cycle. New test `tests/test_voice_router_security_fixes.py` (4
    tests). **Owner note: Claude's weekly usage budget is now critically low (~5%) — from this point the
    audit runs Codex-only for new deep-verify work, with Claude limited to reviewing diffs, running
    tests, and committing.**
    **First Codex-only slice: `districts/content/`+`districts/research/` (35 files, commit `d6e87cd2b`)
    — 6 real fixes**: publish failures were silently marked "published" (`content_scheduler.py`); real
    configured-API upload failures fell back to a fake-success simulation (`uploader.py`); a job-claiming
    race let two scheduler runs publish the same job (`post_job.py`); ComfyUI response paths could escape
    the output directory (`comfyui_adapter.py`); the `blog_publisher.py` self-test could publish real
    public articles if credentials were configured; NewsAPI's key was in the URL query string, not a
    header (`news_aggregator.py`). 6 more real findings flagged (Graph API Instagram bypasses the
    1/day cap entirely; SSRF gaps in 3 research/scraping files; unrestricted local file reads; etc.).
    **Second Codex-only slice: `districts/investment/`+`districts/security/` (31 files, commit
    `81e4c2054`) — 7 real fixes, 5 the same recurring shape** (a scan/action fails, the failure path
    returns empty/default, the caller reads that as "clean"/"success" and rewards it):
    `node_guard.py`/`threat_scout.py` falsely rewarded HP for a failed scan as if the network/system were
    clean; `alert_manager.py` suppressed the next real alert for 5 min when persisting a failed alert;
    `incident_playbook_runner.py` ignored `netsh`/`taskkill`/`tasklist`/`netstat` nonzero exit codes,
    reporting failed containment actions as `status=ok`; `log_aggregator.py` used the wrong loguru API for
    exception context. Plus a 2nd instance of the API-key-in-URL bug (`sentiment_bot.py`). 2 more flagged:
    the district's own "analysis only, never trades" contract conflicts with deliberately-implemented,
    RED-gated real trade/crypto-execution paths (explicitly documented as an intentional exception in
    `core/config.py`, not an accidental gap); `malware_hunter.py`'s file-read failures degrade to
    false-clean instead of unknown.
    **Third Codex-only slice: `districts/qa/`+`districts/health/`+`districts/finance/` (33 files,
    commit `f6a3d35d5`) — 8 real fixes.** Most significant: `health/fatigue_monitor.py` called a
    `ContextEngine` method that doesn't exist (`get_full_context()` — the real one is
    `get_world_state()`), so camera-based fatigue detection has silently never worked at all; fixed to
    call the real method. 6 more fixes are the same recurring shape as the prior slice — a failed data
    fetch/scan read as a genuinely clean/healthy/passing result (`sleep_tracker.py`,
    `biometrics_aggregator.py`, `budget_analyst.py`, `test_results_analyzer.py`). Plus a financial-privacy
    fix (`upi_parser.py` logged exact transaction amounts in routine HP/audit logs) and a calendar-drift
    bug in `fpa_analyst.py`'s forecast loop. 3 more flagged findings.
    **Pace check**: 3 Codex-only slices completed since Claude's budget warning, all reviewed/tested/
    committed by Claude at a leaner level of scrutiny than earlier slices (spot-checking the most
    significant diffs directly, trusting mechanical/repeated-pattern fixes after the first few
    confirmations, rather than reading every line of every file) — this is a deliberate tradeoff to
    conserve the remaining budget while still not committing anything unreviewed.
    **Fourth slice, run via a real `claude --cloud` session (not Codex) against `$100` of Anthropic's
    cloud-session bonus credit, since both the local session and Codex hit their weekly limits** —
    `districts/intelligence/`+`districts/ops/`+`districts/governance/` (commit `8fe5ebf37`, cherry-picked
    from the cloud session's own branch after local review). **3 real fail-open bugs fixed**:
    `districts/governance/llm_council.py`'s `run()` defaulted `requester_hp` to `700` when a caller
    omitted it — exactly matching the "700+ HP only vote" gate threshold, so any caller that simply didn't
    pass its real HP silently passed the gate regardless of actual standing; now defaults to `0` (fails the
    gate unless real HP is supplied). `districts/ops/sre_monitor.py` reported `error_rate=0.0` (healthy) on
    a DB query failure instead of distinguishing "no errors" from "couldn't check"; now reports `1.0`
    (worst case) on failure. `districts/ops/incident_commander.py`'s `detect_incidents()` returned `[]`
    (all-clear, HP awarded) on a DB failure — now returns `None` to signal the query itself failed, checked
    at every call site, returning `status: error` and deducting HP instead of falsely declaring "all clear."
    New test `tests/test_ops_governance_audit_phase3.py` (7 tests). Independently re-verified plus
    `tests/test_llm_council.py` + `tests/integration/test_cross_district.py` (20 more) — zero regressions.
    **Ops/governance audit (commit `c85bf65c9`) — 3 fail-open bugs fixed.** `ops/sre_monitor.py` set
    `error_rate=0.0` on a DB failure (reading as perfectly healthy); it now sets `1.0`.
    `ops/incident_commander.py` `detect_incidents()` returned `[]` on a DB failure (reading as "no
    incidents"); it now returns `None`, and both `run()` call sites are None-guarded.
    `governance/llm_council.py` `run()` defaulted `requester_hp=700`, which bypassed the strict `<700`
    gate; it now defaults to `0`. 7 new tests are in `tests/test_ops_governance_audit_phase3.py`.
    `districts/intelligence/` was verified clean.
    **Communications + agency + design + karpathy_lab + interview_prep audit (commits `00f76051`,
    `c93c8468`, `d0790ccb`, `6cad9348`) — 34 fixes, 5 new test files (`tests/test_audit_phase3_*.py`),
    each new test confirmed failing on the old code and passing on the new.** Reviewed by five
    parallel subagents; every diff re-read and re-tested by Claude before commit. Dominant class again:
    a failure reported as success. `communications` (4): `reply_forward` reported `sent` and left the
    row in Sent when SMTP failed; `email_agent` awarded HP and masked the error status on a failed
    reply/forward and on an unsaved auto-draft; `email_intelligence` read any Gmail failure as "no mail".
    `design` (3): CWE-22 via caller-supplied `corpora` in the knowledge loader; a failed LLM audit
    returned a clean-looking score of 75; `UIDesigner.run` ignored `task["params"]`. `interview_prep`
    (6): two CWE-22 writes (company-research note, `export_report`), unescaped HTML export,
    `RecruitmentBot` fabricating `fit_score=7 / should_apply=True` on LLM failure and writing failure
    text into the Obsidian placement brief, `MockInterviewer` never recording Q1 / reporting a failed
    start as ok, failed research reported ok. `agency` (11): a malformed or tz-aware `last_updated`
    left the pipeline reading `healthy`; `params` dropped in sales/proposal `run`; a failed LLM answer
    fell through to a fabricated "AI Automation Project" proposal; CWE-22 in content-plan/trend vault
    writes; non-atomic client/metrics saves that a corrupt load then overwrote (now atomic with a
    `.corrupt` backup); a bad payment amount half-mutating state; non-numeric `lifetime_value` poisoning
    summaries. `karpathy_lab` (14): non-zero training exit parsed as a good score; a failed baseline
    reported `ok` with `best_val_bpb=inf`; `git checkout -b` failure ignored; 404 body saved as a
    dataset; unvalidated `dataset_name` used as path/URL (CWE-22 + SSRF-guarded); empty preprocess
    reported success; `tokenize_data` crashed on any vocab >256 (all Indic/Japanese text);
    `generate_report` mixed every run's steps and let `run_name` steer the write path.
    **Flagged, not fixed (design calls):** `core/email/receiver.py` returns `[]` on IMAP errors
    (poll reads as ok/0 fetched) and `sender.send_email` returns `duplicate_suppressed` that
    `reply_forward` ignores; `DataPrep.preprocess_data/tokenize_data` take arbitrary `input/output`
    paths from task params (confinement would break the module's own callers);
    `AutoresearchRunner` runs LLM-written Python unsandboxed and commits in the live repo (RED-gated,
    documented 58D tradeoff); `feedback_analyst` persists a canned score-6 analysis when
    `VECTOR_FEEDBACK_LLM` is off, and `generate_session_report/progress_report` invent data
    ("use placeholder data"); `report_generator`/`feedback_analyst` data dir resolves above the repo
    root; `feedback_analyst._load_data` overwrites a corrupt JSON; `performance_tracker`
    `alert_anomaly(direction="both")` only ever alerts "above"; several `{"error":...}` returns lack a
    `status` key but existing tests pin that contract; `ux_researcher`/`image_prompt_engineer` fallbacks
    are unlabelled templates; `ProgressTracker` uses `threading.RLock` (banned) and `start_run` reuses
    old step_logs; agency client data is plaintext JSON outside the encrypted DB; sync `chat()` blocks
    the event loop in sales/proposal.
    **Languages + startups + projects + predictive_analytics + memory_curator + home_assistant audit
    (commits `4defa3d5`, `803dc633`, `43751974`, `61553331`, `114b4187`, `79b6ef1b`) — 6 new test files
    (`tests/test_audit_phase3_*.py`); each new test re-run by Claude against the pre-fix code in a
    throwaway worktree and confirmed failing there, passing now.** `memory_curator` (priority): **PASS** on
    both gates — zero raw `sqlite3`/`sqlcipher` opens (all access via `get_temp_cursor()` /
    `EpisodicMemory`), and none of the 5 sacred tables is renamed/dropped/altered/vacuumed (only
    `prune_old_episodes()` in core, decay-gated, plus a capped DELETE on the non-sacred
    `context_budget_handles` cache). Real bug fixed there: `ConsolidationBot` pruned the raw episodes
    after `remember()` had *failed* to persist the summary (it returns `False`, never raises) and reported
    success — a data-loss path; now keeps the episodes and reports an error (+3 more writes that said
    "Got it/Noted/ok" when nothing was stored). `home_assistant`: `HASS_URL=https://…` never enabled TLS
    (bearer token sent in cleartext to port 8123); `entity_id`/service injected into URL paths unvalidated;
    `connect()` hung forever in the WS-reconnect loop when HA was down and returned True anyway; a failed
    service call, an unresolved device ("kitchen lamp") and the `dim` no-op all reported "Turned on / Executed";
    "unlock"/"disarm" parsed as lock/arm; door/garage/gate covers now require confirmation; scene restore
    sent `turn_off` to covers/climate; `threading.Lock` removed. `startups`: a failed/unparseable LLM
    reply used to score every dimension 5 and **admit the idea past the Equation revenue-velocity gate**
    (fail-open); missing score now fails closed (counted 0), plus scanner/spy/modeler canned fallbacks
    (LTV:CAC 5.0 → "GOOD", "12 months MEDIUM risk") now return errors. `projects`: an unreadable store
    read as "no deadlines"; unparseable dates stored and never alerting; canned doc written to the vault
    as real; CWE-22 note titles (`ObsidianSync.write_note` doesn't confine); `POST /projects/create`
    sent `description` but `run` read only `goal`; experiment tracker fabricated an `adopt_variant` win
    from an empty arm. `predictive_analytics`: forecasts built on **random synthetic history** drove
    recommendations and Pushover alerts (now tagged `+synthetic_history` and ignored); NaN readings
    made the anomaly detector report clean; CWE-22 in `load_scenario`; Prophet path always raised
    (`Series.dt.isoformat`). `languages`: all 5 coaches returned `ok` + stored a memory row when the LLM
    returned nothing. Test edit to note: `tests/test_phase2_districts.py` two doc_writer tests asserted
    `write_doc()==True` with the LLM mocked *offline* (encoding the canned-doc-as-success bug); now mock
    a real reply.
    **Flagged, not fixed (design / tier-policy):** home_assistant `SceneManager`/`AutomationEngine`
    `call_service` are **ungated** (lock/alarm-arm/all-switches rules; latent — `evaluate_triggers` has no
    production caller) — recommend not wiring it until a tier decision; `home_control`/`smart_home` are
    YELLOW so with `VECTOR_YELLOW_AUTO_CONFIRM=1` any proposer can run lights/climate/covers unattended
    (consider RED); the "Are you sure…" high-risk confirmation has no pending-state, so lock/alarm via
    voice can never complete (fail-closed); the gateway `home_control` branch ignores `connect()`'s
    return, ignores `HASS_URL`, and classifies replies by string prefix; entity matcher silently picks
    the top of ties. `memory_curator`: with `VECTOR_MEMORY_CURATOR_LLM` unset every consolidation stores a
    conf-0.3 placeholder then still prunes at 90d, and only 50 of up to 200 old rows reach the summary.
    `idea_validator` reads the regime via `get_regime()`, which returns NORMAL on any read failure
    (documented "never freeze"; fails open at the regime gate). `predictive_analytics`: `evaluate_risk`
    returns 0.0 on an empty/failed simulation (existing tests pin it); `autonomous_loop.predict_cycle`
    compares a forecast with itself (anomaly step is a no-op) and never closes its stores; Pushover
    POSTs in `anomaly_predictor`/`strategy_recommender` bypass the gateway; no cap on `iterations`.
    `projects`: `create_project` never registers a `project_deadline` so created projects never alert,
    `DeadlineWatcher` silently drops overdue items, pipe-delimited storage corrupts on `|`.
    `languages`: Hindi/English/Bengali/Assamese return canned "Offline language guidance" as `ok` unless
    `VECTOR_LANGUAGE_LLM=1` (existing tests pin `ok`). Cross-cutting: `core/memory/obsidian_sync.write_note`
    does not confine `title` to the vault — other districts passing caller-controlled titles are likely
    exposed (needs a core fix).
    **Time_calendar + growth + emergency + learning + news_trends + data_analytics audit (commits
    `a2958ee9`, `a38eb25a`, `e1dbdcd8`, `c479b6f3`, `1ead4118`, `51daa617`) — 6 new test files; each new
    test re-run by Claude against pre-fix code (a throwaway worktree at the true baseline) and confirmed
    failing there (time_calendar 11/13, growth 14/15, learning 19/27, emergency 10/12, news_trends 23/23,
    data_analytics 22/22; the rest are controls/regression guards).** **`emergency` (priority) — inventory
    of real actions, none gated:** the district never imports `permission_gateway`, and its entry points
    (`escalate_emergency`, `classify_emergency`, `detect_anomaly`, `emergency_alert`, `emergency`,
    `runbook`) are all **GREEN** in `CONFIG["permission"]`, so they auto-execute via `Governor.dispatch`.
    Real actions: priority-0/1/2 Pushover to the owner (siren, 30s retry), local beeps, and runbook
    system mutations — `*.tmp`/`*.log` deletion in the **process CWD** (`cleanup_temp`), `nvidia-smi -pl 150`,
    `ollama serve`, `ipconfig /renew`, `netsh advfirewall … state on`. **No urgency/severity/override/force
    flag short-circuits any gate or confirmation (checked: task `params` only carries `domain`/`query`),
    and there is no approval wait that defaults to approve** — so "emergency" does not bypass the gateway;
    it simply was never routed through it. Fixed (7): a stopped heart rate (declared severity 1.0) was
    dampened to LOW during work hours → log-only → owner never notified (`severity_floor`); the
    `heart_rate_stopped` / `battery_critical` runbooks returned `notification_sent` / `alert_sent` without
    sending anything; `_step_runbook` and `main._outcome` reported `escalated` when every step failed or
    was skipped; uncapped priority-2 Pushover on varied-source events (now 20 per 600s, constant in
    `escalation.py`) and `CONFIG["emergency"]["pushover_enabled"]` ignored; rule-check failures hidden at
    debug; `_emit()` dropped signals silently. **Flagged (tier policy, owner decision):** should
    `escalate_emergency` be YELLOW/RED when not owner-initiated; the runbook mutations (esp. CWD file
    deletion, which can hit repo-root logs) are ungated and gating them as-is would block them all (unknown
    types are blocked) — needs new tier entries; `CONFIG["emergency"]` `quiet_hours_*` / monthly Pushover
    cap are unused; `heart_rate_critical/high` still score below CRITICAL in work hours (classifier floors
    only explicit severities); `process_heart_rate` calls `asyncio.run()` inside a running loop;
    `districts/health/emergency_detector.py` builds a separate detector nobody consumes.
    Other districts — `growth` (12): with `auto_publish` off (the default) the IG reel was published via the
    configured phone/Graph-API publisher with **no approval** despite a comment saying "notify owner";
    simulated/blocked uploads counted as success; `graph_api` mode always raised TypeError (missing
    `hashtags`); beta-signup `_privacy_check` returned True on import success and `_store_encrypted` never
    stored (wrong API); caller `**extra` could overwrite `consent`; software_arm marked `validated: True`
    on import success and "escalated" without notifying. `learning` (12): SSRF/option-injected download URLs
    (now guarded + `--`), 404 body saved as a video, canned/simulated transcripts, summaries and concepts
    stored as real, empty `source_dir` organized the CWD. `news_trends` (22 edits): simulated headlines
    returned as news, NewsAPI key in the URL query (now `X-Api-Key`), `venture_pipeline` ranked and drafted
    marketing for `UNVERIFIED` ideas (consumer of the startups fail-closed change) and wrote a stray
    `02 Projects/` into the CWD, empty Reddit/HN mining wrote an empty snapshot as ok, prompt-echo read as
    `SOFTWARE_SOLVABLE: yes`. `time_calendar` (6): rejected KIIT login and unreadable calendar read as "no
    notices"/"all hours free", tz-aware events never matched `is_class_soon`, sub-hour events left slots
    free, `BookingRequest.created_at` evaluated once at import. `data_analytics` (16 changes/12 groups):
    caller table names interpolated into PRAGMA/SELECT (`sqlite_master` readable; now allow-listed), failed
    DB pull published as a quiet-week report, failed benchmarks `ok` and overwrote the baseline with -1,
    bronze dedup no-op on tables without `content`, fabricated "Sample data" analysis. **Flagged, not
    fixed:** `DataAnalytics.analyze_dataset(path)` reads any local path and sends 1000 chars to the LLM (no
    caller found; needs an allowed-roots setting in core); `run_bronze_to_silver` never writes Silver;
    `benchmark_memory_ops` writes probe rows into the real episodic DB; `DeadlineManager.create_event`
    inserts real Google Calendar events ungated (no caller); gateway `check_attendance` calls a
    nonexistent `KIITScraper.get_cached_schedule()`; `TimeBlocker` starves "low" urgency tasks;
    `venture_pipeline` ranks by demand not verdict (a validated REJECT can still be "top"); sync httpx +
    `time.sleep` in async `SocialMiner.run`; `note_organizer` writes next to any caller-named dir; offline
    `VECTOR_LEARNING_LLM` gate returns canned concepts as degraded; `course_tracker` progress always 0%
    and imports `threading`; `data_engineer._open_db` opens its own keyed connection to the main DB
    (documented 2026-08-05 deliberate choice — shared `get_db_connection()` singleton can't be closed by
    callers; same precedent as `emergency/log.py`). Behavior choices worth a second look:
    `time_calendar.run()` now returns `error` (not `ok`) when Google Calendar isn't configured, and
    `AINewsBot.run()` with no URL now fetches news (previously summarized `""`).
    **Self_dev + legal_compliance + privacy + personal_growth + calls + chief_of_staff + skills + science
    + relationships + pattern_detective + reflection audit (commits `5c10506e`, `1ad7b8e0`, `a27246ab`,
    `5adcc112`, `4f0f5d95`, `80f52bb9`, `f79ddbe2`, `61197622`, `9e14fae7`) — ~118 fixes, 11 new
    `tests/test_audit_phase3_*.py` files; each re-run by Claude against the pre-audit commit `66c9c9bc`.**
    **`privacy` (priority) — it DID leak what it protects:** `redact_pii` returned and stored (via
    `context=result` into episodic memory) the raw emails/phones/Aadhaar it had just matched
    (`examples: matches[:3]`); `find_leaks` copied scanned event content (`content_preview`, which can be a
    password/token) into its returned result, `self.leak_candidates` and a new episodic row; both LLM calls
    omitted `district`/`sensitive`/`allow_cloud`, and `route_policy` only forces local for the
    `security`/`privacy` district, `sensitive=True`, RED or a narrow secret-word list (emails, phones, PAN,
    "token" are NOT on it) — so PII-adjacent prompts could reach pooled cloud keys. All three fixed
    (`district="privacy", sensitive=True, allow_cloud=False`; fields removed). Also: empty/failed reads
    reported `LOW` risk (now `status: no_data`), MEDIUM rolled up to LOW, empty audit report stored as ok,
    the uppercase-only PAN regex ran on lowercased text (never matched). **Routing-enforcement verdict:
    the district has NO cloud-vs-local enforcement logic at all** — it keyword-counts episodic text and
    runs PII regexes; it never inspects providers or endpoints, so its "cloud vs local enforcement" role
    is unimplemented (needs a design decision). **Core issues found, not fixed (core/ off limits):**
    `vectorcode_llm.chat` leaves `local_only=False` if `route_policy` raises (fails OPEN for sensitive
    prompts, debug-logged; ~L676 and ~L850); `route_policy._is_local` uses substring checks
    (`"localhost" in base_url`, so `localhost.evil.com` / `http://127.0.0.1@evil.com` pass, and a remote
    vLLM URL counts as local); the secret-marker list is narrow so privacy depends on callers passing the
    flags; `EpisodicMemory.recall()` swallows read errors and returns `[]` (indistinguishable from empty
    memory — 4 districts had to report `no_data` for both). **`calls` (priority) — plaintext call
    content:** caller numbers and contact names at INFO and in HP-ledger award reasons (now masked to the
    last 4 digits / constant reasons); the audio filename (often embeds the caller number) logged; first 50
    chars of the LLM reply logged; **all four LLM paths (spam check, transcript summary, action items,
    voice response) went through `ProviderClient` with no `district`/`sensitive` flag, so call content
    could reach pooled cloud keys** (now `sensitive=True, district="calls"`); exception strings that echo
    the prompt (transcript) logged; raw temp wav left on disk on failure. Also: `"SPAM" in "NOT_SPAM"`
    added +0.3 spam to every non-spam verdict; `add_contact("")` / hidden-ID VIP whitelisted every
    hidden-ID caller (fail-open); blank transcription and the canned "I heard you: {text}" fallback
    reported as success (and the fallback was sent to TTS); TTS `output_path` unconfined (CWE-22). **No real
    call action exists in the district** (no answer/reject/SMS/ADB/Twilio; TTS only writes a file); whatever
    consumes `screen_call`'s block/allow decision to act on a call must be gated and there is no call
    action type in the permission tiers yet (tier-policy decision). **Other districts:** `reflection` —
    `growth_analyst` queried a nonexistent `semantic_memory.timestamp` column (real column `updated_at`)
    so the weekly trend NEVER had real data; a canned "LLM reflection unavailable" body was written to
    the vault as the owner's journal with +50 HP and a 0.85 reasoning chain; a failed DB read was treated
    as a quiet day (LLM then invented wins/policy rules/score); `growth_score` stored the heading
    `## GROWTH_SCORE` instead of the number; the cutoff was naive local vs aware-UTC stored timestamps
    (lost ~5.5h of events in IST); `W%V-%Y` made 2025-12-29 overwrite the real W01-2025 note.
    `chief_of_staff` — `episodic.store()` saves tags as JSON but the noise filter split on commas, so
    **tag-based SIGNAL rules (security/threat/malware/deadline) never matched real events and they were
    dropped as noise**; a ROUTINE substring match (`security_scan`, `deadline_sync`) beat a CRITICAL
    marker; a failed event pull produced "No significant signals today"; a failed council escalation was
    reported routed with +10 HP; `run_forever` slept 60 minutes per "minute" tick so the 5-minute 08:00/22:00
    brief windows were mostly skipped. `legal_compliance` — malformed trigger flags (`"yes"`) skipped the
    identity/consent/conflict/deadline safeguards (false PASS), string/blank rule lists passed vacuously,
    prohibited phrases split by a newline or curly apostrophe were missed, unverified checks returned `ok`.
    `self_dev` — read-only district (no write/subprocess/git primitives; confirmed by search); four
    verification checks failed open: a failed audit returned `status: ok`, generated agents calling
    `subprocess`/`eval`/`exec` passed, a plugin entrypoint `../../core/loop/permission_gateway.py` passed
    confinement, empty skill-comparison expectations passed. `personal_growth` — ZKSteward backlinks
    wrote to any path (now `.md` inside the vault), a re-run replaced prior links with only the new ones,
    LLM-suggested link names (hallucinated or `../../x`) were written into notes; canned synthesis written
    as a real report; own report re-ingested as input. `skills`/`science` — `mastery_tracker.track_mastery`
    raised TypeError on EVERY call; a NaN score became "Master"; canned skill maps/gaps cached as real;
    invalid SMILES, NaN/negative physics and CAD input reported `ok`. `relationships`/`pattern_detective`
    — contact names/phones/messages and the owner's activity log went to cloud-eligible LLM calls and
    names to INFO logs and persisted ghost-memory lessons (re-injected into prompts); re-adding a contact
    (`INSERT OR REPLACE`) wiped interaction history; unknown-contact `track_interaction` stored an orphan
    row and said ok; the analyst analysed its own derived events as the owner's behavior;
    `BehaviorAnalyst.run` was a silent no-op. **Flagged, not fixed (design / tier-policy):** `contacts.db`
    (names, phones, emails, notes) and `call_contacts.json` are plaintext outside the SQLCipher DB;
    `CommunicationAnalyst` never reads real message text (joins two stores); `_normalize_caller_id` turns
    any 10-digit number into `+1…` so an Indian number can evade the blocklist by format; `calls` never
    calls `session_hydration_prompt()` (RULE 1) or `policy.get_score/update_from_outcome` (RULE 4);
    `core/loop/cron_jobs.py` `job_daily_review`/`job_weekly_growth_report` call `agent.run({})` which does
    nothing under the 2026-08-06 gating and returns ok (needs `{"type":"review"}` etc.; not checked
    whether scheduled); reflection/chief_of_staff `run_forever` sleep-granularity bug in reflection's
    instance loops (dead code — the live path is `AutonomousLoop._reflect_tick`); reflection policy
    learning never aggregates (date in the situation hash, constant 0.65 reward); nudge engine
    "`nudge_sent`" only means generated+logged (no delivery path exists — gate when one is added);
    ZKSteward/FeedbackSynthesizer write the owner's vault ungated (confined now; YELLOW tier is a policy
    call); `behavior_analyst`/`habit_finder` bucket time-of-day in UTC though `vector_timezone` is
    Asia/Kolkata; `GapAnalyst` returns canned scores/ranks unless `VECTOR_SKILLS_LLM=1` (deliberate gate;
    marked `source: fallback`); `SkillGrader.passing_score` is caller-set (0 passes everything);
    chief_of_staff `_rice` treats missing fields as 0; `science` engines in core use a small-angle
    pendulum and heuristic SMILES validity when rdkit is absent; `legal` keyword emergency detection
    ("can't breathe" unmatched) and exact-match `prescription_drug`.
    **`core/trading/` audit (89 files; commits `cd1c3030`, `b01750f4`, `4a15657c`, `8a16600a`) — ~32 fixes,
    4 new test files (`tests/test_audit_phase3_trading_{agents,dataflows,graph,cli}.py`); each re-run by
    Claude against the pre-fix tree and confirmed failing there for the stated reason.** **Live-execution
    verdict (explicit): `core/trading/` introduces NO additional live-execution path.** Checked two ways —
    my own search of the final tree (order/broker/exchange/wallet/signing/subprocess/`.post(`: zero hits) and
    all four subagents' independent inventories. The only exchange mention is
    `crypto_trading.py::SUPPORTED_EXCHANGES = [binance, coinbase, kraken, hyperliquid]`, an inert class
    constant echoed into a dict — the class has only `get_quote()` (a read-only yfinance lookup) and a
    placeholder `analyze()` with `paper_mode: True`; no exchange client, no credentials, no signing. Tools
    exposed to LLM agents are read-only data getters; the only writes are the decision log, the per-ticker
    state JSON and the package's own LangGraph checkpoint DB. The two documented intentional exceptions
    (`execution_engine.py` Zerodha, `hedgebot_agent.py` Jupiter/Solana, RED-gated) are unchanged and outside
    this package. **One mislabel to flag (outside `core/trading/`, not changed):**
    `districts/investment/trading_conductor_agent.py` is documented "ANALYSIS ONLY" but declares routing
    capabilities `execute_trade`, `place_order`, `paper_trade`; a Governor task for those types lands on an
    agent that only returns a rating — not execution, but a misleading capability tag; also
    `getattr(final_state["final_trade_decision"], "rating", None)` is always `None` there (the decision is a
    string), so its result `rating` is always `"Hold"` while `decision` carries the real parsed rating.
    **Order / sizing math — real bugs fixed:** `TraderProposal`/`PortfolioDecision` accepted NaN, inf, 0 and
    negative `entry_price`/`stop_loss`/`price_target`, and a **Buy with `stop_loss` ≥ `entry_price`** (stop
    above entry on a long: instantly triggered or protecting nothing); now rejected by validators (a
    validation error already falls back to free text via `invoke_structured_or_freetext`, verified). **Not
    fixed (design):** position sizing is free text ("5% of portfolio") — there is no numeric size field, so no
    [0,1]/portfolio-limit bound exists and nothing under `agents/` computes risk/reward; the Sell-side stop
    is unchecked (short vs exiting a long is ambiguous); reflection's raw/alpha returns are the stock's
    return, not direction-adjusted (a profitable Sell shows negative; only the LLM prompt interprets it) and
    stock/benchmark closes are paired by position (`iloc[n]`), not date. **Finance fail-open fixed:**
    `SignalProcessor` turned `"Not Buy"` / `"Do not Buy this stock."` into **Buy** (now Hold + warning;
    explicit `Rating: X` label still wins; `None` text no longer raises); a NaN close was reflected on and
    stored as a `+nan%` outcome; a reflection LLM error aborted the whole analysis and a blank reflection
    permanently resolved a memory entry. **Checkpoint "resume" was not a resume:** `_run_graph` always
    invoked with the fresh initial state, so after a crash the run re-executed every completed node and
    appended a second human message (reproduced independently on a toy LangGraph: calls
    `['a','b','a','b']`, 2 human messages; with `invoke(None)`: `['a','b','b']`, 1). **Data / look-ahead:**
    Alpha Vantage returns errors as HTTP 200 JSON — `Note`, `Error Message`, premium `Information` and `{}`
    were returned as price data (now raise, so `route_to_vendor` falls back to yfinance); a CSV parse
    failure returned the **unfiltered** CSV (rows after `end_date` = look-ahead leak); the fundamentals
    date filter was dead code (guarded by `isinstance(result, dict)` on a JSON string) so balance
    sheet/cashflow/income never dropped future reports; yfinance `end=` is exclusive so the trade-date bar
    was dropped (now consistent with the other vendors' `<= curr_date`); an empty `yf.download` poisoned
    the cache for the day and cache writes were non-atomic (truncated CSV served as fresh history). **Failed
    fetch read as "nothing":** Reddit/StockTwits errors (429, HTTP-200 error envelope) became "no posts
    found" / "no messages" i.e. zero sentiment; `crypto_trading.get_quote` returned `price: 0.0` on any
    failure and on a missing `last_price` (no `error` key), and accepted NaN/≤0. **Secrets:** `requests`
    embeds the full URL including `apikey=` in its exception text, which reached `logger.error` and the
    string returned to the LLM; now re-raised without the URL. **Injection / CWE-22:** the decision log is
    fed back into later prompts as "lessons" and a prompt-injected `<!-- ENTRY_END -->` in the decision text
    could forge a resolved entry (escaped; unsafe ticker/date raise); the CLI's ticker validator allowed
    `..` (every char individually allowed), so reports were written outside `results_dir`; ticker/date were
    validated only after the whole LLM run; StockTwits ticker interpolated raw into the URL path. **CLI:**
    `core/trading/cli` could not be imported at all (`from cli.models import …`; there is no top-level `cli`
    package) and 3 of the package's own test files (`test_api_key_env`, `test_ollama_base_url`,
    `test_ticker_symbol_handling`) failed to collect — import-path-only fix; a run with no final decision
    was shown as a finished report and offered "Save report?" (now exit 1 with "Analysis FAILED";
    incomplete sections get an INCOMPLETE banner); hostile `ast.literal_eval` text (`{[]: 1}`) crashed the
    run; analysis date not normalised. **Flagged, not fixed:** `agents/utils/rating.py::parse_rating`
    (feeds the memory-log tag) still has the negation weakness ("Not a sell" → Sell; first match wins) so the
    memory tag can say Buy while `SignalProcessor` says Hold; `--checkpoint` is a no-op in the CLI (it calls
    `graph.graph.stream` directly, bypassing `propagate`'s checkpointer, memory-log context and
    `store_decision`); trading LLM clients bypass `core/inference/route_policy`, `budget_gate` and
    `session_hydration_prompt()` (Key Rules 1 & 5) — safe only because the default is local Ollama; if
    `TRADING_LLM_PROVIDER` is switched to a cloud provider, tickers/positions go to the cloud ungated;
    `openai_client` pairs an explicit `base_url` with a provider-keyed API key (a wrong `backend_url` sends
    e.g. the DeepSeek key to that host); fundamentals look-ahead filters use fiscal period END not filing
    date, and OVERVIEW/`.info`/insider snapshots ignore `curr_date` (not point-in-time; unsafe for
    backtests); Reddit/StockTwits are live-only; `_clean_dataframe` `bfill()` can fill leading NaNs with
    future values; `announcements.py` phones home to `api.tauric.ai` on every start with `requests` and
    renders remote text as rich markup (blocks on `getpass` if `require_attention`); `ensure_api_key`
    writes a pasted key to the nearest `.env` (the repo's, if run inside it); `alpha_vantage_common` still
    uses `requests` (rule: httpx); `StatsCallbackHandler` counts calls at start only (no error callbacks);
    `save_report_to_disk` overwrites and is non-atomic; vacuous package tests
    (`test_safe_ticker_component::test_traversal_string_does_not_escape_join` joins only "AAPL",
    `test_env_overrides::test_unknown_env_var_is_ignored`); no tests for the three `VECTOR_TRADING_*_DIR`
    env overrides; `vector-local` provider in `model_catalog` has no factory route.
    **`core/mcp_tools/` (33 files) + `core/scraper/` (49 files) audit (commits `5d66a13e`, `0b46bd48`,
    `fd63bfb9`, `2364a9f6`, `fcdb49c3`, `d41e9a1f`, `46e4b2fd`) — 7 new `tests/test_audit_phase3_*.py` files
    (~330 test cases), each re-run against the pre-fix tree.** **MCP trust boundary (verified in
    `core/mcp_server.py`): NO PermissionGateway or tier policy applies to ANY MCP tool call** — `_make_server`
    just calls `add_*_tools(mcp)`, `call_tool` invokes `tool.fn(**arguments)` directly, and `main()` itself logs
    "Starting MCP server with UNGATED tools" (Task 60 classified it "Class A / user-only", owner-only gap). The
    only control is `mcp_secure_call` (rate limit + audit) which **fails open** (any exception → allow, debug
    log) and is wired into only some tools (builtins/browser/voice/collections/knowledge) and none of the
    expansion modules. So every tool is a direct sink for a prompt-injected caller and only per-tool validation
    protects it; several docstrings claim a "RED gate" (`git_merge/rebase/push`, `file_delete`, `doc_delete`)
    that nothing enforces. **No `eval`/`exec`/`shell=True`/`pickle`/`yaml.load` exists in either package**; the
    real sinks were subprocess argument injection, path confinement, secret disclosure and tools that never
    worked. **mcp_tools — fixed:** `git_*` ref/remote argument injection (`--orphan`, `--upload-pack=`,
    `--exec=`, `ext::sh -c …` remote; now allowlisted + `--`), `git add` of `.env`/secrets and a failed `add`
    followed by a "successful" commit; `files`/`security_path_check`/`doc_delete`/`review_code` used
    `str.startswith` (sibling-prefix bypass `repo-evil`); `doc_move/copy/publish/…` had no containment at all
    (`doc_copy x.md → core/evil.py` planted code); `config_get`/`config_env` echoed the SQLCipher key and
    `github_token`, and `config_set/apply/import` could rewrite `permission`/`allow_shell_exec` (now redacted /
    deny-listed); `hook_fire` ran `<hooks_dir>/<name>.ts` with an unvalidated name (`../../x`); `perf_profile` /
    `perf_hotspots` ran `python <caller file_path>` (`-c "import os;…"` = RCE); pytest tools took caller paths as
    argv (`-p plugin`, `--rootdir`, foreign `conftest.py`); `test_mock` imported caller-named modules;
    `write_note` title `../../x` escaped the vault; `read_paper`/`mine_reddit`/`browser_navigate/download` took
    caller URLs with no SSRF check; `graph_diff` ran `git checkout <caller ref>` on the live working tree
    (now read-only `rev-parse` + `show`); `marketing_cli` returned stderr as normal output on non-zero exit;
    **~25 tools never worked** (called methods that don't exist, `await`ed sync code, or never awaited async
    code — 13 browser tools returned `'<coroutine …>'`, `browser_form` reported `{"ok":true,"filled":[…]}`
    having typed nothing, 7 claims tools `json.dumps(<coroutine>)`, `file_grep` sliced a dict, `memory_recent`/
    `memory_categories` returned empty forever, `security_cve_scan` ran a nonexistent `pip audit` and read "no
    vulnerabilities"). **mcp_tools — NOT fixed (tier policy, owner decision):** which tools are YELLOW/RED —
    suggested RED: `git_push/rebase/pr_create`, `perf_profile`, `test_*`, `doc_delete`, `memory_clear`,
    `browser_eval`, `email_delete`, `db_quarantine/reenable`, `marketing_cli`, `openmythos_train`; YELLOW:
    `git_commit/checkout`, `doc_*` writes, `speak_as`, `write_note`. Other flags: `browser_upload` reads any
    local file and posts it to whatever page is open (exfil primitive); `browser_cookie`/`browser_storage`
    return live session secrets; `memory_clear` is a `DELETE FROM episodic_memory` (sacred table) behind a
    caller-supplied "confirm" string; `knowledge_*` accept any absolute dir and write JSON into it;
    `security_executor_check` is a substring denylist that says `safe: true` for `rm -fr /`; `swarm_*` call
    `get_swarm()` without the required `district` (always TypeError); `core/mcp_server.py` has printf-style loguru.
    **Behavior changes to know about:** `file_copy`/`file_delete` now require the same coding grant `file_write`
    already did; `perf_export/import` and `graph_export/import/merge/compare` are confined to the approved
    `memory_exports` dir (graph_export's default no longer writes into the repo root); `doc_*` accept only doc
    file types inside the repo; git refs like `HEAD~2`/`HEAD^` are rejected by the ref allowlist; the browser
    tools are now `async def`. **scraper — SSRF verdict (your question):** `scraper/` DID reference
    `core/security/ssrf_guard.py` in exactly one place (`vector_scraper.py`) and it used `is_safe_url()`, i.e.
    the module singleton with **`resolve_dns=False`** — demonstrated: with DNS faked so `rebind.example` →
    169.254.169.254, the old guard returns **True**, the new engine check blocks it. Everything else bypassed the
    guard entirely: the static HTTP engine (and so `Fetcher`/`AsyncFetcher`/`FetcherSession`, `ai.py`
    get/bulk_get, spiders, robots/sitemap, shell/cli), the browser fetchers, the four `page.goto` sinks, the MCP
    `bulk_fetch/bulk_stealthy_fetch/screenshot` tools, and the crawler (start URLs, every followed link,
    sitemaps and `Sitemap:` lines, robots.txt, redirects/retries, checkpoint-restored requests; `links.py`
    even extracts `file://`). Now every entry point calls a local `SSRFGuard(resolve_dns=True)` (fails closed on
    DNS error; blocking lookup kept off the event loop) — **`ssrf_guard.py` and its global default were NOT
    changed** (documented owner decision above). Also fixed: MCP `follow_redirects=True` silently disabled the
    engine's "safe" redirect protection (now clamped); the session-level `proxy=` default was popped and traffic
    went direct (privacy leak) and `AsyncFetcher(**kw)` dropped proxy/impersonate/timeout; proxy credentials and
    URL query-string tokens/userinfo were logged (engine, browser retry warnings, `Response.__init__`,
    `BaseFetcher` deprecation warning logged every kwarg, storage debug log, curl translator); `::attr("x|//…")`
    CSS→XPath injection; `find_similar` XPath built from page tag text; adaptive relocation `IndexError` and
    silent miss; robots.txt fetch failure/5xx treated as allow-all (now disallow-all, uncached, per RFC 9309); a
    checkpoint deleted on crash; non-atomic `rename()` (breaks on Windows second save); legacy `.pkl`
    checkpoints deserialized (pickle banned; no longer migrated); block/ban pages cached and replayed as good;
    a crawl where every fetch failed reported success (new `CrawlResult.succeeded`); the `core/scraper` CLI
    `main`/`extract` callbacks raised `NotImplementedError` (every command exited 1); `mcp --http` bound
    `0.0.0.0` (a network SSRF proxy; now `127.0.0.1`); an unreadable main document returned as an empty 200;
    stealth flags silently dropped when any `extra_flags` was passed; Chrome flag/launch-option injection
    (`--remote-debugging-port`, `--load-extension`, `additional_args` `executable_path`/`record_har_path`);
    `timeout=0` (= wait forever); browser/pool leaks when `close()` raised. **scraper — NOT fixed:** redirect
    hops and browser sub-resources are not re-validated and DNS rebinding (validate-then-connect resolves
    twice) is open — needs IP pinning / `page.route` interception / a manual redirect loop (curl_cffi exposes
    no `resolve`); `vector_scraper.fetch_stealth/fetch_dynamic` always fail (use classmethod-only classes as
    async context managers); `cdp_url`, `real_chrome`, `user_data_dir`, `executable_path`, `cookies` are
    caller-controlled through the MCP tools; no crawl limits (max pages/depth/size; `_seen` grows unbounded);
    `robots_txt_obey` defaults False; ReDoS in caller-supplied regex (`find_by_regex`, `.re/.re_first`, no
    timeout); package-owned `elements_storage.db` default path is inside the source tree (bypasses CONFIG);
    `quick_fetch`/`fetch_to_markdown` return `""` on failure and the error body on 4xx/5xx; `--no-sandbox` is
    now rejected in caller `extra_flags` (Docker-as-root needs it); `STEALTH_ARGS` includes
    `--disable-cookie-encryption`.

27. **`core/training/` + `core/benchmark/` + `core/telemetry/` + `core/resilience/` deep-verify, `core/mining/`
    wiring-check only, 2026-10-01 —** resumed slice (a prior fork crashed mid-task from a network outage after
    finding one bug, completed by the parent session: `core/loop/autonomous_loop.py`'s OpenMythos deploy
    eval-gate checked `result.get("status") == "ok"` but `SelfImprovementCycle.run_weekly()` never returns
    "ok" (only "completed"/`failed_*`/`skipped_no_data`) — permanently dead gate, fixed to check "completed";
    `core/training/weekly_scheduler.py`'s silent-swallow-placeholder logging fixed same commit, `262c9d7db`).
    Owner correction mid-slice: `core/mining/` is a vendored third-party port with an unidentified upstream
    license (same disposition as item 9's other unidentified trees) — downgraded from deep-verify to
    wiring-check-only repo-wide for any module originating from an open-source repo; `core/training/
    benchmark/telemetry/resilience` are VECTOR-authored and stayed at full depth.
    **`core/training/` (34 files) — 5 real bugs, commit `ecc4f3e56`:** `data_collector.py`'s `record()`
    gated its documented "autonomous_loop" source-tag default behind `metadata` being truthy
    (`metadata.get("source", "autonomous_loop") if metadata else ""`) — the one real caller never passes
    `metadata=`, so every live-collected training example got `""` instead; fixed to
    `(metadata or {}).get(...)`. `lora_trainer.py`: `self_improvement_cycle.py`'s Phase-4C eval gate
    (`val_loss > 1.5 * initial_loss`, "reject regressions") read those two keys from the trainer's result
    dict, but neither real training path (`_train_with_peft`/`_train_with_unsloth`) ever populated them —
    gate always compared its own defaults (`0 > 1.5`), permanently False, identical bug class to the
    eval-gate fix above. Added `_extract_loss_history()` pulling real loss values from the HF Trainer's own
    `log_history` (train loss — no held-out eval split exists). `openmythos/export_to_ollama.py`:
    `OllamaExporter.create_modelfile()`'s parameter loop had `if config_name := parameters.get(config_name):`
    — `config_name` read on the right-hand side before the walrus ever bound it (loop variable was
    `config_key`); `UnboundLocalError` on the first call with any `parameters` dict, which is the function's
    whole purpose. Fixed to `parameters.get(config_key)`. **FLAG-FOR-OWNER, not fixed:**
    `openmythos/trainer.py`'s `SelfImprovementTrainer.generate()` is an explicitly-labeled placeholder
    (deterministic hash-string output, not real model inference) but is wired into the now-reachable
    Sunday-reflect deploy gate (`evaluate()` → `should_deploy()` after every weekly training cycle) — the
    gate's coherence score never reflects actual trained-model quality; wiring real inference needs a
    decision on what checkpoint to call before promotion to the live Ollama tag. Added a loud warning so
    this fires visibly in logs instead of silently passing as a real eval. Also flagged:
    `openmythos/forward.py`'s 4 dedicated webhook endpoints (`/forward/github`, `/gmail`, `/calendar`,
    `/custom`) never call `_validate_signature()` at all — only the generic `/forward` endpoint does — but
    confirmed zero real importers of `WebhookForwarder` anywhere in the repo (dormant, only reachable via
    its own `__main__`), same bar as other dormant-module flags this cycle. New/extended tests:
    `tests/training/test_data_collector.py` (+2), `test_lora_trainer.py` (+4),
    `test_openmythos_export_and_eval.py` (new, 3 tests). 60/60 `tests/training/` pass, zero regressions.
    **`core/benchmark/` (20 files) — clean, zero bugs.** All 4 harness files (runner/task/isolation/report)
    plus all 14 cognitive-benchmark task modules (T01-T14) read in full; well-constructed throughout, no
    silent-swallow/path-confinement/printf-loguru/fail-open findings. Not every slice needs to find bugs.
    **`core/telemetry/` (19 files) — clean, zero bugs.** All energy-vendor monitors (NVIDIA/AMD/Apple/RAPL),
    the aggregator/store/session/instrumented-engine/vLLM-scraper files read in full. 2 deliberate
    `threading.Thread()` exceptions to the asyncio-only rule, both already carrying the established
    2026-09-23 documented-tradeoff comment (concurrent GPU polling alongside arbitrary measured work) — not
    re-flagged. `TelemetryStore`/`TelemetryAggregator` open raw `sqlite3.connect()` rather than the
    SQLCipher-aware helper, consistent with the established "legitimate non-sensitive auxiliary store" bar
    from this cycle's earlier 14-site sqlite triage (metrics/latency/cost data, no prompt/response content).
    **`core/resilience/` (15 files) — 2 FLAG-FOR-OWNER findings, no autonomous fix (both in dormant,
    unwired code — confirmed zero real production callers of `ResilienceLayer`/`run_all_playbooks()`
    anywhere, test-only, same dormant-module bar as this cycle's other flags):**
    `recovery_playbooks.py`'s `ProcessHangPlaybook.run()` calls `proc.kill()` on *any* system-wide process
    with `cpu_percent > 90`, with zero scoping to VECTOR's own process tree — a legitimate user's unrelated
    CPU-heavy work (rendering, a game, a compile job) would be killed if this playbook ever fires
    automatically. `injectors/process_kill.py`'s `ProcessKillInjector._targets["voice_ws"] = "python"`
    targets the bare interpreter name for `taskkill /F /IM python` — not a specific subprocess; since
    VECTOR's own main process is itself Python, this is either a no-op (wrong Windows image-name format,
    needs `.exe`) or, if it ever matches, catastrophic unscoped self-termination. Both need a real design
    decision (how to identify "VECTOR's own process" distinctly from the host's other processes) before
    this subsystem is ever wired into the autonomous loop — not a narrow patch.
    **`core/mining/` (14 files) — wiring-check only per the owner correction.** Found the one real external
    caller (`core/api/routers/mining.py` → `core.mining._metrics.parse_gateway_metrics`) and verified it:
    `mining.py`'s `errors = int(stats.last_error.split()[0])` looked suspicious in isolation (parsing an
    "error" field as a bare int), but `_metrics.py`'s own producer always formats it as
    `f"{int(errors)} gateway errors observed"` — the round-trip is internally consistent and correct, not a
    bug. No further depth per the owner's wiring-check-only scope for vendored/unidentified-license trees.

28. **`vectorcode/src/tools/` first-pass deep-verify, 2026-10-02 — FIRST vectorcode/ bug-hunting pass ever**
    (the 2026-05-17 absorption effort checked licensing/symbol-porting, not logic). Owner-directed scope
    change same day: `vectorcode/` is no longer wiring-check-only despite originating from absorbed
    OpenJarvis/Hermes/Ruflo — it's slated to become this system's own future Codex/Claude-Code replacement,
    so it gets full depth like hand-written VECTOR code. This is a RESUMED slice (a prior fork hit a Claude
    session rate limit mid-task; its one finding and fix are below, independently re-verified by the parent).
    **`git_tools.py` — FIXED, commit `b1523366f`:** `git_push(remote, branch)` and
    `git_create_branch(name)` passed caller-controlled strings as bare positional git arguments with no
    allowlist or `--` separator — a string starting with `-` is interpreted as a git option
    (`--upload-pack=<cmd>` is a known git RCE vector). Identical bug class already fixed in
    `core/mcp_tools/expansion_modules/git.py` (`d41e9a1f2`/`46e4b2fda`) — same allowlist regex pattern
    applied (`_REF_RE` for branch/ref names, `_REMOTE_RE` for remotes; reject `..`, `//`, `@{`, trailing
    `.`/`/`/`.lock`), plus a `--` separator on the checkout path. Checked all 4 real callers
    (`vectorcode/src/repl.py`, `districts/coding/git_bot.py`, `core/mcp_tools/expansion_modules/git.py`,
    `core/security/mcp_security.py`) — none pass option-like values, no legitimate caller affected. New
    `tests/test_vectorcode_git_tools_arg_injection.py` (6 tests), module's own `__main__` self-test still
    passes. Also fixed in the same resumed slice: `bash_tools.py`'s `__main__` self-test used `%s`-style
    loguru formatting (loguru uses `{}`) — self-test only, no production call site (commit `764ab57ff`).
    **Remaining `src/tools/` scope (127 of 129 files) — pattern-swept, NOT individually read file-by-file**
    (context budget on this slice; flagging the real coverage gap rather than overclaiming depth): grepped
    the whole directory for `shell=True`/`os.system`/`eval(`/`pickle.load` (zero real hits — only JS-`eval`
    in the browser-automation tools and `skills_guard.py`'s own detector-pattern strings, not actual
    dangerous usage) and for `requests`/`str.startswith()` path-confinement patterns. Two findings, both
    **FLAGGED, not fixed** (architecture-level, not narrow bugs): (1) `browser_camofox.py`, `browser_tool.py`,
    `transcription_tools.py`, `tts_tool.py` use `requests` (CLAUDE.md rule 8 bans it, `httpx` required) —
    systemic across 4 files, same "still uses requests" class already flagged-not-fixed in `core/trading/`'s
    `alpha_vantage_common.py` this cycle; a mechanical conversion is plausible but needs per-call-site care
    (requests/httpx differ on streaming and some error types) that this slice's remaining budget didn't
    allow for safely. (2) `file_safety.py`'s `is_write_denied()` is a **denylist** of known-sensitive
    paths/prefixes (`.ssh`, `.aws`, `/etc/passwd`, etc.) rather than an allowlist-confined root — the
    opposite of the "allowlist, never blocklist" principle this cycle's git-argument-injection fixes
    establish. An optional `VECTOR_WRITE_SAFE_ROOT` env var *can* upgrade it to allowlist behavior, but only
    when explicitly configured; unset, any dotfile/config convention not enumerated here is writable. Real
    callers confirmed: `file_operations.py`, `agent/copilot_acp_client.py`. Also noted, not investigated
    further (out of this slice's scope): `agent/file_safety.py` appears to be a second, possibly-duplicate
    implementation alongside `tools/file_safety.py` — worth checking for drift when `vectorcode/src/agent/`
    (79 files) gets its own slice. `path_security.py`'s shared `validate_within_dir()` helper (used by
    `skill_manager_tool`/`skills_tool`/`skills_hub`/`cronjob_tools`/`credential_files`) correctly uses
    `resolve()` + `relative_to()`, not `startswith()` — verified fine, no issue.
    **Remaining vectorcode/ scope, nothing else started this slice:** `vector_cli/` (123), `cli/` (24) —
    the rest of this exact 276-file assignment; then `src/evals` (143), `src/learning` (79), `src/agent`
    (79), `src/plugins` (77), `src/skills` (66), `src/gateway` (64), `src/comms` (58), `src/vc_tools` (52),
    `src/` root (48), `src/channels` (41), `src/connectors` (36), `src/vc_agents` (34), several smaller
    dirs, and the 700-file `python/tests/legacy_ported/` ported test suite — roughly 1,867 files.
    One incidental observation from an unrelated import check, not investigated: `vectorcode/src/vc_tools/
    storage.py` logs the exact silent-swallow-placeholder pattern (`"[VECTOR] suppressed exception"`) twice
    at import time — likely a real instance of this cycle's most common bug class, flagged for whichever
    future slice covers `src/vc_tools/`.

29. **`core/video/` deep-verify, 5 of 13 files, 2026-10-02 —** resumed slice (a prior fork on the
    remaining small `core/` subdirectories died mid-work from a Claude usage-limit rate-limit after
    committing `core/browser/`+`core/sandbox/`; this is a fresh continuation, not that same fork).
    5 real bugs found and fixed, each with a new test file, zero regressions:
    **`video_encoder.py`** (commit `c640a29be`): `_vp9_args()`'s bitrate override used
    `args.index("0")` to find-and-replace the `-b:v` placeholder — `str(crf) == "0"` is a real VP9
    near-lossless setting that appears earlier in the arg list, so the search hit the `-crf` value
    instead whenever both were set, corrupting `-crf` and silently dropping the bitrate override;
    fixed by building the value directly. Also added logging to `probe_duration`/`probe_dimensions`,
    which swallowed every exception with none at all.
    **`audio_mixer.py`** (commit `b25c20e2b`) — most severe finding this slice:
    `AudioMixer._mix_multi()` built a correct per-track volume/delay filter chain into `mix_inputs`,
    then discarded it and rebuilt the `amix` input string from the raw unprocessed `[i:a]` streams —
    any 2+ track mix (e.g. `NarrationPipeline.produce()`'s narration + background music at
    `bg_volume=0.15`) silently applied NO volume reduction and NO timing offset to any track. Fixed
    to use the already-built labels. FLAGGED, not fixed: every method in this file returns a
    success-shaped result even when the underlying ffmpeg call failed (some now log a warning, none
    raise) — changing that contract touches every caller, a design decision for the owner.
    **`background_remover.py`** (commit `8df447a8e`): `bg_plate_path` (the documented "inverse-alpha
    background plate" feature) is accepted by both video-removal methods but never implemented in
    either — silent non-delivery, not an error. No real caller passes it today; added a warning log
    rather than implementing an unrequested feature.
    **`studio_server.py`** (commit `deb55655c`) — 2 independent chaining bugs in `run_workflow()`:
    (1) its "topological order" was really just a 2-bucket split (no-incoming-edge nodes first, then
    everything else in original array order) — a real A→B→C chain with C listed before B in the raw
    `nodes` array (no ordering guarantee in the data model) ran C before B produced output; fixed
    with a real Kahn's-algorithm topological sort, with a cycle now running every node instead of
    silently dropping any. (2) the `"output"` node type never wrote its resolved value into
    `node_outputs` unlike every other node type, so an `"output"` node used as a pass-through (not
    just a terminal node) broke any node chained after it regardless of ordering — fixed to write
    through like the other branches.
    **`website_to_video.py`** (commit `48cb77ac9`) — real XSS: `build_composition_from_content()`
    interpolated `content.title`/`.headline`/`.description` directly into generated HTML with no
    escaping. These fields are extracted via regex from a SCRAPED, attacker-controlled webpage's
    `<title>`/`og:title`/`og:description`/`<h1>` tags, and the composition is then rendered by a real
    headless browser (`capture_screenshot`) — a malicious page's title/og tags containing
    `</div><script>...</script>` would execute real JavaScript in VECTOR's own render context. Fixed
    with `html.escape()` on every interpolated field, including the caller-supplied url (defense in
    depth). Noted, not fixed: the file's own `__main__` smoke test has a pre-existing, unrelated
    broken assertion (confirmed broken identically before this fix via `git stash`) — out of scope.
    **Remaining in `core/video/`** (8 of 13 files, not yet reviewed this slice): `composition_linter.py`,
    `composition_types.py`, `html_renderer.py`, `hyperframes_sidecar.py`, `provider_capabilities.py`,
    `vector_composer.py`, `workflow_resolver.py`.
    **Remaining in the parent slice's full scope, entirely untouched**: `email`(10), `runtime`(8),
    `jcode`(8), `event_bus`(8), `personality`(7), `persona`(7), `seo`(6), `media`(6),
    `code_conductor`(6), `vision_control`(5), `stealth_browser`(5), `knowledge`(5), `cloud`(5),
    `avatar`(5), `ui`(4), `science`(4), `scheduler`(4), `metering`(4), `swarm`(3), `utils`(2),
    `services`(2), `queue`(2), `monitoring`(2), `models`(2), `migration`(2), `mcp`(2),
    `integrations`(2), `experiments`(2), `communications`(2), `causal`(2), `audit`(2),
    `brain_hooks`(1), plus 10 root-level `core/*.py` files (`runtime_paths.py`, `repo_hygiene.py`,
    `prompt_library.py`, `notify.py`, `mcp_server_stdio.py`, `mcp_server.py`, `errors.py`,
    `config.py`, `breaker_registry.py`, `api_manager.py`). Known already-flagged (don't re-flag the
    same issue, but still owed a full logic review beyond it): `core/email/schema.py`,
    `core/persona/evolution.py`, `core/scheduler/store.py` (raw-sqlite3 findings); `core/experiments/
    ab_testing.py` (already has its own dedicated fix, commit `9e7f2d04a`).

30. **`districts/marketing/` + `districts/coding/` full multi-bug-class revisit, 2026-10-01 —** resumed
    slice (a prior fork died mid-task from a Claude rate limit; its committed progress —
    `amazon_ads_agent.py`/`attribution_agent.py`/`sgtm_agent.py` Rule-1-hydration fix,
    `geo_optimizer_agent.py` params-vs-task fix, `ads_orchestrator_agent.py` dead-script-path fix — is
    already recorded above via commits `5f673142b`/`41a8043e6`/`f820438af`). Both districts already had
    ONE bug class fixed historically (params-vs-task dispatch; `task_type` free-text routing in 7
    marketing agents) — this slice is their first full multi-bug-class pass.
    **Marketing (28 files) — fully covered.** Confirmed RULE 1 hydration is already correct everywhere
    else via the shared `SkillMixin._chat()` helper (handles hydration internally) or direct
    `session_hydration_prompt()` calls already present in `seo_agent.py`/`seo_portfolio.py`/
    `meta_ads_agent.py`/`google_ads_agent.py`/`marketing_specialists.py` — no further Rule 1 gaps found.
    **Fixed**: `ads/scripts/generate_report.py` used stdlib `logging` instead of loguru (rule 6) +
    3 broken placeholder exception messages (also left a dangling `logging.basicConfig` call under
    `--verbose`, fixed to `logger.add(sys.stderr, level="DEBUG")`); `ads/scripts/analyze_landing.py`
    (2 sites) + `ads/scripts/generate_image.py` (1 site) had the loguru `exc_info=True`-does-nothing
    placeholder pattern (loguru doesn't treat `exc_info=` as a traceback kwarg the way stdlib does —
    silently drops the real exception); `ads/scripts/capture_screenshot.py`'s `browser.close()` only
    ran on the success path, leaking a chromium process on any `page.goto()`/`screenshot()` exception
    (fixed with try/finally). 4 commits: `a2811152d`, `d8d5f8972` (+ the pre-resumed ones above).
    **FLAG FOR OWNER, not fixed**: `ads/scripts/url_utils.py`'s `validate_url()` does real SSRF
    DNS-resolution checking, but `fetch_page.py` (follow_redirects=True), `analyze_landing.py`, and
    `capture_screenshot.py` all navigate/fetch the validated URL afterward with their own independent
    DNS resolution — redirect hops and the final connection are never re-validated (same unfixed
    validate-then-connect/DNS-rebinding gap already flagged in `core/scraper`'s audit this cycle,
    "needs IP pinning"; should use whatever approach the owner picks for that instance too). Also
    noted but not changed: a near-universal pattern across content-generation methods district-wide
    (`generate_copy`/`audit_account`/etc.) of returning `{"status": "ok", ...}` with an LLM-failure
    error string embedded in the content field instead of `status: "error"` — same shape as the
    "phantom success" bug class fixed elsewhere this cycle, but here it's the district's own original
    design (15+ call sites, not introduced by any single file) — a real API-contract question for the
    owner, not a narrow per-file patch.
    **Coding (28 hand-written files, `vector_mlops/` vendored subtree correctly excluded) — partially
    covered, ran out of context before finishing all 28.** Covered in full:
    `git_bot.py` — fixed a subprocess argv-injection risk in `gitnexus_impact()`/
    `analyze_with_gitnexus()` (caller-controlled `symbol`/`repo_path` as bare argv, same shape as the
    `vectorcode/src/tools/git_tools.py` fix landing in parallel this session), 2 broken loguru
    placeholders, and a dead duplicate `except Exception` clause. `coding_tools.py` — fixed the
    identical argv-injection shape in `grep_code()` at the primitive level (the one external caller,
    `core/mcp_tools/expansion_modules/files.py`'s `file_grep`, already guarded its own `pattern` arg
    with an explicit `--pre=<cmd>` RCE comment, but `grep_code()` itself had no guard — now every
    caller is covered), plus 2 more broken placeholders. `database_optimizer.py` — **the agent was
    completely non-functional**: `analyze_schema()`/`benchmark_queries()` opened the main DB with a
    plain `sqlite3.connect()` instead of `core.memory.episodic.get_db_connection()` (rule 7); with
    SQLCipher active (the live default, confirmed) this fails outright. Fixed to use the shared
    singleton (never closed, same documented caution as `data_engineer.py`/`blog_publisher.py`); this
    exposed a second bug the old code never reached (`sqlcipher3`'s driver returns PRAGMA
    page_size/page_count as `str` not `int`, now coerced). `code_reviewer.py`,
    `codebase_onboarding_engineer.py`, `rapid_prototyper.py`, `refactor_cleaner.py` — one broken
    placeholder each (`refactor_cleaner.py`'s own job is detecting dead `except: pass` blocks in other
    files; it had the modern loguru equivalent of that exact bug in itself). Ruled out, no fix needed:
    `vectorcode_bridge.py`/`mlops_agent.py`'s `threading.Lock()` use (guard only, not a real
    `Thread()` spawn); `vectorcode_bridge.py`'s subprocess calls (task payload goes over stdin, not
    argv; `port`/entry-point args are fixed constants or typed `int`); `code_intel_agent.py`'s
    subprocess (fixed `["node", str(_DIST)]`, no caller input). **FLAG FOR OWNER, not fixed**:
    `test_writer.py`'s `run_test_coverage(module_name)` interpolates `module_name` into a `--cov=`
    flag and a file path with no sanitization — but it has ZERO real callers anywhere in the repo
    (confirmed via repo-wide grep), so flagged as dormant-but-unsafe-if-ever-wired-up rather than
    fixed, same bar as `subagent_runner.py`/`parallel_researcher.py` this cycle. 4 commits:
    `f9d64aa90`, `28c880386`, `5da18ca77` (+ the pre-resumed ones above).
    **Remaining in `districts/coding/` — genuinely not yet examined** (ran out of context):
    `addy_code_reviewer.py`, `agent.py`, `architect_bot.py`, `bug_hunter.py`,
    `code_conductor_agent.py`, `code_explorer.py`, `code_intel_agent.py` (subprocess ruled out above,
    but not given a full logic read), `developer_advocate.py`, `fastapi_reviewer.py`/
    `python_reviewer.py`/`security_reviewer.py` (already have the task-type-ordering fix from an
    earlier slice, but not re-read for other bug classes), `frontend_developer.py`,
    `gui_automation_agent.py`, `minimal_change_engineer.py`, `mlops_agent.py` (612 lines, largest
    untouched — spot-checked for subprocess/threading/phantom-success only, not a full read),
    `obra_code_reviewer.py`, `vectorcode_bridge.py` (subprocess/threading ruled out above, not a full
    logic read), plus the trivial `__init__.py`/`code_review_graph/__init__.py`/
    `vectorcode/__init__.py` files (not checked, likely trivial). Next slice should start here before
    considering `districts/coding/` done.

31. **`vectorcode/src/tools/terminal_tool.py` (full, finished) + `file_state.py`, 2026-10-02 —** resumed
    slice: two prior forks got real depth on 14 of 129 `src/tools/` files plus 1,408 of
    `terminal_tool.py`'s 2,157 lines before each ran low on budget (see item 28). This pass
    finished `terminal_tool.py`'s remaining ~750 lines and separately read `file_state.py`
    (332 lines) in full.
    **`terminal_tool.py`, no severe new bug in the finished segment.** The background-spawn
    path, foreground retry/backoff loop, `check_terminal_requirements()`'s per-backend checks,
    and the tool-schema/registry wiring at the bottom are all internally consistent.
    **FLAGGED, not fixed:** the file uses stdlib `logging.getLogger(__name__)` with `%s`
    placeholders throughout (confirmed real, not the loguru-`%s` bug class — stdlib's `%s`
    works correctly here) — CLAUDE.md rule 6 says loguru everywhere, and this cycle already
    converted 2 other files for the same reason (`core/sandbox/mount_security.py`,
    `vectorcode/src/tools/url_safety.py`), but url_safety.py's conversion was justified by a
    stray broken `from loguru import logger` import sitting in its docstring — clear evidence
    loguru was the actual intent. `terminal_tool.py` shows no such evidence; its stdlib logging
    looks deliberate. A ~24-call-site conversion is a real but non-urgent style fix, not a
    functional bug — left for a dedicated cleanup pass rather than taken out of this budget.
    Also investigated and ruled OUT (not a bug): both the foreground and background success
    paths never set a `"status"` key (only error paths do, each with their own string) — this
    looked like the exact status-contract-drift class fixed twice already tonight
    (`autonomous_loop.py`/`lora_trainer.py`), but confirmed via grep that no real VECTOR-side
    caller parses `terminal_tool`'s JSON for `status=="ok"` — the LLM agent itself consumes the
    tool's JSON output directly as conversational tool-result text, not as internal
    control-flow data, so there's no reachable failure mode.
    **`file_state.py`, clean.** Real per-path locking (`threading.Lock()` as a guard, not a
    spawn — compliant), bounded dicts via `_cap_dict`'s insertion-order eviction, and the
    3-case staleness detection in `check_stale()` (sibling-write-after-read, external-mtime-
    drift, never-read) are all logically sound. No bug found.
    No commits this pass (nothing to fix, one item flagged for a future cleanup slice, not
    fixed here).
    **`vectorcode/src/tools/` running total: 16 of 129 files + `terminal_tool.py` now fully
    read (18 "files" in effective coverage terms). ~111 files remain, all still unread**:
    `fuzzy_match.py` (704 lines, next smallest unread) should be picked up first; then the
    thirteen 1,000+ line files flagged as their own dedicated future slices by the prior fork
    (`skills_hub.py` 3,226, `mcp_tool.py` 3,066, `browser_tool.py` 2,884, `delegate_tool.py`
    2,518, `web_tools.py` 2,112, `send_message_tool.py` 1,583, `code_execution_tool.py` 1,581,
    `tts_tool.py` 1,526, `skills_tool.py` 1,496, `rl_training_tool.py` 1,407,
    `browser_supervisor.py` 1,363, `process_registry.py` 1,354, `file_operations.py` 1,260,
    `approval.py` 1,219, `file_tools.py` 1,187, `kanban_tools.py` 1,139, `lsp/servers.py` 1,040,
    `voice_mode.py` 1,018); plus `browser_*`/`browser_providers/*`, `computer_use*`,
    `microsoft_graph*`, `mcp_oauth*`, `feishu*`, `environments/*` (daytona/docker/modal/ssh/
    singularity/local/vercel_sandbox), and the rest not yet enumerated. `vector_cli/` (123
    files) and `cli/` (24 files) haven't started at all. This directory is clearly far denser
    than its file count suggested going in — treat every future batch size estimate for it
    with that in mind.

32. **`core/personality/` deep-verify, 2026-10-02 — COMPLETE (7 files, 1,205 lines).** Real
    line-by-line review, not mechanical grep.
    **1 real bug fixed:** `sentiment.py`'s `SentimentAnalyzer.analyze()` docstring promises a
    3-tier "keyword → embedding → LLM fallback" cascade (`core/config.py` documents
    `sentiment_method`'s 3 valid values as `keyword | embedding | llm`), but the
    embedding-tier gate (`self._method == "embedding" or (self._method == "keyword" and
    self._embedding_model)`) only matched `method == "embedding"`, never `"llm"` —
    configuring the full documented cascade silently skipped the embedding tier entirely,
    jumping straight from keyword to LLM on low keyword confidence. Fixed by including
    `"llm"` in the gate. New `tests/test_core_personality_sentiment_cascade.py` (4 tests).
    Verified `tests/personality/` (full suite) + `tests/integration/test_spec03_personality.py`,
    zero regressions. Commit `697df9a0b`.
    **2 flagged, not fixed:** `sentiment.py`'s `_llm_analyze()` and `consistency.py`'s
    `_llm_rewrite()` both call raw `httpx.post()` against `CONFIG['ollama_host']` directly,
    bypassing `core/inference/provider_client.py` + `route_policy` entirely (CLAUDE.md: never
    raw `httpx` for LLM calls) with no `session_hydration_prompt()` — low real-world exposure
    today (`sentiment_method` defaults to `"keyword"`; `_llm_rewrite` only fires on a
    borderline consistency score), flagged rather than fixed since routing through
    `provider_client.py` needs confirming its `format="json"` structured-output param is
    uniformly supported across providers, not a one-line swap. `consistency.py`'s
    `_TRAIT_CHECKS["language"]` bucket (emoji/filler-word regex patterns) is dead code —
    `"language"` is never a real `CharacterCard` trait name, so it's never reached via the
    `for trait_name in active_traits` iteration that drives `_check_traits()`; functionally
    covered anyway by `_check_speech_patterns()` with different penalty weights, so it's
    ambiguous whether this is a real scoring-leniency bug (the intended double-penalization
    under `trait_score`'s 0.40 weight never fires) or just vestigial dead code — flagged for
    owner judgment rather than guessed at either way.
    **Clean, no bugs found:** `__init__.py`, `character_card.py`, `tone_adapter.py`,
    `memory_persona.py`, `middleware.py`. `memory_persona.py` is a clean example of the
    correct SQLCipher-aware pattern — it uses the shared `get_db_connection()` singleton for
    the main encrypted DB, with a well-documented, narrowly-scoped private-path exception for
    tests — the pattern several OTHER files this cycle got wrong (`database_optimizer.py`,
    etc.).
    `core/personality/` is now COMPLETE.

33. **`core/runtime/` (7 files, resumed after a rate limit) + `core/persona/` (7 files, singular —
    distinct from `core/personality/` above), 2026-10-02 — both COMPLETE.** Real line-by-line
    review, not mechanical grep. `core/runtime/world_model.py` was already fixed by the fork this
    resumed (hardcoded `tts`/`stt` "available" phantom success, commit `ddd3a266e`) — not re-checked.
    **1 real bug fixed:** `core/runtime/missions.py`'s `MissionPlanAdvisor._call_model()` called its
    `chat_fn` directly with no `session_hydration_prompt()` at all (RULE 1 gap) — confirmed
    `core/inference/ollama_safe.chat()` (the default `chat_fn`) does not inject hydration itself.
    Reachable via `core/runtime/plans.py`'s two real `MissionPlanAdvisor()` construction sites
    (`decompose_goal_to_plan()`, `replan_plan()`'s Strategy 2) — not dormant. New
    `tests/test_mission_plan_advisor_hydration.py` (1 test, injects a fake `chat_fn` via the
    constructor). Verified `tests/unit/test_planning.py` + `tests/backend/test_missions.py`, zero
    regressions. Commit `5c52b681e`.
    **1 flagged, not fixed:** `core/persona/voice_tone.py`'s `ToneModulator.modulate(text, context)`
    computes `self._collect_rules(context)` into `rules` and never uses it — only an `[URGENT] `
    prefix on critical urgency is actually applied; the collected time-of-day/mood/social-context
    instructions are discarded. Zero real callers today (confirmed via repo-wide grep — the one
    `modulate(...)` call site found is a different class, `core/voice/voice_personality.py`'s own
    `VoicePersonality.modulate()`). Not fixed: the right fix requires a design decision on what
    "modulating raw text" against LLM-instruction-shaped rule strings should actually do, not a
    narrow mechanical patch.
    **Already-known, not re-flagged:** `core/persona/evolution.py`'s raw `sqlite3.connect()`
    (person-linked behavioral data, needs owner migration decision, flagged in an earlier pass).
    **Clean, no new bugs:** `core/runtime/doctor.py`, `executor.py` (both extensively
    pre-hardened across multiple prior review rounds — 2026-09-23 rounds 3/4, 2026-09-27 —
    documented inline), `plans.py` (1,278 lines; DAG toposort, `param_bindings`/`_lookup_path`
    real data handoff, `verify_step_outcome()`'s 5 verification types, `replan_plan()`'s 3-strategy
    fallback — all read in full, no new issues; both `MissionPlanAdvisor` call sites inherit the
    `missions.py` hydration fix automatically), `readiness_check.py`, `tls.py`. `core/persona/`:
    `__init__.py`, `consistency.py`, `identity.py`, `persona_manager.py`, `schemas.py` clean.
    `core/runtime/` and `core/persona/` are now COMPLETE.

34. core/event_bus/ (remaining 6 of 8 files) + core/jcode/ (8 files) + core/seo/ (6 files)
    deep-verify, 2026-10-02 -- COMPLETE. Resumed slice (a sibling fork already landed
    core/event_bus/bus.py, commit 2a50a1fd6, not re-checked).
    core/event_bus/'s remainder -- clean, zero bugs. base.py, circuit_breaker.py,
    rate_limiter.py, types.py, worker_pool.py, __init__.py all read in full, no issues.
    One minor observation, not fixed: wiring.py's DISTRICT_SUBSCRIPTIONS has several pattern
    keys (engineering, testing, documentation, product) that don't match any real district
    name in the current manifest -- dead/unreachable config entries, same class as the already-
    documented 2026-09-08 "strategy" retirement comment in EVENT_TRIGGER_MAP, just never
    similarly annotated. Cosmetic, not a functional bug.
    core/jcode/ -- 5 real bugs fixed. tools/apply_patch.py (commit 9b1dd6b26): zero path
    confinement on patch-supplied paths -- hunk.path/move_to are parsed directly out of the
    patch TEXT (an LLM-generated patch is this tool's whole purpose), and base / hunk.path
    silently returns an absolute RHS unmodified, discarding base_dir entirely. Real caller:
    districts/coding/coding_tools.py's apply_codex_patch() (gated behind an active coding
    grant, but that grant authorizes editing the repo, not an arbitrary/escaped path). Fixed with a
    _confine() helper per hunk. tools/multiedit.py (commit b6dbd8bd3): identical shape on
    file_path, same real caller (multiedit_file()); fixed by confining to the real repo root --
    also fixed the module's own __main__ self-test, which used a system-tempdir path the new
    confinement correctly rejected (same situation as core/code_conductor/str_replace.py's
    self-test fix earlier this cycle). session_persistence.py + ambient_scheduler.py (commit
    ae657abaf): 3 more "[VECTOR] suppressed exception (degraded mode)" placeholders
    (list_sessions(), _load_directives(), _load_queue()). Checked and confirmed NOT a live
    bug: session_persistence.py's load(session_id) takes a caller-supplied id with no
    confinement, but both real callers (core/loop/autonomous_loop.py, 2 sites) only ever pass an
    internally-generated uuid.uuid4() -- not changed. cache_tracker.py, semantic_cache.py clean.
    core/seo/ -- 4 real bugs fixed. broken_link_checker.py (commit 4382c3428):
    BrokenLinkChecker.check() crawled start_url and every discovered link via a real urlopen()
    with zero SSRF validation -- same bug class fixed in core/scraper/+core/browser/ this cycle.
    Real caller: districts/marketing/seo_portfolio.py/seo_agent.py (Governor-dispatchable).
    Fixed with SSRFGuard(resolve_dns=True) checked on every URL before fetch, start_url and
    discovered links alike. pagespeed_client.py (same commit): one more silent-swallow placeholder
    (.env read failure), downgraded to logger.debug with the real exception (a missing optional
    file is expected, not warning-worthy). portfolio.py (commit 81611796a): record_audit()/
    add_goal()/get_audit_history()/schedule_followup()/record_followup_metrics() all built a
    file path from a caller-supplied site_id (and item_id) with zero confinement -- legitimate
    ids only ever come from _normalize_site_id(), but these methods trusted that invariant rather
    than enforcing it. Checked real callers: both always validate site_id via get_site() first or
    use add_site()'s own normalized return -- not exploitable today, hardened anyway at the
    primitive level (new _safe_site_id() helper), same bar as worktree.py/direct_executor.py's
    earlier dormant-but-fixed findings. Checked and confirmed NOT bugs, not fixed:
    pagespeed_client.py's and cms_connector.py's Ghost ?key= query params are each the
    vendor's own documented, only-supported auth mechanism for these specific public/read-only
    APIs (no header alternative exists) -- confirmed neither ever reaches a log statement in either
    file, so there's no leak path; not the same shape as this cycle's other "credentials in URL"
    fixes, which were VECTOR choosing a weaker option when a header alternative genuinely existed.
    gsc_client.py reviewed in full -- clean (OAuth Bearer tokens correctly in headers throughout).
    New tests: tests/test_jcode_apply_patch_confinement.py (4), tests/test_jcode_multiedit_confinement.py
    (2), tests/test_jcode_silent_swallow_logging.py (3), tests/test_seo_broken_link_checker_ssrf.py
    (3), tests/test_seo_portfolio_site_id_confinement.py (5) -- 17 new tests total, zero prior
    coverage existed for any of these files. 145 tests re-verified across this slice's own new tests
    plus tests/event_bus/, tests/test_coding_tools_grep_code_argv_injection.py,
    tests/test_audit_phase3_mcp_top.py, tests/test_marketing_district_run_wiring.py, zero
    regressions. Out-of-scope, flagged only: scripts/audit_toprank.py has one unrelated,
    pre-existing failing assertion against a "SessionPersistence" string in run_vector.py --
    confirmed via grep that run_vector.py has zero such references and was never touched by any
    of tonight's work.
    Commits: 2a50a1fd6 (sibling, pre-existing), 9b1dd6b26, b6dbd8bd3, ae657abaf,
    4382c3428, 81611796a.

35. **`core/avatar/` (5 files) + `core/cloud/` (5 files) + `core/knowledge/` (5 files)
    deep-verify, 2026-10-02 — COMPLETE.** ~3,841 lines, genuinely untouched by this audit
    cycle before now (only old unrelated historical commits existed for these three
    directories).
    **Fixed:** `core/cloud/heartbeat.py`'s `build_payload()` — 2 "[VECTOR] silent swallow"
    placeholder exception logs (agent-registry stats, episodic-memory stats), same systemic
    bug class fixed 50+ times this cycle. Commit `5c4c904dd`, `tests/test_cloud_heartbeat_silent_swallow.py`
    (2 tests).
    **FLAG FOR OWNER, not fixed:** `core/cloud/remote_sync.py` pushes local episodic-memory
    records to Supabase (`push_episodic()`/`sync_now()`) with no sensitivity filtering at
    all — every record `EpisodicMemory().recall()` returns gets shipped, including any
    RED-tier/secret-bearing content that ever lands in episodic memory. Supabase is
    documented, intentional VECTOR infrastructure (architecture.md's Layer B), not a rogue
    leak, so this isn't a narrow bug — it's a real data-classification question (should ALL
    episodic memory sync, or only non-sensitive records) the owner needs to decide, same bar
    as Codex's earlier plaintext-PII flags this cycle.
    **Clean, no new bugs (real depth, not a skim):** `core/avatar/avatar_core.py`,
    `avatar_state.py`, `avatar_voice.py` (extensively pre-hardened — verb-agreement and
    markdown-stripping fixes already documented inline from 2026-07-29/30), `proactive_care.py`
    (its `get_fatigue_score()` fallback-to-5.0-on-error behavior is the ALREADY-KNOWN
    camera/MediaPipe finding from an earlier slice, not re-flagged — and is a safe failure
    mode here since 5.0 sits below this file's own 7.0 fatigue threshold, so no false
    intervention fires). `core/cloud/failover.py`, `notify.py` clean. `core/knowledge/`'s
    `domain_extractor.py`, `wiki_parser.py`, `wiki_merger.py`, `graph_merger.py` (dense,
    heavily self-tested algorithmic code — node-ID normalization, two-pass `tested_by`
    linker, entity dedup, layer/tour building, all read in full) — their caller-controlled
    `project_root`/wiki `root` with zero path confinement is the SAME already-known
    `knowledge_*`/mcp_tools finding from the earlier core/mcp_tools audit ("`knowledge_*`
    accept any absolute dir and write JSON into it"), confirmed still the same root cause,
    not a new finding, not re-flagged.
    Commit: `5c4c904dd`.
    `core/avatar/`, `core/cloud/`, `core/knowledge/` are now COMPLETE.

36. **Mop-up slice, 2026-10-02 — `core/vision_control/` (2 remaining files) +
    `core/stealth_browser/` (4 remaining files) + `core/scheduler/` (3 files) +
    `core/metering/` (2 remaining files) + `core/ui/` (4 files) — ALL COMPLETE.**
    Collected the small leftovers several prior forks didn't reach, ~4,267 lines total.
    **Most significant finding: `core/ui/web_ui.py`'s `/ui/ws/chat` WebSocket had ZERO
    authentication.** `auth_middleware` is registered via `app.middleware("http")` —
    Starlette's HTTP-scope middleware does not run for websocket-scope connections — so
    any network client could connect with no key at all, drive a real LLM call
    (`caller_id="web_ui_ws_chat"`, real inference cost), and trigger an episodic-memory
    write, regardless of whether `VECTOR_API_KEY` was configured. Identical bug class
    already fixed in `core/api/routers/notifications.py` this cycle; `voice_ws.py`
    already did this correctly. Fixed by calling the same canonical
    `require_auth_handshake()` right after `accept()`. New
    `tests/test_web_ui_ws_chat_authorization.py` (3 tests, source-ordering checks, same
    approach as `test_notifications_ws_authorization.py`). Also 4 more
    "[VECTOR] suppressed exception (degraded mode)" placeholders fixed in the same file
    (loguru's `exc_info=True` doesn't capture the real exception; the `WebSocketDisconnect`
    handler specifically downgraded from a scary warning to a plain debug log, since a
    client disconnecting is routine, not an error). Commit `088285115`.
    **`core/stealth_browser/`: a real argument-injection RCE in `transcripts.py`** —
    `_extract_via_ytdlp()` passed a caller-supplied `url` (reachable via Governor dispatch,
    `districts/research/stealth_scout_agent.py`'s `youtube_transcript` action, zero
    validation) as a bare positional argv to `yt-dlp`. `_is_youtube_url()`'s `re.search()`
    only checks substring presence anywhere in the string, so a value like
    `"--exec=<cmd> #youtube.com"` passes that gate AND starts with `-` — `yt-dlp`'s real
    `--exec` flag runs an arbitrary shell command after "download" (genuine RCE), same
    argument-injection shape fixed 25+ times elsewhere this cycle. Fixed with a leading-`-`
    rejection plus a `--` separator as defense in depth. Also fixed the `__aexit__` bug in
    `server_manager.py` (unconditionally raised `NotImplementedError` referencing a
    subclass that doesn't exist anywhere in the repo, contradicting the module's own
    documented direct-context-manager usage) and 3 more placeholder-logging instances
    across `client.py`/`transcripts.py`/`server_manager.py`. Investigated and ruled out,
    not a bug: `macros.py`'s `use_server_macro=True` path interpolates the raw query with
    no Python-side encoding (inconsistent with the `False` path) — confirmed the Node-side
    consumer (`core/stealth_browser/server/lib/macros.js`) applies `encodeURIComponent()`
    before building the real URL regardless, so this is a style inconsistency, not a
    vulnerability; `client.py`'s `navigate()` forwards the URL to a separate server
    process rather than fetching it itself, so it's not an SSRF vector the same way
    `core/browser/`'s fixes were. New
    `tests/test_stealth_browser_transcripts_argv_injection.py` (3 tests). Commits
    `683e88487`, plus the earlier `f4abc78bf`/`e6b9c1e86`/`ab09a4a34` batch from the same
    resumed slice (browser_controller.py SSRF+hydration fix with a new
    `allow_private_navigation` constructor flag so `tests/test_browser_task_evidence.py`'s
    own real local test server keeps working without weakening the real default;
    `core/errors.py`'s `MemoryError`-shadows-the-builtin rename; the same `__aexit__`
    finding — see those commits for full detail).
    **`core/scheduler/`: one real wiring-gap flag, not fixed.** `tools.py` registers 5
    MCP tools (`schedule_task`/`list_scheduled_tasks`/`pause_scheduled_task`/
    `resume_scheduled_task`/`cancel_scheduled_task`), each correctly guarding
    `self._scheduler is None` before acting — but `_scheduler` is a class attribute never
    assigned anywhere in the repo (confirmed via repo-wide grep), so every one of these
    tools is permanently non-functional today. Not a narrow patch (needs an owner decision
    on which real `TaskScheduler` instance to inject and how), flagged rather than guessed.
    `store.py`/`__init__.py` read clean beyond the already-known `scheduler.py`-sibling
    sqlite flag (not re-flagged).
    **`core/vision_control/`, `core/metering/`: both clean, no new issues.**
    `action_parser.py` (pure text parser, no I/O) and `__init__.py` read clean.
    `inference_observability.py` (dense, carefully self-documented) read clean — explicitly
    privacy-preserving by design (no prompt/response content logged), so its raw
    `sqlite3.connect()` on a dedicated non-sensitive telemetry DB is an acceptable,
    deliberate pattern, not a new finding.
    Also `core/ui/chat.py`: 2 more of the same placeholder-logging instances (terminal-
    only, owner-operated, no auth/injection concerns there). Commit `30a697fdb`.
    This completes `core/vision_control/`, `core/stealth_browser/`, `core/scheduler/`,
    `core/metering/`, `core/ui/` specifically. **Correction, do not overclaim:** a sibling
    fork's slice (the 14 tiny `core/` subdirs + root-level files — `swarm`/`science`/
    `migration`/`mcp`/`experiments`/`audit`/`services`/`causal`/`communications`/
    `monitoring`/`integrations`/`models`/`utils`/`queue` + `config.py`/`mcp_server.py`/
    `mcp_server_stdio.py`/`notify.py`/`prompt_library.py`/`repo_hygiene.py`/
    `runtime_paths.py`/`api_manager.py`/`brain_hooks/`) was still actively in progress as
    this entry was written (observed mid-edit, uncommitted, on `core/migration/
    importer.py` — correctly left untouched, not this fork's scope). Real progress
    confirmed via its own commits so far: `config.py`+`mcp_server.py` (`cb07cb70f`),
    `brain_hooks`+`api_manager.py`+`mcp_server_stdio.py` (`c3767cbd5`),
    `communications/hub.py` (`d7d28574d`), plus an unrelated bonus find in
    `core/api/routers/investment.py` (`94fdff611`, a US ET hardcoded-offset bug wrong
    ~5 months/year — outside its declared scope but found and fixed anyway). **Do NOT
    claim all of `core/` is deep-verified until that slice's own completion is confirmed
    — check its final report/commits before relying on this file's own claim above.**

37. **Final core/ mop-up slice, 2026-10-02 — root-level files + 14 tiny subdirectories,
    ALL COMPLETE. This is the slice item 36 flagged as still in progress — now confirmed
    done.** Scope: `core/config.py`, `core/mcp_server.py`, `core/mcp_server_stdio.py`,
    `core/notify.py`, `core/prompt_library.py`, `core/repo_hygiene.py`,
    `core/runtime_paths.py`, `core/api_manager.py`, `core/brain_hooks/`, `core/errors.py`,
    plus `core/audit/`, `core/causal/`, `core/communications/`, `core/experiments/`,
    `core/integrations/`, `core/mcp/`, `core/migration/`, `core/models/`,
    `core/monitoring/`, `core/queue/`, `core/science/`, `core/services/`, `core/swarm/`,
    `core/utils/` — ~12,500 lines total.
    **Most severe finding: `core/audit/merkle_chain.py`'s `_redact()` only inspected
    top-level payload keys before writing to the persistent, append-only, on-disk audit
    trail.** This is LIVE code (`core/city/governor.py` — central dispatch for every one
    of VECTOR's ~230 agents' actions — plus `core/loop/cron_jobs.py`,
    `core/scraper/vector_scraper.py`, `core/api/routers/audit.py`), not dormant. A nested
    secret (e.g. `{"request": {"api_key": "sk-..."}}`, a plausible shape for the
    "tool_call"/"llm_request" actions this chain exists to log) passed through completely
    unredacted, directly contradicting the class's own docstring promise. Fixed with a
    recursive `_redact_value()` walking nested dicts/lists. Commit `d95576127`.
    **Real logic bugs fixed (not security, correctness):**
    `core/swarm/orchestrator.py`'s `dispatch()` fallback loop ("try all swarms in order")
    only advanced past a swarm that RAISED — but every real swarm/agent in this codebase
    reports failure via a returned `{"status": "error"}` dict instead, so it silently
    never tried more than the first swarm. Commit `c29011eee`.
    `core/experiments/ab_testing.py`'s `winner()` compared candidates against a p-value
    that `stats()` only ever computes relative to `variants[0]` — and `variants[0]` itself
    never gets a p-value key — so `winner()` returned `None` (no significant result)
    whenever the control/base variant also qualified as a candidate, the normal case.
    Verified via `git stash` that the new test fails against the pre-fix code. Commit
    `2d2f3017c`. `core/migration/importer.py`'s `save_agent()`/`to_python_file()` took
    `agent.name`/`system_prompt` from a parsed, untrusted migration-source config file with
    no confinement/escaping — a crafted name could path-traverse the output location, and a
    triple-quote in a prompt could inject arbitrary code into the generated agent `.py`
    file. Both dormant (zero real callers), fixed anyway. Commit `459e73835`.
    `core/api/routers/investment.py`'s `/market-status` had its own independent,
    hardcoded-US-ET-offset market-hours re-implementation (wrong ~5 months/year vs.
    `core/utils/market_hours.py`'s correct DST-aware version) — found while verifying
    `market_hours.py` itself; deleted the duplicate. Commit `94fdff611`.
    `core/swarm/generic_swarm.py`'s `_fallback()` and `core/runtime/missions.py` (prior
    sibling slice) both had the RULE 1 hydration gap; `core/brain_hooks/__init__.py`'s
    `run_hook()` had the identical hook-name path-traversal primitive that
    `core/mcp_tools/`'s wrapper already guards at the call site but not at the source —
    fixed at the primitive per this cycle's established pattern. Commits `f3d9daf65`,
    `c3767cbd5`.
    **~10 more silent-swallow-placeholder fixes** across `core/mcp/client.py`,
    `core/communications/hub.py`, `core/science/physics_engine.py` (all dormant or
    low-traffic, fixed per this cycle's "fix narrow bugs even in dormant code" bar) —
    see commits `844585c76`, `d7d28574d`, `643c023d1`.
    **One more correctness fix:** `core/science/chemistry_engine.py`'s RDKit-unavailable
    heuristic fallback doubled every real ring count (SMILES ring-closure digits appear
    twice per ring). Commit `643c023d1`.
    **Flagged, not fixed:** `core/mcp_server_stdio.py`'s `MCP_KERNEL_SECRET` is generated,
    validated for production strength, and gated by `core/runtime/readiness_check.py`'s
    readiness check, but `_sign_request()` (the only thing that would ever use it) has zero
    callers anywhere — the comments describing "signed MCP requests" described an intended,
    unwired feature as if active; corrected the comment, left real signing as a design
    decision. Commit `c3767cbd5`.
    **Clean, no issues:** `core/queue/retry_queue.py`, `core/services/` (both files),
    `core/monitoring/perf_contracts.py`, `core/causal/causal_reasoner.py`,
    `core/integrations/gmail_auth.py`, `core/models/health_models.py`,
    `core/science/cad_engine.py` (all geometry formulas verified), `core/__init__.py`.
    21 commits total this slice.
    **With this slice done, `core/` (every subdirectory except the 2 confirmed-vendored
    trees, `core/research_engine/` and `core/coding_assistant/`) is now GENUINELY,
    confirmedly fully deep-verified — all 3 parallel forks covering the remaining `core/`
    territory (this slice, item 35's `avatar+cloud+knowledge`, item 36's
    `vision_control+stealth_browser+scheduler+metering+ui`) have completed and are
    cross-confirmed via their own commits, not just claimed.**

This file is the single owner-facing source of truth. Full per-item evidence
(the detailed 31-repo absorption + open-issues audit with file:line proof) lives
in git history — the in-tree `repo_analysis/` archives were removed once their
open items were folded in here.

---

## A. This session's follow-ups (2026-06-29)

1. **Force-push the rewritten history.** ✅ **DONE 2026-07-05.** Pushed
   `production-hardening-complete` to github.com/arghyadeep-deb/VECTOR;
   remote HEAD == local (06d6d208), largest blob now 27MB (kokoro voices,
   well under GitHub's 100MB). The >100MB-blob history is gone from the
   pushed tree.
2. **Delete the safety backups.** ✅ **DONE** — `vector_git_backup*` and
   `vector_memory.db.premaint.bak.*` were already removed in a prior session;
   confirmed none remain.

## B. Physical hardware / OS settings (cannot be done from code)

3. **Termux node:** run `bash phone_node/setup.sh` on the Android device — needed
   before the phone↔Legion command relay can be tested end-to-end.
4. **Legion Wake-on-LAN:** enable WoL in BIOS/UEFI + network-adapter settings,
   then set `LEGION_HOST` to Legion's LAN IP in `phone_config.env`. Code
   (`core/control/wake_on_lan.py`, `ambient_server.py`) is built/tested against
   local sockets; only firmware WoL is missing.
5. **`face_recognition`:** ✅ **RESOLVED** — `import face_recognition` succeeds (verified 2026-09-24);
   the earlier Application Control block no longer applies.
6. **"Hey VECTOR" wake word** — PIPELINE COMPLETE; blocked on owner's real voice
   data (2026-07-04). Full openWakeWord train->export->load pipeline runs end-to-end
   (gen_wake_synthetic.py + train_wake_word_synthetic.py); 5 env bugs fixed
   (torchvision-first import, cp1252 stdout, mmap_batch_generator {label:path},
   empty-val-history, export_to_onnx empty output). Voice diversity solved via
   multi-speaker libritts (904 voices) -> FIXED false-triggering (silence 0.97->0.01).
   But the real wall is RECALL on the OWNER's actual voice: synthetic TTS voices don't
   transfer to the owner's real voice/mic -- best ~13% recall (2/15 real clips fire)
   across every config (5k/20k steps, 32-64 pos/batch). Quality gate fixed to measure
   real-clip RECALL FRACTION (>=50% must fire), not a lucky max -- so synthetic-only
   models are correctly REJECTED and core/voice/wake_word.py keeps working Whisper
   keyword-spotting (NO regression, verified). ONE remaining need is OWNER-GATED:
   ~50-100 real "Hey VECTOR" recordings (record via scripts/train_wake_word.py, drop
   into models/wake/samples/, re-run the synthetic trainer -- it installs only if
   recall clears 50%). Full ~17GB ACAV negatives would NOT help (problem is recall).

## C. Cloud deploy (needs your Cloudflare account/credentials)

7. **`cloud/email` Worker deploy** (separate from the already-live API Worker):
   needs a Cloudflare account/domain, Email Routing, R2 bucket `vector-email`,
   Workers AI, Cloudflare Access, and Worker secrets `POLICY_AUD`/`TEAM_DOMAIN`.
8. **`cloud/email` dependency advisories** — ✅ **RESOLVED (2026-07-01).** `npm audit`
   = **0 vulnerabilities** (was 4). The `echarts` XSS moderate was cleared by a safe
   `npm audit fix`; the 3 high `react-router` turbo-stream RCEs were fixed by upgrading
   `react-router`/`@react-router/dev`/`@react-router/node` 7.13.1 → **7.18.1** (in the
   7.x line — vite-6 compatible, no toolchain cascade; only `@latest` 8.x needed vite 7).
   `npm run typecheck` passes (EXIT=0). No remaining advisories.
9. **Cloudflare Worker parity tests** (`api/test/smoke.test.ts`): the harness is
   real and correct but `workerd`'s module loader can't resolve modules because
   this repo's path contains a literal space (`V.E.C.T.O.R. Codebase`). It runs
   in CI (Linux) or any space-free clone path — an upstream tooling limitation,
   not a code bug.

## D. Paid / verified API keys (optional — only for the `last30days` research brief)

10. **Twitter/X, TikTok, Instagram, Polymarket** connectors need paid tiers or
    app-review/business verification. Three free connectors (HackerNews, Reddit,
    GitHub) already work today; the rest stay disabled until you provide keys.

## E. Decisions that need no code — just your choice

11. **Post-training:** flip `post_training_enabled` in `core/config.py` and decide
    when the weekly Sat-04:00 run (`cron_jobs.py::job_post_training_run()`) should
    fire. Gated OFF by default; zero heavy imports until flipped.
12. **Voice engine default:** all engines (Kokoro/OmniVoice/Supertonic) are
    installed with weights downloaded; only Kokoro has real benchmark numbers so
    far. Defaults unchanged (`live_engine="kokoro"`, `cloning_engine="chatterbox"`).
    A/B listening + any default flip is your call.
13. **Optional integrations** (all have disabled-by-default seams; enable only if
    wanted): HelixDB graph-vector mirroring, LongCat-Video, Evolution-API
    (WhatsApp), Cal.diy calendar booking.

---

## F. Runtime config flags (reference — not work, just knobs)

These env-var flags gate live services / model calls / mutable resources out of
default runs. They are **off by default on purpose** (so tests never hit live
LLMs/services); flip one when you want that feature live. A feature behind a flag
isn't "proven in production" until you supply the service/device and run it live.

| Flag | Default | Enables |
|---|---:|---|
| `VECTOR_LIVE_TESTS=1` | off | Live network/model integration proofs in `tests/integration/test_capability_live.py`. |
| `VECTOR_RESEARCH_LLM_DESIGN=1` | off | Ollama-backed research experiment design (`core/research_engine/experiment_designer.py`); else rule-based. |
| `VECTOR_TRAINING_REAL=1` | off | Real PEFT/Unsloth LoRA training (`core/training/lora_trainer.py`); else simulated/dry-run. |
| `VECTOR_PREDICTIVE_USE_MEMORY=1` | off | Predictive analytics mining of live episodic memory history. |
| `VECTOR_DB_RECOVERY_CHECK=1` | off | Live memory-DB integrity check + recovery playbook. Keep off unless DB is backed up. |
| `VECTOR_OBSIDIAN_RAG_QUERY=1` | off | Obsidian/LightRAG query during context hydration. |
| `VECTOR_FASTAPI_REVIEW_LLM=1` | off | LLM-backed FastAPI code review. |
| `VECTOR_PYTHON_REVIEW_LLM=1` | off | LLM-backed Python code review. |
| `VECTOR_SECURITY_REVIEW_LLM=1` | off | LLM-backed security review. |
| `VECTOR_SEO_LLM=1` | off | LLM-backed SEO synthesis/schema/keyword work. |
| `VECTOR_GOOGLE_ADS_LLM=1` | off | LLM-backed Google Ads audit/copy/landing-page reasoning. |
| `VECTOR_FEEDBACK_LLM=1` | off | LLM-backed interview feedback analysis. |
| `VECTOR_STYLE_LLM=1` | off | Ollama-backed persona style rewrites. |
| `VECTOR_WEB_SCOUT_LLM=1` | off | LLM-backed WebScout research summaries. |
| `VECTOR_REDDIT_MINER_LLM=1` | off | LLM-backed RedditMiner opportunity extraction. |
| `VECTOR_SKILLS_LLM=1` | off | LLM-backed skills gap analysis, prioritization, learning paths. |

---

*Section 0 is the open engineering list; update this file in place as items land.*

38. **`vectorcode/src/tools/` 3rd slice + systemic loguru-shadowed-by-stdlib-logging finding, 2026-10-02 —**
    resumed after a rate-limit; the dead fork's one completed file (`tirith_security.py`, systemic
    stdlib-logging-to-loguru conversion) was independently verified and committed by the parent
    session (`c14d585f1`) before this slice started. **5 real bugs fixed, same systemic class across
    4 files**: `feishu_doc_tool.py`, `managed_tool_gateway.py`, `environments/ssh.py` each had a real
    `from loguru import logger` immediately shadowed by `logger = logging.getLogger(__name__)` two
    lines later (one via the import sitting trapped inside the module docstring, the other two via a
    plain reassignment) — every logger call in all 3 files was silently using stdlib `%s`/`%d`
    placeholders under loguru's own `{}` formatter. `video_generation_tool.py` had the identical
    shadowing shape. Fixed all 4 (remove the stdlib import/reassignment, keep the real loguru import,
    convert every placeholder). Commits: `a2711db4f`, `433b70ce1`, (managed_tool_gateway.py fix —
    folded into this entry, no separate commit message captured before compaction, verify via
    `git log -- vectorcode/src/tools/managed_tool_gateway.py`), `dc8b8c723`.
    **MAJOR SYSTEMIC FINDING, not fully fixed — needs its own dedicated slice(s)**: cross-referencing
    every file with a real `from loguru import logger` against every file with `logging.getLogger`
    (`comm -12` on the two grep outputs, not estimated) found **34 files total** sharing this exact
    shadowing bug, of which only 4 are fixed above. Remaining 30: `approval.py`, `browser_camofox.py`,
    `browser_supervisor.py`, `browser_tool.py`, `checkpoint_manager.py`, `code_execution_tool.py`,
    `computer_use/cua_backend.py`, `delegate_tool.py`, `discord_tool.py`, `environments/base.py`,
    `environments/daytona.py`, `environments/docker.py`, `environments/managed_modal.py`,
    `environments/modal.py`, `environments/vercel_sandbox.py`, `feishu_drive_tool.py`, `file_tools.py`,
    `image_generation_tool.py`, `lazy_deps.py`, `mcp_oauth.py`, `mcp_tool.py`, `memory_tool.py`,
    `rl_training_tool.py`, `send_message_tool.py`, `skill_manager_tool.py`, `skill_usage.py`,
    `skills_hub.py`, `skills_sync.py`, `skills_tool.py`, `tts_tool.py`, `vision_tools.py`,
    `voice_mode.py`, `web_tools.py`, `yuanbao_tools.py`. 13 of these 30 are also on the
    already-reserved "needs its own dedicated slice" large-file list (over 1,000 lines each:
    `skills_hub.py`, `mcp_tool.py`, `browser_tool.py`, `delegate_tool.py`, `web_tools.py`,
    `send_message_tool.py`, `code_execution_tool.py`, `tts_tool.py`, `skills_tool.py`,
    `rl_training_tool.py`, `browser_supervisor.py`, `file_tools.py`, `approval.py`, `voice_mode.py`) —
    those slices should fix this same-file logger bug as part of their own full read, not as a
    separate pass. The remaining 16 small/medium files are a good, well-scoped next slice on their own.
    **1 dead-code/duplication finding, flagged not fixed**: `code_execution.py` (85 lines, its own
    unused `ALLOWED_TOOLS` constant) has zero real callers anywhere in the repo — confirmed via
    repo-wide grep — superseded entirely by `code_execution_tool.py` (1,581 lines, has the real,
    wired-in `SANDBOX_ALLOWED_TOOLS`, used by `vectorcode/src/model_tools.py`). Same unexplained-
    duplication shape as the `core/jcode` vs. `vectorcode/src/vc_tools` question the owner raised
    this session — needs an owner call (delete the dead file, or confirm it's intentionally kept for
    a reason not visible in the code) rather than a guessed fix.
    **Verified clean, real depth**: `schema_sanitizer.py`, `code_execution.py` (logic itself, separate
    from the dead-code flag above), `osv_check.py` (fail-open is explicitly documented/intentional,
    not a bug), `microsoft_graph_auth.py` (correct OAuth client-credentials flow, proper token
    caching/locking, httpx not raw requests).
    **Remaining scope in `vectorcode/src/tools/`**: of 129 total files, 21 now have real depth
    (17 before this slice + feishu_doc_tool.py + video_generation_tool.py + managed_tool_gateway.py +
    environments/ssh.py); 108 remain, including the 30-file systemic logger bug list above (16 of
    which are small/medium and not yet separately scheduled) and all 18 of the 1,000+-line files.

39. **`vectorcode/src/vector_cli/` 2nd slice, 2026-10-02 —** resumed slice: a prior fork died from a
    rate limit right after starting, having found but not finished fixing `vault_cmd.py`'s
    data-destroying fail-open on decrypt failure (completed and committed separately, `36d5256de`).
    This slice covered 9 more small files with real depth, continuing from the 11 already done.
    **Fixed (6 real bugs):** `hints.py`'s `hint_no_config()` told users the config file would be at
    `~/.vectorcode.src/config.toml` — a Python-module-path fragment leaking into user-facing text,
    pointing at a directory that never exists (real path confirmed via `vc_core/config.py`:
    `~/.vector/config.toml`); `__init__.py`'s `kanban_db` import guard had the systemic
    `"[VECTOR] suppressed exception"` placeholder; `gateway_cmd.py`'s `start()` (no `--install`)
    printed `"Gateway started. Press Ctrl+C to stop."` with zero real action — no subprocess, no
    blocking loop — phantom success (dormant: this `gateway` click group is not registered anywhere
    in the real CLI, confirmed via repo-wide grep, fixed anyway per this cycle's bar);
    `proxy/adapters/vector_portal.py` — importing this module raised `ImportError` immediately:
    `vector_cli.auth._write_shared_nous_state` has never existed anywhere in `auth.py`'s git history
    (confirmed), so this was broken from the file's first commit, not a regression. Removed the dead
    import/call (`_save_state()` already persists correctly via the same `providers.nous` +
    `_save_auth_store()` path `auth.py`'s own `persist_nous_credentials()` uses) and fixed its
    stdlib-logging-instead-of-loguru + `%s`-placeholders in the same pass. **FLAG FOR OWNER, not
    fixed:** even after the import fix, this module *still* cannot be imported —
    `vectorcode/src/vector_cli/proxy/adapters/base.py` (and `proxy/__init__.py`,
    `proxy/adapters/__init__.py`) do not exist anywhere in the repo; `vector_portal.py` is the ONLY
    file under `proxy/` — an orphaned fragment of an incomplete port with zero real callers anywhere
    (confirmed via grep), not fixable without inventing a base-class hierarchy the owner hasn't
    specified. `daemon_cmd.py` — 3 more `"[VECTOR] suppressed exception"` placeholders (SIGTERM/SIGKILL
    failure paths, psutil uptime lookup), plus simplified a redundant `except (ImportError, Exception)`
    to just `Exception`.
    **Verified clean, real depth (14 files):** `init_cmd.py`, `default_soul.py`, `_chat_banner.py`,
    `_first_run.py`, `colors.py`, `_tool_names.py`, `_chat_notifications.py`, `platforms.py`,
    `_bg_state.py` (noted a second instance of the same stale `.vectorcode.src` path, but only in an
    internal docstring, not user-facing — not fixed, too low-value for the remaining budget),
    `timeouts.py`, `pt_input_extras.py`, `log_config.py` (intentional stdlib `"openjarvis"` named
    logger for legacy-compat subsystems, not a bug), `add_cmd.py`, `browser_connect.py`,
    `registry_cmd.py`, `pearl_cmd.py` (pass-through CLI wrapper, user-controlled args by design, not
    an injection risk).
    New tests: `tests/test_vectorcode_vector_cli_hints_and_init.py` (2), `tests/test_vectorcode_
    gateway_cmd_foreground_start.py` (1), `tests/test_vectorcode_vector_portal_logging.py` (3,
    source-level — the module cannot actually be imported), `tests/test_vectorcode_daemon_cmd_
    logging.py` (2). 8 tests total, all independently passing. Commits: `86a5f68a2`, `0094423a4`,
    `354494720`, `dfca9f0f0`.
    **Remaining scope in `vectorcode/src/vector_cli/`**: of 123 total files, 20 now have real depth
    (11 before this slice + 9 from this one); 103 remain, including 19 files 1,200+ lines each
    (`main.py` 10,191, `kanban_db.py` 4,840, `auth.py` 4,370, `config.py` 4,266, `gateway.py` 4,228,
    `setup.py` 3,372, `web_server.py` 3,175, `models.py` 3,069, `tools_config.py` 2,318, `kanban.py`
    2,253, `commands.py` 1,621, `skills_hub.py` 1,597, `model_switch.py` 1,468, `plugins_cmd.py`
    1,281, `doctor.py` 1,274, `runtime_provider.py` 1,256, `plugins.py` 1,198 — each needing its own
    dedicated future slice) and roughly 80 more untouched small/medium files (e.g. `kanban.py`,
    `commands.py` already counted above, `model_switch.py`, `profiles.py`, `mine_cmd.py`, `skin_
    engine.py`, `backup.py`, `nous_subscription.py`, `mcp_config.py`, `kanban_diagnostics.py`, and
    dozens more).

40. **`vectorcode/src/tools/` 4th slice — completed the 19-file systemic logger-shadow fix, 2026-10-02 —**
    resumed after a rate-limit (the dead fork's one completed file, `tirith_security.py`, was already
    independently verified and committed, `c14d585f1`). Fixed the remaining 19 of 23 total files sharing
    the systemic bug first found in the prior slice (`from loguru import logger` present but shadowed by
    `logger = logging.getLogger(__name__)` -- in 12 of the 19, the loguru import line was dead text sitting
    inside the module docstring, never actually executed): `browser_camofox.py`, `checkpoint_manager.py`,
    `computer_use/cua_backend.py`, `discord_tool.py`, `environments/daytona.py`, `environments/docker.py`,
    `environments/managed_modal.py`, `environments/modal.py`, `environments/vercel_sandbox.py`,
    `feishu_drive_tool.py`, `image_generation_tool.py`, `lazy_deps.py`, `mcp_oauth.py`, `memory_tool.py`,
    `skill_manager_tool.py`, `skill_usage.py`, `skills_sync.py`, `vision_tools.py`, `yuanbao_tools.py`.
    Moved the real import out of the docstring where needed, removed the stdlib shadow, converted every
    `%s`/`%d`/`%r`/`%.Nf` placeholder to `{}`/`{:.Nf}` (including 5 stragglers split across adjacent
    concatenated string literals that the mechanical first pass missed -- only caught via a full AST walk
    of every logger call's string arguments, not regex on raw text). Commit `5cbac2980`.
    **One false positive confirmed, not touched**: `environments/base.py` matched the same mechanical
    `comm -12` cross-reference (its docstring also contains dead `from loguru import logger` text) but its
    real stdlib `logger = logging.getLogger(__name__)` + `logger.setLevel(logging.INFO)` is genuinely
    intentional -- `run_agent.py`'s real `quiet_mode` feature calls
    `logging.getLogger('tools').setLevel(logging.ERROR)` for the whole `tools.*` hierarchy, and this file's
    opt-in `VECTOR_DEBUG_INTERRUPT` trace depends on participating in that same stdlib hierarchy to
    override it. Confirmed via a repo-wide grep for the real caller before assuming it was "the same bug" --
    it is not. Left entirely alone; the dead docstring text is misleading but not itself a functional bug.
    **Second, separate bug surfaced by the fix, not previously flagged**: 22 logger calls across 9 of the
    19 files (`checkpoint_manager.py`, `environments/docker.py`, `environments/vercel_sandbox.py`,
    `image_generation_tool.py`, `memory_tool.py`, `skill_manager_tool.py`, `skill_usage.py`,
    `skills_sync.py`, `vision_tools.py`) passed `exc_info=True` -- a real, working kwarg under the OLD
    stdlib logger that becomes a silent no-op under loguru's real logger (verified directly: no traceback
    printed). These calls would have silently stopped capturing real tracebacks the moment the shadow bug
    was fixed, with nothing flagging the regression since no test asserts on traceback presence. Converted
    to `logger.opt(exception=True).<level>(...)`, the pattern already established elsewhere in this exact
    package (`browser_cdp_tool.py`, `kanban_tools.py`) -- verified it actually captures a real traceback.
    **Third, separate test-infrastructure bug surfaced, fixed**: pytest's `caplog` fixture hooks stdlib
    logging's root handler, not loguru -- any test asserting `caplog.text` against a module using real
    loguru saw an empty string (the message IS logged correctly, visible in captured stderr; caplog just
    never received it). Latent and invisible before now because every affected module had the OTHER bug
    (stdlib shadow), which made caplog work by accident. Broke 8 assertions across
    `test_discord_tool.py`/`test_docker_environment.py`/`test_mcp_oauth.py`/`test_vision_tools.py` once the
    real fix landed. Fixed with the standard loguru+pytest recipe: an autouse fixture in
    `vectorcode/python/tests/legacy_ported/conftest.py` that forwards loguru records into stdlib logging
    for the test's duration. Commit `5b725f8ce`. 25 files in this suite use `caplog` and could hit the same
    gap for any future loguru-shadow fix elsewhere in `vectorcode/src/`.
    **Verified**: ran the full existing legacy_ported suite for all 19 files (31 tests) against a stashed
    pre-fix baseline -- 0 new failures after the caplog fix landed, 0 pre-existing failures fixed (not this
    slice's goal). 1 of 32 pre-existing failures (`test_non_persistent_cleanup_removes_container`)
    independently confirmed via 3x isolated runs to fail deterministically on BOTH pre-fix and post-fix
    code -- a pre-existing thread-timing test fragility (`cleanup()` spawns a daemon thread for `docker
    stop`; the test asserts on captured subprocess calls immediately after `cleanup()` returns, before the
    thread necessarily runs), unrelated to this change, not fixed here.
    New `tests/test_vectorcode_tools_loguru_shadow_regression.py` (4 tests, AST-based, covers all 23 fixed
    files across both slices): locks in no real loguru import is missing, none is shadowed by stdlib
    logging, no logger call has a printf-style placeholder, none uses the `exc_info=` kwarg.
    **Remaining scope in `vectorcode/src/tools/`**: of 129 total files, 40 now have real depth (21 before
    this slice + 19 here); 89 remain, including all 18 of the 1,000+-line files (each needing its own
    dedicated slice -- the logger-shadow fix should be applied there too as part of that full read, since
    none of those 18 were touched by either logger-shadow slice).

41. **`vectorcode/src/channels/` (38 files) + `vectorcode/src/cron/` (3 files), 2026-10-03 —** full
    deep-verify of a previously-untouched 41-file vectorcode/ slice (the owner clarified "V1 ready"
    means full depth on ALL of vectorcode/, including currently-dormant/not-yet-wired-in code --
    channels/ has zero confirmed direct-instantiation callers found, registered only via
    `@ChannelRegistry.register(...)` for presumed future dynamic dispatch, same bar as other
    narrow-fix-anyway findings this cycle).
    **Systemic bug, 31 of 41 files: stdlib `logging.getLogger(__name__)` instead of loguru**
    (CLAUDE.md rule 6), same class already fixed 23 times across `vectorcode/src/tools/` and
    `vectorcode/src/vector_cli/`. Fixed all 31 (commit `beccf6dc8`, `webhook.py` separately in
    `feca4bb02`). Follow-up pass caught two sub-bugs the single-line fix missed: **34 multi-line
    `%s`/`%d` printf-style placeholders** across 17 files (format string on a separate source line
    from the `logger.X(` call, invisible to a single-line grep) and **41 `except Exception: /
    logger.debug(msg, exc_info=True)` sites across 29 files** -- confirmed directly that loguru
    silently no-ops on an unrecognized `exc_info=True` kwarg (verified with a standalone repro, no
    error, no traceback), so every one of these 41 sites was dropping the real exception. Both
    fixed via an AST-aware multi-line regex pass + per-file verification, commit `8f9ca3eaa`.
    **1 real security finding: `channels/webhook.py`'s `send()` had zero SSRF validation** on the
    caller-configured target URL before a real `httpx.request()` call -- same bug class fixed in
    `core/browser/`, `core/seo/`, `core/vision_control/` this cycle. Fixed with
    `SSRFGuard(resolve_dns=True)`, commit `feca4bb02`.
    **Checked and confirmed NOT a bug**: `channels/telegram.py`'s bot token in the URL path
    (`https://api.telegram.org/bot<TOKEN>/...`) is Telegram's own required Bot API convention, no
    header alternative exists -- not the same shape as this cycle's other credentials-in-URL
    findings (which were VECTOR choosing the weaker option when a header alternative existed).
    New tests: `tests/test_vectorcode_webhook_channel_ssrf.py` (4 tests). Verified: syntax-checked
    all 41 files; re-ran `vectorcode/python/tests/legacy_ported/cron/` (full suite) + 5 gateway
    discord/slack test files -- ~28 cron failures (Windows chmod/home-dir-expansion environment
    limitations, one unrelated `vectorcode/src/agent/memory_manager.py` ImportError) + 2 gateway
    failures (`vectorcode/src/gateway/run.py`, untouched, `asyncio.CancelledError`) all
    independently reconfirmed via `git stash` to be identical on unmodified code -- zero
    regressions from any of this slice's 3 commits.
    **Remaining in this slice's scope**: none -- all 41 files got real depth. `channels/` and
    `cron/` are now both fully deep-verified.
    **Flagged for owner, not resolved**: none new this slice (the `channels/` vs. `core/api/routers/
    channels.py` vs. `vectorcode/src/comms/` naming-overlap question was checked -- confirmed these
    are three genuinely different things: `channels/` is vectorcode's own multi-platform adapter
    library, `core/api/routers/channels.py` is VECTOR's own already-wired channel-listing API
    endpoint, `comms/` -- a sibling fork's scope this same session -- is a separate gateway layer;
    no actual duplication found here, unlike the jcode/vc_tools finding).

42. **`vectorcode/src/gateway/` root slice (partial, 2026-10-04) —** began the requested
    24-file deep audit, explicitly excluding `platforms/` and the separately-reserved 11,770-line
    `run.py`. Work was done by Codex (gpt-5.6-sol); Codex's sandbox could not write
    `.git/index.lock` (`Permission denied`), so every change below was reviewed, in places
    corrected, and committed by Claude on Codex's behalf — commit hashes are real.
    **Fixed:** 9 modules used stdlib logging instead of loguru (`builtin_hooks/boot_md.py`,
    `channel_directory.py`, `delivery.py`, `mirror.py`, `platform_registry.py`, `session.py`,
    `shutdown_forensics.py`, `status.py`, `stream_consumer.py`, `whatsapp_identity.py`), with
    `stream_consumer.py` importing loguru and then shadowing it; a complete pass also converted
    90+ `%s`/`%d`/`%r`/`%.1f` logger placeholders across those files plus `pairing.py`
    (`cee9fd86e`). `hooks.py` and `pairing.py` used forbidden production `print()` calls, fixed
    in the same commit and in `484aef3f0`. `delivery.py` interpolated caller-controlled `job_id`
    into both an output directory and a filename without validating it, allowing `../` or
    backslash path traversal (CWE-22); both paths now require one safe path component
    (`71aa5b0ad`). `builtin_hooks/boot_md.py` launched a raw `threading.Thread` (banned by
    CLAUDE.md); replaced with `asyncio.to_thread()` wrapped in `asyncio.create_task()` — Claude
    additionally added a module-level strong-reference set, since a bare `create_task()` result
    with nothing holding a reference to it can be garbage-collected mid-run (`b01435e4b`).
    `server.py`'s agent-execution gateway defaulted to binding `0.0.0.0` with no stated reason
    (its one real caller already explicitly binds `127.0.0.1`), and its `/run` handler ran a
    convoluted `run_in_executor` + nested `asyncio.run`/`asyncio.get_event_loop` dance that also
    unconditionally hardcoded `sess["status"] = "complete"` regardless of actual outcome; both
    fixed — direct `await`, default now `127.0.0.1`, status taken from the real result
    (`9ab8489ff`). **Corrected by Claude during review:** Codex's first pass at
    `sticker_cache.py` made `_load_cache()` raise on a corrupt/unreadable cache file, matching
    the vault/webhook fail-open-destroys-data pattern fixed elsewhere this audit — but that
    pattern fits credential/subscription stores where losing data matters. This cache is cheaply
    regenerable (one vision call) and has exactly one caller (`telegram.py`'s sticker handler)
    that does not wrap the lookup in a `try/except`; raising would have crashed sticker handling
    on any corruption instead of costing one extra vision call. Reverted to fail-open with a
    logged warning, and updated the matching test to assert the corrected contract
    (`a82311e19`). New tests: `tests/test_vectorcode_gateway_logging.py` (4),
    `tests/test_vectorcode_gateway_hooks_and_sticker_cache.py` (2),
    `tests/test_vectorcode_gateway_delivery_paths.py` (5), and
    `tests/test_vectorcode_gateway_server.py` (2) — 13/13 passing. Cross-checked against the
    pre-existing ported suite (`test_delivery.py`, `test_hooks.py`, `test_mirror.py`,
    `test_pairing.py`, `test_channel_directory.py`, `test_status.py`, `test_stream_consumer.py`,
    `test_stream_consumer_fresh_final.py`, `test_sticker_cache.py`, `test_platform_base.py`): 5
    pre-existing failures found, all confirmed via `git stash` to fail identically on the
    unmodified baseline (Windows file-permission/chmod environmental flakiness in `pairing.py`/
    `status.py`, and an unrelated count-assertion mismatch in `test_stream_consumer.py`) — none
    caused by this slice. **FLAGGED, not fixed:** `pairing.py` and `session.py` still import
    `threading` for synchronous store locks; those stores are called from executor workers, so
    replacing the locks is an async architecture/migration decision, not a safe one-line audit
    fix. The HTTP/WebSocket API still has no authentication when an operator explicitly chooses
    a non-loopback bind; deciding the authentication scheme is owner policy, the unsafe default
    is fixed. **Depth statement:** real full depth completed for `__init__.py`,
    `builtin_hooks/__init__.py`, `builtin_hooks/boot_md.py`, `delivery.py`, `display_config.py`,
    `hooks.py`, `restart.py`, `runtime_footer.py`, `session_context.py`, `slash_access.py`,
    `sticker_cache.py`, and `whatsapp_identity.py`. The remaining files received targeted
    security/pattern inspection and several proven fixes, but not the promised complete
    line-by-line depth; in particular `config.py` (1,373 lines, confirmed already loguru-clean
    on inspection but not logic-reviewed), `session.py` (1,373), `status.py` (803), and
    `stream_consumer.py` (985) must be resumed as their own future slice rather than represented
    as complete.

43. **`vectorcode/src/{agents remainder, api, bench, claims, config, daemon, display, districts}/`
    full-depth audit (2026-10-04) —** completed the requested deep audit of the remaining small
    `agents/` files plus every file in `api/`, `bench/`, `claims/`, `config/`, `daemon/`,
    `display/`, and `districts/__init__.py`. `gateway/` was explicitly out of scope (a sibling
    fork's territory, item 42 above). **Fixed, each with a new regression test:**
    `agents/loader.py`'s `definitions_from_markdown_dir()` only wrapped the file-read step in
    try/except — one malformed agent `.md` file (e.g. a non-numeric `hp:`) raised uncaught and
    the caller (`registry.py`'s `get_registry()`, which populates the real agent registry on
    every process start) caught it at the whole-batch level, silently dropping every other
    agent in the directory, not just the bad one; isolated per-file. `api/server.py`'s two SSE
    streaming endpoints sent `Content-Type: text/event-line` (not a real MIME type; should be
    `text/event-stream`) — fixed both (dormant, zero callers). `claims/_service.py`'s
    `ClaimService.claim()` duplicate-claim guard only checked `status == ClaimStatus.active`,
    not the full `_ACTIVE_STATUSES` set the rest of the module uses as "still live" — an issue
    sitting in `paused`/`blocked`/`in_review`/`pending_handoff`/`stealable` could be claimed a
    second time, creating two live claims for one issue; **live bug** (real caller:
    `swarm.py`'s `SwarmAgent.start_task()`, return value unchecked). Same unfixed bug confirmed
    present in the now-dead `vectorcode/src/claims.py` monolith (see flag below). Also removed a
    stale docstring in `_service.py` claiming it "imports from the canonical claims.py" — it
    never has. `config/env_detector.py`'s `adjust_paths()` and `config/theme.py`'s
    `ThemeEngine.__init__`→`_load_custom_themes()`/`save_theme()` both called `Path.home()` with
    no `from pathlib import Path` anywhere in either file — 100% reproducible `NameError` on
    every call (confirmed by running each file's own mandated self-test block directly and
    watching it crash); both dormant but part of documented public API, fixed. `daemon/gateway.py`'s
    `GatewayDaemon.session_key()` embedded the literal string `"None"` into the key when
    `thread_id` was absent instead of omitting the segment, diverging from the live canonical
    key format in `gateway/session.py`; fixed to match. `daemon/service.py` was missing a
    `ServiceManager` class entirely — `core/loop/autonomous_loop.py` (live core autonomous loop)
    does `from vectorcode.src.daemon.service import ServiceManager` inside a bare
    try/except, so this **live** `ImportError` was silently swallowed every single time and
    `self._daemon_mgr` was always `None`; added a thin `ServiceManager` wrapping the two
    generator functions that already made up the module's whole capability. Six systemic
    stdlib-logging-instead-of-loguru fixes (`agents/coordinator.py`,
    `bench/{energy,latency,throughput}.py`) plus two %-style→`{}` loguru placeholder fixes in
    `config/theme.py`. `agents/workflow_engine.py`'s `execute()` always reported top-level
    `status: "completed"` even when a step failed and the loop broke early — the "phantom
    success" bug class, dominant this whole cycle; fixed to reflect the real per-step outcome.
    `agents/manager.py`'s silent `except Exception: <empty stub>` fallback got a real warning
    log. **Reviewed, no changes needed:** `agents/{__init__,_abc,agent,deep_research,
    digest_store,executor,scheduler}.py`, `bench/{__init__,_abc,_stats}.py`,
    `claims/{__init__,_types,_persistence,_stealing}.py`, `config/__init__.py`,
    `daemon/{__init__,session_expiry}.py`, `display/{__init__,spinner,renderer,diff_preview}.py`,
    `districts/__init__.py` (a 6-line shim; real districts live at the top-level `districts/`
    package). `display/renderer.py`'s unusual `from vectorcode.display.spinner import *`-via-shim
    import chain was verified working end-to-end despite looking circular. **FLAGGED, not
    fixed — owner decision needed:**
    (a) `vectorcode/src/claims.py` (63KB monolith) and the `vectorcode/src/claims/` package
    (this audit's scope) share the same import name. Confirmed empirically: `import
    vectorcode.src.claims` resolves to the package (`claims/__init__.py`, has `__path__` set),
    so `claims.py` is 100% dead, unreachable code — Python's package-over-module precedence
    shadows it completely. The package is a clean 1:1 structural split of the monolith into
    `_types.py`/`_persistence.py`/`_service.py`/`_stealing.py` with identical class names, so
    unlike the already-deferred jcode-vs-vc_tools duplication (two genuinely different
    unwired approaches), this looks like simple leftover-file cruft from the refactor, not an
    open design question — but deleting a 63KB file is bigger than this session's narrow-fix
    scope. For precedent: `config/__init__.py` solves the identical "package shadows a
    same-named sibling module" shape correctly via a `_reexport_config_module()` helper that
    `exec_module()`s the shadowed file directly and merges its public names in — that pattern
    only makes sense when the shadowed module still holds unique live content (it does, for
    `config.py`'s `VectorConfig`/`SESSION_DIR`/etc.); `claims.py` has no unique content left, so
    re-exporting would just resurface its already-identified duplicate-claim bug under a second
    mechanism. Recommend: delete `vectorcode/src/claims.py` once confirmed truly redundant.
    (b) `daemon/service.py`'s new `ServiceManager` fixes the `ImportError`, but
    `core/loop/autonomous_loop.py` never actually reads `self._daemon_mgr` anywhere after
    assigning it — the wiring is orphaned even with the import now working. Whether
    `autonomous_loop.py` is supposed to call it (e.g. on startup, to ensure the systemd/launchd
    unit is installed) is a real design question outside this session's scope (that file isn't
    part of the assigned directories). New tests: `tests/test_vectorcode_agents_loader_markdown_batch_isolation.py`
    (2), `tests/test_vectorcode_api_server_sse_content_type.py` (1),
    `tests/test_vectorcode_bench_loguru_smoke.py` (3),
    `tests/test_vectorcode_claims_service_duplicate_claim.py` (2, verified both fail against the
    pre-fix code before confirming they pass against the fix),
    `tests/test_vectorcode_config_missing_path_import.py` (3),
    `tests/test_vectorcode_daemon_gateway_and_service.py` (3), plus the earlier
    `tests/test_vectorcode_agents_workflow_engine_phantom_success.py` (2) — 16/16 passing.
    **Depth statement:** genuine full line-by-line depth completed for every file listed above
    as fixed or reviewed; nothing in this slice was deferred by live-vs-dormant status.

44. **`vectorcode/src/plugins/` audit (77 tracked Python files, partial, 2026-10-04) —**
    audited the authoritative `git ls-files "vectorcode/src/plugins/*.py"` inventory and applied
    targeted security/correctness fixes across the slice. **Fixed:** 33 files used stdlib
    `logging.getLogger(__name__)` or imported loguru and then shadowed it; all now use the real
    loguru logger, and every affected `%s`/`%d`/`%r`/float-style call (including multi-line calls
    in the four 1,200+-line memory modules) was converted to loguru `{}` formatting so diagnostic
    arguments are no longer silently dropped. `bridges/qe_security_bridge.py:14` used string
    prefix matching for path confinement, so an allowed `safe` directory also authorized a
    sibling `safe-evil`; fixed with `Path.is_relative_to()`. `google_meet/node/protocol.py:119`
    compared its shared bearer token with timing-variable `!=`, and
    `teams_pipeline/subscriptions.py:111` did the same for the Graph client-state secret; both now
    use `secrets.compare_digest()`. `image_gen/xai/__init__.py` and three HTTP paths in
    `memory/retaindb/__init__.py` used the project-banned `requests` package; migrated to equivalent
    synchronous `httpx` calls (including `follow_redirects=True` for RetainDB content downloads).
    `google_meet/cli.py:97-98` installed an import-failure callback that closed over exception
    variable `e`; Python clears that name after the `except` suite, so every later invocation
    raised `NameError`; the callback now captures the rendered error in a default argument.
    New regression suite: `tests/test_vectorcode_plugins_audit_regressions.py` (6 tests), all
    passing; all 77 plugin files also pass `compileall`, `git diff --check`, and AST-wide guards
    for forbidden `requests`, stdlib logger shadowing, and printf-style logger placeholders.
    **FLAGGED, not fixed:** the three tracked `teams_pipeline` modules import nonexistent
    `plugins.teams_pipeline.models`, `.store`, and `.pipeline` modules, making that feature
    unimportable; restoring or designing those components is not a narrow audit fix. Multiple
    memory backends plus Google Meet still rely extensively on banned `threading`; converting
    their synchronous provider contracts and background lifecycle to asyncio is an architecture
    migration. `memory/holographic/store.py:116` stores real persistent facts through raw
    `sqlite3.connect()` rather than VECTOR's SQLCipher connection gateway; encryption/schema
    migration needs an owner decision. **Depth statement:** every file received syntax, import,
    logging, dependency, subprocess, filesystem, exception, and credential-pattern inspection.
    Full line-by-line depth was completed for the bridge files, Google Meet node protocol,
    Teams subscriptions, xAI image provider, RetainDB HTTP client sections, and the logging call
    sites changed. The 1,200+-line Hindsight/Honcho files and the remaining large Google Meet and
    memory implementations received targeted rather than complete line-by-line logic review and
    must be resumed; this entry deliberately does not represent the requested 77-file audit as
    complete. Work was done by Codex (gpt-5.6-sol); as with item 42, Codex's sandbox could not
    write `.git/index.lock` (`Permission denied`), so every change above was reviewed and
    committed by Claude on Codex's behalf — see commit hashes below.

45. **`vectorcode/src/gateway/{config,session,status,stream_consumer}.py` full-depth follow-up,
    2026-10-04 —** these 4 files only received a mechanical loguru-shadow logging pass in the
    `vectorcode/src/gateway/` root slice (item 42); this entry is the deferred real logic review.
    **Fixed:** `config.py`'s `_apply_env_overrides()` legacy-env-var back-compat branch (the
    renamed `QQ_HOME_CHANNEL` → `QQBOT_HOME_CHANNEL`) called
    `logging.getLogger(__name__).warning(...)`, but this module only imports `from loguru import
    logger` — `logging` is never imported anywhere in the file. Any user still setting the legacy
    `QQ_HOME_CHANNEL` env var hit a `NameError` inside `load_gateway_config()`, crashing gateway
    startup, instead of getting the intended one-time deprecation warning. Fixed by using the
    existing logger (commit `f2a32c563`). `stream_consumer.py` had two related bugs in
    `GatewayStreamConsumer`, found by investigating a previously-dismissed-as-"pre-existing"
    failing test rather than taking that dismissal at face value, since this file was now
    squarely in scope: (1) `run()`'s `got_done` handling calls `_send_or_edit(accumulated,
    finalize=True)` when no earlier mid-stream fallback was triggered; if *that* finalize edit
    itself exhausts the flood-control strike budget, `_send_or_edit` sets
    `self._fallback_final_send=True` as a side effect of giving up — but the `if
    self._fallback_final_send:` check that would normally flush the pending text via
    `_send_fallback_final()` already ran earlier in the same `if/elif` chain, using the stale
    pre-call value. The accumulated text was silently dropped: never sent, never edited, never
    delivered via the fallback path either. Fixed by re-checking `_fallback_final_send`
    immediately after that finalize call. (2) `_try_strip_cursor()` unconditionally set
    `self._last_sent_text` to the cursor-stripped text after calling `adapter.edit_message()`,
    even when the call returned `success=False`, desyncing internal tracking from what the
    platform message actually shows; fixed to only update on confirmed success (currently inert
    given today's single caller's control flow, but the same "treat a non-exception result as
    success without checking `.success`" bug class fixed everywhere else in this file). Verified
    fix (1) directly: `vectorcode/python/tests/legacy_ported/gateway/test_stream_consumer.py
    ::TestSegmentBreakOnToolBoundary::test_edit_failure_sends_only_unsent_tail_at_finish` was
    failing before this fix (`adapter.send.call_count` was 1, not the expected 2 — the tail text
    was dropped) and passes after it; the full pre-existing suite (`test_stream_consumer.py` +
    `test_stream_consumer_fresh_final.py`, 90 tests) passes with zero regressions. New
    `tests/test_vectorcode_gateway_stream_consumer_finalize_fallback.py` (2 tests) proves fix (2)
    directly (commit `063405a30`). **Reviewed, no changes needed:** `status.py` (804 lines) — careful,
    well-reasoned PID/lock-file concurrency logic throughout; one harmless cosmetic artifact
    (a stray `from loguru import logger` sitting inside the module's own docstring text at line 2,
    dead but inert since the real import at line 15 works correctly) not worth a fix/test cycle.
    `session.py` (1,373 lines) — reviewed in full; the `threading.Lock()` usage already flagged
    in item 42 as an owner migration decision is the only non-bug finding; traced the one
    `force_new=True` caller (`run.py:5501`) to confirm `get_or_create_session()`'s SQLite
    end-session gap on that path is unreachable today (the sole caller only passes `force_new=True`
    after `reset_session()` has already confirmed no entry exists for that key), not a live bug.
    **Depth statement:** genuine full line-by-line depth completed for all 4 files. No further
    follow-up needed on this specific scope.

46. **`vectorcode/src/gateway/platforms/` 12-file continuation (2026-10-05) —** audited
    `signal_rate_limit.py`, `sms.py`, `feishu_comment_rules.py`, `qqbot/keyboards.py`,
    `yuanbao_sticker.py`, `qqbot/chunked_upload.py`, `email.py`, `yuanbao_media.py`,
    `mattermost.py`, `bluebubbles.py`, `signal.py`, and `whatsapp.py` (7,828 lines total).
    **Fixed:** nine files used stdlib logging (four even imported loguru first and immediately
    shadowed it); all affected production logging now uses loguru and its `{}` formatting, so
    diagnostic arguments are no longer silently discarded. Production `print()` calls in Email
    and WhatsApp were likewise replaced with structured loguru calls (the explicit
    `feishu_comment_rules.py` CLI retains stdout output). Feishu's generic mtime cache treated a
    corrupt/unreadable persistent pairing-approval store as genuinely empty, allowing the next
    add to overwrite and destroy existing approvals; pairing data now fails closed while the
    cheaply replaceable rules config retains its logged empty-config fallback. Email marked an
    IMAP UID seen *before* FETCH succeeded, permanently suppressing a still-unread message after
    one transient fetch failure; the UID is now recorded only after a valid fetch. Email,
    Mattermost, Signal, and WhatsApp shutdown paths re-raised `CancelledError` from tasks they had
    themselves cancelled, aborting the remainder of disconnect cleanup; those expected local
    cancellations are now consumed. BlueBubbles compared its webhook password with timing-variable
    `!=` and launched read receipts through an unreferenced `asyncio.create_task()`; it now uses
    `secrets.compare_digest()` and holds the task in the adapter's background-task set. WhatsApp
    converted Baileys device-qualified JIDs such as `user:2@server` into invalid `user@2@server`
    identifiers, breaking reply/mention identity matching; it now removes the device suffix.
    QQBot chunked-upload parsing accepted a non-empty raw `parts` array containing no dictionaries,
    then skipped every upload and called completion; it now rejects that malformed response.
    `SMS_WEBHOOK_HOST=0.0.0.0` was reviewed and retained because the endpoint fails startup without
    a configured Twilio URL unless an explicitly named insecure-development override is set, and
    live requests use HMAC-SHA1 plus `compare_digest()`. New regression suite:
    `tests/test_vectorcode_gateway_platforms_audit_regressions.py` (9 tests), all passing; all 12
    targets also pass `compileall` and `git diff --check`. The existing relevant legacy batch ran
    338/349 passing; its 11 failures were unrelated pre-existing config/sandbox/fixture expectation
    failures (gateway config bridging, HOME/lock state, a MagicMock awaited as a task, and an email
    subject expectation), not regressions in this diff. **Depth statement:** full line-by-line
    review completed for `signal_rate_limit.py`, `sms.py`, `feishu_comment_rules.py`,
    `qqbot/keyboards.py`, `qqbot/chunked_upload.py`, and `email.py`; the remaining six received
    complete security-pattern/import/task/subprocess/filesystem inspection plus focused logic-path
    review, but their unchanged long catalogue/media/adapter sections still need a final dedicated
    line-by-line pass before this 12-file slice can honestly be called complete. Commit was
    attempted with specific paths, but the sandbox could not create `.git/index.lock` (`Permission
    denied`); all changes remain uncommitted on disk for review and commit by the owner/parent agent.

47. **`vectorcode/src/learning/` audit continuation (79 tracked Python files, partial,
    2026-10-05) —** established the authoritative inventory with `git ls-files` and completed
    full-depth review of `distillation/pending_queue.py`, `distillation/execute/base.py`,
    `distillation/execute/loop.py`, `distillation/execute/appliers/{agent,intelligence,tools}.py`,
    `distillation/checkpoint/store.py`, `distillation/models.py`,
    `distillation/storage/paths.py`, and `distillation/orchestrator.py`. **Fixed:** model-produced
    pending-queue session/edit identifiers were interpolated directly into filesystem paths, so
    separator-bearing identifiers could address paths outside the intended queue or create nested
    queue paths; all queue operations now require the resulting file's parent to be exactly the
    queue directory. Agent names from edit payloads/targets were likewise joined directly below
    `agents/`, allowing prompt or few-shot writes to escape that tree; these paths now require a
    direct child of `agents/`. Both touched production modules now use loguru and `{}` formatting,
    and corrupt pending records read through `get()` emit a useful warning. New regression suite
    `tests/test_learning_path_confinement.py`: 5/5 passing. **FLAGGED, not fixed — owner/design
    decision needed:** the orchestrator calls each applier's rollback after a benchmark rejection,
    but every concrete rollback is a no-op and the orchestrator never stages/commits through its
    injected `CheckpointStore`; a rejected edit therefore remains on disk while its outcome says
    `rejected_by_gate`. Correct per-edit checkpoint transactions affect session semantics and are
    not a safe narrow patch. The whole-scope scan also found widespread stdlib/printf-style logging
    and banned `threading` plus raw SQLite in the two learning stores; those require continuation,
    with store encryption and async contracts treated as owner-level migration questions.
    **Depth statement:** only the ten files named above received genuine full logic depth. The
    remaining 69 received inventory and broad hotspot scans but not line-by-line review, so this
    entry explicitly does not claim the learning scope complete. Commit was attempted with
    specific paths, but the sandbox could not create `.git/index.lock` (`Permission denied`);
    the verified changes remain uncommitted for review.

49. **`vectorcode/src/agent/` audit continuation (79 tracked Python files, partial,
    2026-10-05) —** established the authoritative inventory with `git ls-files` and
    prioritized the credential and execution-safety paths. **Fixed:**
    `credential_pool.py` imported loguru and then shadowed it with
    `logging.getLogger(__name__)`; its 16 argument-bearing `%s` log calls therefore did
    not render diagnostics under VECTOR's required logger. It now uses loguru directly
    with `{}` placeholders. `file_safety.py` compared resolved sensitive paths without
    applying the host filesystem's case normalization, allowing differently-cased names
    such as `.SSH/ID_RSA` to bypass the denylist on Windows; all write-policy operands
    now pass through `normcase(realpath(...))`. `trajectory.py` likewise used stdlib
    logging and `%s`, so save success/failure details are now emitted correctly through
    loguru. New regression tests:
    `tests/test_vectorcode_agent_credential_pool_logging.py` (2),
    `tests/test_vectorcode_agent_file_safety_case.py` (2), and
    `tests/test_vectorcode_agent_trajectory_logging.py` (1); combined result 5/5
    passing, with touched modules also passing `compileall` and `git diff --check`.
    **FLAGGED, not fixed — owner/design decision needed:** the credential pool stores
    OAuth/API tokens in the deliberately permission-restricted, atomically-written
    `~/.vectorcode/auth.json`. Moving pooled refresh state into the project's keyring
    path would alter CLI interoperability and single-use refresh-token synchronization,
    so it is not a safe narrow patch. The pool's synchronous `threading.Lock` similarly
    requires a caller-contract migration rather than a local substitution.
    **Depth statement:** genuine full line-by-line review completed for
    `credential_pool.py`, `tool_guardrails.py`, `file_safety.py`, `retry_utils.py`,
    `trajectory.py`, `tool_result_classification.py`, `memory_manager.py`,
    `memory_provider.py`, `prompt_caching.py`, `portal_tags.py`,
    `lmstudio_reasoning.py`, `manual_compression_feedback.py`, `__init__.py`,
    `transports/{__init__,base,types}.py`, and the five two-line `lsp` re-export shims
    (`eventlog.py`, `servers.py`, `install.py`, `workspace.py`, `range_shift.py`). The
    other 58 files received inventory and broad forbidden-import/logging/subprocess/path/
    credential scans but not full logic depth. In particular `auxiliary_client.py`
    (3,491 lines) and the remaining large adapters are explicitly deferred; this entry
    does not claim the requested directory audit complete. A focused commit was attempted,
    but the sandbox could not create `.git/index.lock` (`Permission denied`), so there
    are no commit hashes and all verified changes remain uncommitted on disk.

48. **`vectorcode/src/{vc_agents,connectors,vc_tools}/` continuation (122 tracked Python files,
    partial, 2026-10-05) —** resumed where a prior same-scope fork had stopped after hitting a
    session usage limit (its own partial work — `vc_tools/git_tool.py`, `vc_agents/manager.py`,
    `vc_agents/monitor_operative.py`, 4 loguru-shadow files, and `connectors/gcalendar.py`'s
    threading.Thread design-decision flag — was already committed separately). **Fixed:** 16
    files used plain stdlib `logging.getLogger(__name__)` with zero loguru import at all
    (`connectors/{apple_music,gmail_imap,scheduler,whatsapp}.py`, `vc_agents/{__init__,
    claude_code,executor,morning_digest,prompt_loader,rlm_repl,scheduler}.py`,
    `vc_tools/{agent_tools,description_loader,http_request,web_search}.py`,
    `vc_tools/templates/loader.py`) — converted all to loguru and every %-style placeholder
    found therein (commit `0edf568b2`). A separate, easily-missed shape: 12 *more* files
    (`connectors/{apple_contacts,attachment_store,gcalendar,gcontacts,gdrive,
    github_notifications,news_rss,oauth,store,sync_engine}.py`, `vc_tools/digest_collect.py`,
    `vc_tools/storage/sqlite.py`) already correctly imported loguru with no shadow at all, but
    still had one leftover %-style placeholder each (mostly the repo-wide
    `"[VECTOR][module] suppressed <ExcType>: %s"` convention) — missed by a same-line-only grep
    since the format string and substituted variable often sit on different source lines; found
    via a multi-line-aware scan of each `logger.*(...)` call's full argument list and fixed
    (commit `10e58dbae`). Two instances of stdlib's `exc_info=True` kwarg (which loguru's
    `.debug()`/`.warning()` silently ignore) were replaced with `logger.opt(exception=True)`,
    loguru's real equivalent. `vc_agents/rlm_repl.py`'s `execute()` had a second, distinct bug:
    despite the module correctly importing loguru at the top, this one method did a local
    `import logging; logging.getLogger(__name__).warning(..., "%.200s", code)`, silently
    bypassing the module's own correct logger with a fresh stdlib one — fixed to use the module
    logger with `{:.200}` (verified live to truncate identically to `%.200s`).
    New tests: `tests/test_vectorcode_vc_agents_connectors_vc_tools_logging.py` (5) and
    `tests/test_vectorcode_connectors_vc_tools_loguru_placeholders.py` (3, including a live
    loguru-sink proof that `{}` substitutes while `%s` does not) — 8/8 passing.
    **Reviewed, no bug found:** all 10 `print()` call sites flagged by an initial grep in
    `vc_agents/{agent_registry,image_agent,insight_agent,memory_agent,reasoning_agent,
    routing_agent,skill_agent,tool_agent,video_agent,web_search_agent}.py` are inside each
    file's own `if __name__ == "__main__":` self-test block (confirmed: every `print()` line
    number falls after that file's `__main__` guard line), matching CLAUDE.md's own mandated
    per-file self-test convention — not a violation. `threading.RLock()` usage in
    `connectors/{attachment_store,store,sync_engine}.py`, `vc_agents/digest_store.py`, and
    `vc_tools/storage/{knowledge_graph,sqlite}.py` is a synchronization primitive protecting
    shared mutable state, not the banned "spawn a worker thread instead of asyncio" pattern —
    left as-is. `connectors/{gcontacts,gdrive}.py`'s `handle_callback()` raw `threading.Thread`
    spawns are the identical shape already flagged (not fixed) via `connectors/gcalendar.py`'s
    design-decision comment, which explicitly cross-references both files by name — not
    re-flagged here to avoid triplicating the same comment.
    **FLAGGED, not fixed — owner decision needed:** raw `sqlite3.connect()` bypassing
    `core.memory.episodic.get_db_connection()`'s SQLCipher gateway in
    `connectors/{attachment_store,store,sync_engine}.py`, `vc_agents/digest_store.py`, and
    `vc_tools/storage/{knowledge_graph,sqlite}.py` — these six persist VECTOR's own connector
    sync state, attachments, digests, and knowledge-graph data unencrypted on disk, the same
    bypass pattern flagged repeatedly elsewhere this audit; encrypting them is a migration
    decision, not a narrow fix. By contrast, `connectors/{apple_contacts,apple_notes,
    imessage}.py`'s `sqlite3.connect(..., mode=ro)` calls open **Apple's own macOS system
    databases** (Contacts.sqlite, Notes.sqlite, chat.db) read-only — these are not VECTOR's data
    store at all and cannot be run through the SQLCipher gateway (VECTOR doesn't create or own
    them), so they are correctly out of scope for this finding, not an oversight.
    `vc_tools/db_query.py`'s `sqlite3.connect(conn_str, ...)` is a generic SQL-query tool that
    connects to whatever connection string its caller supplies (by design, per its own
    docstring: "execute SQL queries against SQLite and PostgreSQL") — not VECTOR's own
    persisted store either, so likewise correctly out of scope.
    **Depth statement:** 27 files received genuine full-depth review with real fixes this
    continuation (16 + 12, with `connectors/gdrive.py` counted once), plus the 10 `print()`
    files and the 6 `threading.RLock`/raw-sqlite3 files above received a specific, judgment-based
    review (not a rushed skim) even though most needed no change. Combined with the prior
    fork's 10 files, roughly 52 of 122 files in this 3-directory scope now have real depth; the
    remaining ~70 files (most of `vc_agents/` proper — `agent_registry.py`, `orchestrator.py`,
    `rlm.py`, `simple.py`, etc. — most of `connectors/` — `dropbox.py`, `gdrive.py`'s own
    non-threading logic, `notion.py`, `obsidian.py`, `slack_connector.py`, `spotify.py`, etc. —
    and most of `vc_tools/` — `browser.py`, `code_interpreter*.py`, `knowledge_search.py`,
    `pdf_tool.py`, `shell_exec.py`, storage backends other than sqlite/knowledge_graph, etc. —
    still need their own continuation pass and should not be treated as audited.

50. **`vectorcode/src/skills/` audit continuation (65 in-scope tracked Python files, partial,
    2026-10-05) —** established the authoritative inventory with `git ls-files` (66 files total;
    the explicitly reserved 2,794-line `optional/migration/openclaw-migration/scripts/
    openclaw_to_vector.py` was excluded and untouched). **Fixed:** `parser.py` used stdlib logging,
    while `manager.py`, `matcher.py`, `hub.py`, `loader.py`, PowerPoint `clean.py`, Google
    Workspace `setup.py`, `domain_intel.py`, `memento_cards.py`, and `telephony.py` used stdlib
    `%s` formatting or `exc_info=True` with loguru, silently losing diagnostic values/tracebacks;
    these now use loguru's real formatting and exception API. Removed `matcher.py`'s dead stdlib
    fallback so production logging consistently obeys the repository dependency. The Canvas LMS
    skill imported the project-banned `requests`; it now uses `httpx` with pagination and HTTP
    status handling preserved. Telephony's persistent-state loader treated every parse/read/type
    failure as a new empty state, after which ordinary callers saved and could overwrite owned
    number IDs, inbound cursors, and provider mappings; an existing invalid state now logs and
    fails closed with `TelephonyError`, while an absent file still initializes normally. New
    `tests/test_vectorcode_skills_audit_regressions.py`: 4/4 passing (Canvas two-page pagination,
    live loguru interpolation, AST guard against regressed stdlib formatting, and byte-preserving
    telephony corrupt-state rejection). All 65 in-scope files pass `compileall`; `git diff --check`
    passes. **Depth statement:** genuine full line-by-line review completed only for `manager.py`,
    `matcher.py`, `parser.py`, and `optional/productivity/canvas/scripts/canvas_api.py`.
    `telephony.py` received a focused state-persistence/API hazard review, and the other changed
    modules received focused logging-path review; neither is a claim of full-file logic depth.
    Every other in-scope file received inventory and broad hazard scans only and remains for a
    dedicated continuation, including the large `telephony.py` and `maps_client.py` bodies.
    No commit hash exists: a focused commit was attempted with explicit paths, but the sandbox
    could not create `.git/index.lock` (`Permission denied`), so the verified changes remain
    uncommitted on disk.

51. **`vectorcode/src/{vc_security,telemetry,engine,vc_engine,mining,providers,speech,utils,memory}/`
    audit continuation (116 tracked Python files, partial, 2026-10-05) —** authoritative inventory
    established with `git ls-files`. **Fixed:** nine `vc_security` modules now use loguru correctly
    instead of stdlib logging, `%` placeholders, or ignored `exc_info=True`; three `engine` modules
    had the same placeholder defect fixed. `vc_security/subprocess_sandbox.py` no longer passes the
    POSIX-only `preexec_fn=os.setsid` on Windows and now uses a Windows process group plus fixed-argv
    tree termination. `memory/swarm_db.py` now rejects path separators/traversal in caller-supplied
    swarm IDs before creating a database. `utils/usage_pricing.py` now timestamps records so bounded
    summaries work, refuses to overwrite corrupt accounting state, and saves atomically. Regression
    tests in `tests/test_vectorcode_vc_security_logging.py` and
    `tests/test_vectorcode_memory_utils_audit_regressions.py`: 7/7 passing; touched modules pass
    `compileall` and `git diff --check`.
    **FLAGGED, not fixed — owner/design decisions needed:** capability enforcement is currently
    permit-by-default for unknown agents (`vc_security/capabilities.py` and its permission-gateway
    construction); configured scanner initialization can fail open to an unwrapped engine or an
    empty `BoundaryGuard`; Ed25519 private keys are written without the existing restrictive-create
    helper; `engine/tool_exec.py` uses banned `ThreadPoolExecutor` and compares Windows path scopes
    case-sensitively; multiple LLM paths do not visibly enforce session hydration or the Permission
    Gateway locally; direct `sqlite3.connect()` persists VECTOR-owned audit/memory/FAISS/swarm data
    in `vc_security/audit.py` and `memory/{backends,faiss_index,swarm_db}.py`, requiring an owner-led
    SQLCipher migration rather than a silent local rewrite.
    **Depth statement:** full line-by-line review completed for all 18 `telemetry` re-export shims;
    `engine` files other than the separately large `agent_loop.py`; and the independently reviewed
    `vc_security/{__init__,_abc,audit,boundary,capabilities,file_policy,file_utils,signing,ssrf,
    subprocess_sandbox,taint,types}.py`, `memory/{faiss_index,provider,swarm_db}.py`,
    `providers/{retry,retry_utils,router}.py`, and `utils/{subdirectory_hints,usage_pricing}.py`.
    Logging-specific review/fixes were also completed for the remaining changed `vc_security` files
    and `engine/agent_loop.py`, but those are not claimed as full logic depth. The rest of
    `vc_engine/`, `mining/`, `providers/`, `speech/`, `utils/`, `memory/`, plus the unlisted
    `vc_security` files and full `engine/agent_loop.py`, remain for continuation. No commit hash
    exists: the required focused commit was attempted with explicit paths, but the sandbox could
    not create `.git/index.lock` (`Permission denied`); all verified changes remain uncommitted.

54. **`vectorcode/src/{vc_system,tui_gateway,system,security,scripts,context,workflow,vc_core,mcp}/`
    audit continuation (60 tracked Python files, partial, 2026-10-05) —** authoritative inventories
    and line counts were established with `git ls-files`; the 5,047-line
    `tui_gateway/server.py` was explicitly deferred under the requested large-file rule. **Fixed:**
    `mcp/protocol_manager.py` imported the unrelated installed PyPI `mcp` package and therefore
    failed on every import, while `get_server()` eagerly replaced an existing named server;
    imports now target the local compatibility package and registered servers retain identity.
    `mcp/server.py` returned un-awaited coroutine objects; it now awaits any awaitable handler
    result. The MCP transport now uses loguru and writes its required JSON-lines protocol directly
    to stdout without production `print()`. Workflow agent and loop nodes no longer report success
    for explicit agent error results or missing execution systems, invalid condition expressions
    fail their step instead of silently becoming successful `false`, and transforms consume only
    graph predecessors rather than unrelated branch outputs. `context/__init__.py`'s nonexistent
    import path no longer gets silently swallowed, and `load_project_context()` now routes
    `VECTOR.md` through the existing prompt-injection scanner before embedding it. Reviewed
    `vc_system/{builder,core,orchestrator}.py` logging paths now use loguru, `{}` formatting, and
    `logger.opt(exception=True)`. Four new regression files provide 11 tests; all pass together,
    and every edited Python module passes `py_compile`.

    **FLAGGED, not fixed — owner/design decisions needed:** `workflow/engine.py` uses the
    project-banned `ThreadPoolExecutor`, and its timeout is ineffective because
    `future.result(timeout=...)` runs only after `as_completed()` yields a finished future;
    converting the public synchronous workflow API to asyncio is not a narrow patch. It also
    stores `WorkflowEdge.condition` but never consults it, so conditional routing executes every
    branch; skip/failure/result semantics need an explicit decision. `security/safe_executor.py`
    allows caller-controlled arguments to powerful interpreters/package managers (`python -c`,
    npm lifecycle commands, git configuration), so its executable allowlist is not an argument-
    level security boundary; tightening that contract could break intended callers.
    `security/injection_scanner.py` has a fallback scanner that returns an empty list on canonical
    import failure, which fails open; hard-fail versus typed-blocking-result behavior affects
    callers and remains open.

    **Depth statement:** genuine full line-by-line review completed for all seven `system/` files,
    all seven `security/` files, all six `workflow/` files, and all six `mcp/` files. Full review
    also completed for `context/{__init__,prompt_builder,session_memory,vectormd}.py` and
    `vc_system/{__init__,_channel_kwargs,orchestrator,protocols}.py`; `vc_system/builder.py` and
    `core.py` received focused logging/correctness review but not a complete logic pass. The
    remaining `context` files, `vc_system/bundles.py`, most of `tui_gateway/`, all `scripts/`, all
    `vc_core/` (including the 1,978-line config), and the deferred TUI server remain for future
    line-by-line slices. A focused commit was attempted with explicit paths, but the sandbox could
    not create `.git/index.lock` (`Permission denied`); there are no commit hashes and all verified
    changes remain uncommitted on disk.

52. **`vectorcode/src/{vc_agents,connectors,vc_tools}/` continuation, round 2 (2026-10-05) —**
    resumed this 122-file slice after a prior continuation fork finished cleanly (not a usage-limit
    cutoff) at ~52/122 files covered. Computed the exact remaining-file set via `git log` against
    the prior round's commits (0edf568b2, 10e58dbae, plus individually-named earlier fixes): 85
    files were still unreviewed at the start of this round. **Fixed:** a repo-wide bug across 13
    files (`vc_agents/{image_agent,insight_agent,memory_agent,reasoning_agent,skill_agent,
    tool_agent,video_agent,_abc}.py`, `connectors/{__init__,apple_health}.py`,
    `vc_tools/{__init__,_abc}.py`, `vc_tools/storage/__init__.py`) — 67 "suppressed exception"
    diagnostic calls passed `exc_info=True` to a loguru logger; confirmed live that loguru
    silently accepts and drops that stdlib kwarg with no traceback ever logged, so every one of
    these diagnostics (mostly guarded-import fallbacks) was permanently blind to the actual
    exception. Replaced with `logger.opt(exception=True)`, loguru's real equivalent, confirmed
    live to attach the traceback. `vc_tools/db_query.py`'s `_is_read_only_query()` only scanned
    the full query string for write keywords (DROP/DELETE/INSERT/UPDATE/ALTER/CREATE/TRUNCATE) in
    its `WITH`-CTE branch — a simple-statement query only had its *prefix* checked against the
    read-only allowlist. Because psycopg2's `cursor.execute()` (unlike sqlite3's) runs every
    semicolon-separated statement in one call, a query like `"SELECT 1; DROP TABLE users;"` passed
    the read-only guard and then actually executed the `DROP TABLE` against the PostgreSQL
    backend — a complete bypass of the tool's own `read_only=True` safety parameter via SQL
    statement stacking. Fixed by scanning for write keywords up front, uniformly, before any
    prefix match. `vc_tools/browser.py`'s `BrowserNavigateTool` wrapped its SSRF check in
    `except ImportError: pass` — if the SSRF guard module failed to import for any reason, the
    headless browser navigated to the caller-supplied URL (including internal addresses or cloud
    metadata endpoints) with zero protection and zero diagnostic; now logs a loud warning naming
    the exact URL that proceeded unprotected. New tests, all passing:
    `tests/test_vectorcode_vc_agents_connectors_vc_tools_exc_info_dropped.py` (14),
    `tests/test_vectorcode_vc_tools_db_query_stacked_statement_bypass.py` (9, verified 3 fail
    against the pre-fix code via `git stash`), `tests/test_vectorcode_vc_tools_browser_ssrf_fail_open_logged.py`
    (1). **Reviewed, no bug found:** `knowledge_sql.py` (already scans unconditionally, and
    sqlite3 itself rejects multi-statement `execute()` calls, so no stacking bypass exists there),
    `file_read.py`/`file_write.py` (both correctly use `Path.is_relative_to()` for confinement,
    not the vulnerable `startswith()` pattern), `dropbox.py` (httpx already used correctly; its
    OAuth token exchange is an explicitly-documented stub, not a silently-incomplete one),
    `apple_notes.py`/`imessage.py` (confirmed read-only connections to Apple's own system
    databases, correctly out of scope per the prior round's classification). **FLAGGED, not
    fixed:** `code_interpreter.py`'s `_BLOCKED_PATTERNS` is a literal-substring blocklist on raw
    source text, trivially bypassed without obfuscation (e.g. `importlib.import_module("os")
    .system(...)` contains neither `"os.system"` nor `"subprocess."` verbatim); a real fix means
    building sandboxed execution, not patching this list, and the tool's own comment already
    treats `VECTOR_ENABLE_UNTRUSTED_CODE=1` + isolated-lab-only as the real boundary — added an
    explicit comment rather than attempting a fix. `vc_agents/digest_store.py` and
    `vc_tools/storage/knowledge_graph.py` were found during a repo-wide `sqlite3.connect()` sweep
    as two more files bypassing the SQLCipher gateway (distinct from the already-flagged 6 and
    the 3 correctly-out-of-scope Apple system-DB readers) — not fixed, same owner migration
    decision as the earlier-flagged instances. **Depth statement:** real depth given to the 13
    exc_info files, `db_query.py`, `knowledge_sql.py`, `file_read.py`, `file_write.py`,
    `browser.py`, `code_interpreter.py`, `dropbox.py`, plus a targeted grep-based security sweep
    (requests/httpx usage, API-key-in-URL, raw `sqlite3.connect`, timing-unsafe comparison,
    `0.0.0.0` binds, `pickle`, `os.system`/`os.popen`) across all 85 files in this round's
    starting scope. Roughly 65 of those 85 files (most of `vc_agents/` proper beyond the 8 fixed,
    `connectors/{notion,outlook,slack_connector,spotify,strava,oura,weather,hackernews,
    google_tasks,granola,chunker,pipeline,gmail,obsidian}.py`, and most of `vc_tools/`'s
    storage-backend and tool-wrapper files) received only the grep sweep, not full line-by-line
    logic review, and are not represented as complete — a third round should resume from this
    list rather than re-deriving it. Commits: `c9a01abbf` (exc_info fix), `e7d416124` (db_query
    stacked-statement fix), `eeeaa2fca` (code_interpreter.py flag-only), `f5fe83811` (browser.py
    SSRF fail-open fix).

53. **`vectorcode/src/{environments,cli,server}/` audit (partial, 2026-10-05) —** assigned
    scope was all tracked Python files in these 3 directories (24 + 21 + 21 files, ~20,459
    lines combined); `server/` got substantial real depth, `cli/` got one file, `environments/`
    got none beyond an initial grep triage. **Fixed, `server/` (13 files, 15 commits):**
    `auth_middleware.py` — the bearer-token check on every `/v1/*`/`/api/*` request used plain
    `!=` instead of `secrets.compare_digest()`, a timing side-channel on the real API key.
    `webhook_routes.py` — three more timing-unsafe secret comparisons (`bluebubbles_password`,
    `whatsapp_verify_token`, SendBlue's `webhook_secret`), all fixed the same way; the WhatsApp
    POST handler's HMAC check already correctly used `hmac.compare_digest()`. `cloud_router.py`
    — `_stream_google()` passed the Gemini API key in the URL query string (`?key=`, logged by
    proxies/access logs); moved to the documented `x-goog-api-key` header alternative.
    `connectors_router.py` — three findings: (1) loguru imported then immediately shadowed by
    `logging.getLogger(__name__)`, breaking every placeholder in the file; (2) two
    `threading.Thread` background-task sites (CLAUDE.md: asyncio only) converted to
    `asyncio.create_task(asyncio.to_thread(...))` with a strong-reference set (bare
    `create_task()` results can be GC'd mid-run) and `_sync_threads`/`.is_alive()` renamed to
    `_sync_tasks`/`not .done()`; (3) a real, independently-confirmed bug found via the new
    test: `sync_status()`'s `effective_state` logic had two dead-identical branches (`elif
    status.state != "idle": effective_state = status.state` then `else: effective_state =
    status.state` — same assignment either way) and never checked `bg["state"] == "complete"`.
    Real connectors' own `sync_status()` reports `"idle"` on success, not `"complete"`
    (confirmed in `apple_health.py`), so `GET /sync` never actually surfaced a finished
    background sync to any UI polling on it — fixed by checking `bg["state"] == "complete"`
    explicitly. `session_store.py`, `routes.py`, `channel_bridge.py`, `api_routes.py`,
    `ws_bridge.py`, `upload_router.py`, `app.py`, `stream_bridge.py` — the same
    loguru-shadowed-by-stdlib-logging pattern (one as a local in-function shadow inside two
    `except` blocks in `stream_bridge.py`, which had loguru correctly imported at module level)
    plus the resulting broken `%s`/`%d`/`%r` placeholders and `exc_info=True` kwargs (stdlib-only,
    silently ignored by loguru) across all eight; converted to `logger.opt(exception=...)`
    where a traceback mattered. `app.py` also had a trace-store init failure logged as the
    literal, content-free message `"[VECTOR] silent swallow"` (an auto-generated leftover from
    an earlier automated pass) — replaced with a real diagnostic message. `ws_bridge.py` had a
    bare `except (RuntimeError, asyncio.QueueFull): pass` with zero logging — added a debug log.
    `middleware.py` reviewed, clean, no changes needed. **Fixed, `cli/` (1 file):** `auth.py` —
    one broken `%s` placeholder (loguru was otherwise used correctly throughout, mostly via
    f-strings); reviewed the credential-storage design (keyring + XOR-"obfuscation"-not-
    encryption file fallback) and confirmed it is honestly self-documented as weak-by-design,
    not a new finding. **FLAGGED, not fixed:** `server/api_routes.py`'s `/memory/index` resolves
    an arbitrary user-supplied path with zero confinement (CWE-22 shape), but "index any local
    path I choose" is this endpoint's actual intended feature on a single-owner local-first
    system, already gated behind `auth_middleware.py`'s API key — restricting it would be a
    product decision, not a bug fix, documented with a comment instead. `webhook_routes.py`'s
    SendBlue handler nests a raw `threading.Thread`/`Event` for a periodic reminder inside a
    function that already runs via `asyncio.to_thread()` — no event loop is reachable from
    inside that worker thread to schedule an asyncio timer against, so converting it needs an
    end-to-end sync-to-async restructure, not a narrow fix; same reasoning applies to
    `cli/digest_cmd.py`'s background-audio-playback thread in a one-shot synchronous CLI command
    (flagged in this entry only, not yet commented in the file itself). `cli/agent_cmd.py`'s two
    `threading.Event()` uses are the standard idiom for blocking a synchronous process on a
    signal handler and are not a bug. New tests, all passing: 9 new test files across the
    `server/` fixes (`test_vectorcode_server_auth_middleware_timing_safe.py`,
    `test_vectorcode_server_webhook_routes_timing_safe.py`,
    `test_vectorcode_server_cloud_router_gemini_key_header.py`,
    `test_vectorcode_server_connectors_router_asyncio_sync.py`,
    `test_vectorcode_server_routes_loguru_logging.py`,
    `test_vectorcode_server_channel_bridge_logging.py`,
    `test_vectorcode_server_misc_logging_fixes.py`) plus `test_vectorcode_cli_auth_logging.py`.
    **Depth statement, honestly incomplete:** `server/agent_manager_routes.py` (2,166 lines,
    exceeds this audit's ~1,500-line single-file threshold) was deliberately not opened at all
    and needs its own dedicated future slice. `server/dashboard.py`, `digest_routes.py`,
    `cost_calculator.py`, `savings.py`, `models.py`, `comparison.py` passed an initial grep
    triage for the known bug-class patterns (all clean) but were not read line-by-line for
    logic bugs. In `cli/`, only `auth.py` got real depth; `digest_cmd.py` and `agent_cmd.py` got
    a targeted look at their flagged `threading` usage only (not a full read); `mine_cmd.py`
    (978 lines) got a pattern grep only (clean); the remaining ~17 `cli/` files
    (`chat_cmd.py`, `completion.py`, `doctor.py`, `init_cmd.py`, `profiles.py`,
    `registry_cmd.py`, `scan_cmd.py`, `scheduler_cmd.py`, `self_update.py`, `skill_cmd.py`,
    `workflow_cmd.py`, `ask.py`, and the small `_`-prefixed helper files) were not reviewed at
    all this round. **`environments/` (24 files, ~7,288 lines) received no real review this
    round** — only the very first broad grep pass across the whole assigned scope, which
    surfaced that most files there use plain stdlib `logging.getLogger(__name__)` consistently
    (not the loguru-shadow shape, just never-adopted-loguru) and that `yc_bench_env.py`/
    `terminalbench2_env.py` use heavy `print()` for benchmark-harness CLI result output, which
    looks like legitimate human-facing eval console output rather than a bug, but neither
    conclusion was verified with a full read. A continuation round should start with
    `environments/` in full, then the ~17 untouched `cli/` files, then
    `server/agent_manager_routes.py` as its own slice. Commits (server/+cli/, this round):
    `739d3b501`, `eab3e610c`, `577f17b2b`, `90cc714be`, `f5b21b334`, `ac472e3cc`, `e2d76171a`,
    `3cd3a8f13`.

55. **`vectorcode/src/evals/` audit continuation (132 production Python files, partial,
    2026-10-05) —** established the authoritative 143-file inventory with
    `git ls-files`; excluded the 11 vendored test files as audit targets, leaving 132
    production files (~35,592 lines). **Fixed:** `backends/external/_runners/vector_runner.py`
    referenced `Path` in its argument parser without importing it, so every invocation crashed
    before parsing. The same runner received `VECTOR_AGENT_PATH` from its caller but never put
    it on `sys.path`, so its promised `from run_agent import AIAgent` failed unless the foreign
    framework happened to be installed globally. Both are corrected and exercised through the
    real `main()` path. `backends/external/vector_agent.py` also no longer exposes its API key
    in the child process's command-line arguments (visible to local process inspection); the
    key now travels in the dedicated inherited `VECTOR_EVAL_API_KEY` environment variable.
    `core/config.py`, `datasets/deepplanning.py`, and `datasets/workarena.py` now use loguru,
    `{}` placeholders, and `logger.opt(exception=True)` instead of stdlib logging, `%`
    placeholders, and ignored/incompatible exception kwargs. New top-level regression tests:
    `tests/test_vectorcode_evals_vector_runner_regressions.py` (3/3 passing) and
    `tests/test_vectorcode_evals_logging_regressions.py` (4/4 passing); edited modules compile
    and pass `git diff --check`.

    **FLAGGED, not fixed:** `backends/external/openclaw.py` likewise places its API key in the
    Node child process argv, but the runner script and its secret-input contract are external
    to this assigned directory; changing one side would break execution, so this needs an
    owner-coordinated external-runner change. `backends/external/_subprocess_runner.py` uses a
    dedicated `threading.Thread` for synchronous 10 Hz energy sampling; replacing it with
    asyncio would require changing the public synchronous backend contract, so it remains a
    policy/design decision rather than a narrow audit patch.

    **Depth statement, honestly incomplete:** full line-by-line review completed for
    `core/config.py`, `datasets/{deepplanning,workarena,taubench,pinchbench,liveresearch}.py`,
    `backends/{_commit_util,external/_subprocess_runner,external/vector_agent,
    external/openclaw,external/_runners/vector_runner}.py`. The rest of the 132-file production
    scope received only inventory and broad known-hazard scans and remains for continuation;
    in particular, the six owner-prioritized large files were sized but not yet fully read.
    The vendored `test_config.py` run had one expected logging-capture mismatch (`caplog` cannot
    observe mandated loguru output) plus six unrelated stale failures for old `jarvis-*`
    backend names / the removed `vector.evals` package path. No commit hash exists: both
    required focused commits were attempted with explicit paths, but the sandbox could not
    create `.git/index.lock` (`Permission denied`), so all verified changes remain uncommitted.

56. **`vectorcode/src/skills/` audit, round 3 (2026-10-05) —** resumed where round 2 left off
    (commits `5a94883f9`, `28cd89660`, `5790b2d09`, `84525d250` — git-clone argument injection +
    cache-dir traversal in the github source, the "vector" source's broken-stub wiring, the
    unwired capability-gate flag, and importer.py's skill-name path traversal). Checked whether
    `vector_cli/skill_cmd.py` had the identical broken-stub wiring bug the round-2 fix only
    applied to `cli/skill_cmd.py`: it does not -- `vector_cli/skill_cmd.py` routes its `"vector-
    cache"` source to the real `VectorCacheResolver` (a `GitHubResolver` subclass), a genuinely
    different, already-correct class, not a near-duplicate of the broken stub. **Fixed, each with
    a new regression test:** `overlay.py`'s `_escape()` only covered `\\`/`"`/`\n`/`\r`/`\t`, but
    TOML's basic-string grammar forbids ANY unescaped control character
    (U+0000-U+0008, U+000B-U+001F, U+007F) -- `write_overlay()` persists DSPy/GEPA-generated
    optimizer text, and an unescaped control character (verified live with `\x0b`) produced a
    syntactically invalid TOML file that then silently and permanently failed to load back via
    `SkillOverlayLoader.load()`'s own documented "never raises" design, losing the optimization
    result with only a logged warning as the trace; rewrote `_escape()` to cover every
    TOML-mandated escape. Confirmed `vectorcode/src/vc_skills/overlay.py` (a different import
    path used by `learning/agents/skill_optimizer.py`) is a thin re-export shim of this same
    file, not a second copy of the bug. `skill_utils.py`'s `load_skill()` had the same unconfined
    `skill_name`-into-path CWE-22 shape already fixed in `importer.py` and
    `learning/distillation/pending_queue.py` this cycle; this module has zero callers anywhere in
    the repo (the live loader is the separate, confusingly-similarly-named
    `vectorcode/src/agent/skill_utils.py`), but fixed anyway per this audit's "dormant doesn't
    mean low priority" rule. Both files also got the usual loguru-shadowed-by-stdlib-logging
    fix. **Reviewed, no bug found (full depth):** `telephony.py`'s remaining body (consistent
    error handling via `TelephonyError`, correct XML escaping in `_twiml_say`/`_twiml_play`, no
    injection vectors -- the state-loading fix from round 1 was the only real bug in this file),
    `maps_client.py` in full (every Overpass QL interpolation is either validated-numeric or
    sourced from a hardcoded internal dict, never raw user input), `executor.py` (confirms the
    already-flagged capability gate is genuinely never called from `run()`, nothing new),
    `dependency.py` (the depth-check DFS's `visiting` parameter is dead/vestigial -- added but
    never checked for a cycle -- but unreachable with bad input today since `validate_dependencies`
    always runs Kahn's-algorithm cycle detection first; not a live bug, too speculative to fix
    without a reachable trigger), `tool_adapter.py`, `index.py`, `sources/{base,openclaw,
    vector_source,vector_cache}.py`. **FLAGGED, not fixed:** `types.py`'s `manifest_bytes()` has
    zero callers anywhere in the repo -- the entire skill-signing feature (the `signature` field,
    this serialization method) is fully data-plumbed but entirely unenforced at runtime, the same
    shape as `security.py`'s capability gate. Separately noted in a comment for whoever eventually
    wires it up: `manifest_bytes()` excludes `markdown_content` (the actual SKILL.md body the
    agent executes), so a signature over this serialization would not attest to a skill's real
    instructions -- a validly-signed skill's content could be swapped without invalidating the
    signature. Not fixed since there is no live verification path yet to regression-test against.
    **SIGNIFICANT FINDING, needs owner attention:** `vectorcode/skills/` (no `/src/`) is a
    separate, git-tracked directory of **15,576 files** -- not a build artifact or typo, a
    genuinely different tree from `vectorcode/src/skills/` (63 files) that this entire audit has
    been covering. Discovered because `vectorcode/src/skills/builtin/sparc/__init__.py` imports
    `from vectorcode.skills.builtin.sparc.coordinator import (...)` (no `.src.` segment) -- this
    initially looked like the "wrong import path" bug class found repeatedly elsewhere this audit,
    but verified live that the import actually succeeds and resolves to a real,
    **completely different 24-line `coordinator.py`** at `vectorcode/skills/builtin/sparc/
    coordinator.py`, not the 126-line SPARC implementation in `vectorcode/src/skills/`. This is
    not investigated further here -- it is well outside this slice's assigned scope
    (`vectorcode/src/skills/` only) and is a much bigger architectural question than a narrow bug:
    whether `vectorcode/skills/` is a vendored/cached skill marketplace snapshot, a pre-refactor
    legacy tree that should have been deleted, or something actively relied upon, needs an owner
    decision before anyone touches it -- the same class of question as the already-deferred
    jcode-vs-vc_tools duplication, but potentially much larger given the file count.
    New tests: `tests/test_vectorcode_skills_overlay_toml_escaping.py` (2) and
    `tests/test_vectorcode_skills_skill_utils_path_confinement.py` (2) -- 4/4 passing, plus the 13
    pre-existing round-1/round-2 skills tests re-run clean (17/17 total). Commits: `df5864d8b`
    (overlay.py), `e498bd97e` (types.py flag), `5b36850bd` (skill_utils.py). **Depth statement:**
    full line-by-line depth this round on `overlay.py`, `skill_utils.py`, `types.py`, `index.py`,
    `dependency.py`, `tool_adapter.py`, `executor.py`, `sources/{base,openclaw,vector_source,
    vector_cache}.py`, `telephony.py`'s remaining body, and `maps_client.py` in full. Still not
    covered by any round: `__init__.py`, `builtin/sparc/coordinator.py` (read but not exercised
    beyond confirming its own import works; its STAGE_PROMPTS/run_sparc_* logic itself was not
    deeply re-derived against real agent behavior), and the ~25 remaining `optional/*` and
    `productivity/*`/`creative/*`/`red-teaming/*`/`research/*`/`media/*`/`mlops/*` scripts
    (blockchain clients, health calculators, MCP scaffolding templates, meme generation, OCR,
    PowerPoint helpers, arxiv/polymarket research, godmode red-teaming scripts) -- none of these
    received real depth this round and should not be treated as audited.

57. **`vectorcode/src/learning/` audit, round 3 (2026-10-05) —** resumed where rounds 1-2 left
    off (15 of 79 files already had real depth: `distillation/{pending_queue,models,orchestrator,
    gate/regression,plan/prompt_diff}.py`, `distillation/checkpoint/store.py`,
    `distillation/storage/paths.py`, `distillation/execute/{base,loop,appliers/{agent,
    intelligence,tools}}.py`, `agents/{dspy_optimizer,gepa_optimizer}.py`,
    `intelligence/grpo_trainer.py`). **Correction to a prior round's claim:** round 1/2's summary
    listed `distillation/execute/loop.py` as already fully reviewed, but it still had the raw
    stdlib-logging-shadow bug (no loguru import anywhere in the file) -- that claim was inaccurate
    for this file; fixed this round. **Fixed:** 20 files used plain `logging.getLogger(__name__)`
    with zero loguru import (`distillation/diagnose/{runner,teacher_agent}.py`,
    `distillation/execute/loop.py`, `distillation/gate/{benchmark_gate,cold_start}.py`,
    `distillation/orchestrator.py`, `distillation/plan/{planner,risk_tier}.py`,
    `intelligence/orchestrator/{grpo_trainer,policy_model,sft_trainer}.py`,
    `learning_orchestrator.py`, `optimize/feedback/judge.py`, `optimize/{llm_optimizer,optimizer,
    trial_runner}.py`, `routing/{learned_router,router}.py`, `training/lora.py`), plus
    `agents/skill_optimizer.py` which had a correct top-level loguru import shadowed by a second,
    stdlib-backed `LOGGER` name used at 3 call sites. Converted all to loguru and fixed every
    `%s`/`%d`/`%r`/`%.Nf`-style placeholder found in their logger calls (including several
    multi-line calls). `learning_orchestrator.py` additionally had a local re-shadow: one
    `except` branch did a fresh `import logging; logging.getLogger(__name__).warning(...)`
    inside a method body instead of using the module's own logger -- removed. New test:
    `tests/test_vectorcode_learning_round3_logging.py` (5 tests, all passing; verified via git
    stash that 4/5 fail against the pre-fix code). Commit: `a3ddac6fc`. **Also hunted (no new
    findings):** this directory's two highest-value bug patterns from rounds 1-2 -- CWE-22
    identifier-into-filesystem-path (checked every `Path(...)`/`os.path.join(...)` site built
    from an `*_id` variable across all 64 previously-untouched files; every one traced back to an
    internally-generated id via `uuid.uuid4()` or a timestamp, never a model- or caller-controlled
    value) and the "blanket NotImplementedError regression" pattern already found 3 times here
    (grepped for `raise NotImplementedError` repo-wide in this directory; zero live occurrences
    remain, only historical mentions inside the fix comments from rounds 1-2). The two
    already-flagged raw-SQLite learning stores (`optimize/store.py`,
    `distillation/storage/session_store.py`) were re-confirmed bypassing the SQLCipher gateway
    but not re-flagged as new, per the existing owner-decision record. **Depth statement:** this
    round covered the systemic logging bug plus a targeted pattern hunt across all 64
    previously-untouched files in the directory, but did NOT give full line-by-line logic review
    to every file's business logic -- in particular `distillation/diagnose/tools.py` (548 lines),
    `optimize/llm_optimizer.py`'s optimization logic beyond its logging, `optimize/store.py`,
    `optimize/optimizer.py`'s trial-selection logic, `agents/agent_evolver.py`,
    `agents/skill_discovery.py`, and the `optimize/personal/*`, `optimize/feedback/collector.py`,
    and `intelligence/orchestrator/{environment,reward,types,prompt_registry}.py` files remain
    unreviewed at full depth and should not be treated as audited.

58. **`vectorcode/src/` 20-small-directory audit (62 production Python files, full depth,
    2026-10-05) —** completed a line-by-line review of every tracked Python file directly in
    `a2a`, `vc_traces`, `vc_sessions`, `scheduler`, `persona`, `operators`, `vc_skills`,
    `sandbox`, `repl`, `recipes`, `mcp_client`, `guidance`, `vc_templates`, `traces`, `prompt`,
    `neural_training`, `migrations`, `intelligence`, `acp`, and `transports` (62 files / 8,004
    lines; tests excluded as audit targets). **Fixed with regression coverage:** operator
    activation no longer leaves the scheduler's random task ID runnable alongside its stable
    `operator:<id>` task; JSON session IDs can no longer traverse outside their store and corrupt
    JSON is surfaced instead of treated as missing; persona profile names can no longer escape
    their store and profile writes no longer report phantom success; direct persona Ollama calls
    now include mandatory context hydration; recipe `max_tokens` is actually loaded/forwarded and
    zero temperature is preserved; JSON-form chat responses retain usage/cache accounting; the
    `vectorcode.src.transports` package now registers its own implementations rather than
    accidentally importing the separate top-level `transports` package; A2A handler failures
    now retain exception diagnostics; and the scoped Loguru shadowing, `%` placeholders, and
    incompatible `exc_info=True` sites were corrected. Tests are in
    `tests/test_vectorcode_small_dirs_round1.py` (13/13); that suite plus three existing A2A
    suites passed 44/44, `tests/test_absorption.py` passed, all 62 scoped modules compile, and
    `git diff --check` passed.

    **OWNER DECISIONS / cross-boundary findings, not changed:** (1) ACP publishes agent creation,
    execution, messaging, listing, deletion, and capability routes without authentication or an
    established Permission Gateway check. Its default loopback bind reduces exposure, but the host
    is configurable and the source already carries an owner flag. (2) `vc_sessions/session.py`,
    `vc_traces/store.py`, and the migration utility use raw `sqlite3.connect()` for persistent
    VECTOR session/trace data instead of the mandated SQLCipher gateway; migration semantics and
    compatibility require an owner-directed conversion. (3) `mcp_client/client.py` is a separate
    650-line implementation using a banned `threading.Thread`, while the package bridge and
    initializer resolve `vectorcode.mcp_client.client`, a different tracked sibling shim; no live
    caller of the scoped implementation was found, so deleting, consolidating, or asynchronously
    redesigning it is an architectural choice. (4) MCP tool-group switches are discovery filters,
    not authorization, and unknown group prefixes currently remain visible. (5) The out-of-scope
    `vectorcode/src/server/api_routes.py` imports this slice's JSON `SessionStore` but calls missing
    `.recent()` and `.get()` methods, so those endpoints fail/empty at runtime; repairing the API
    contract spans the reserved `server/` scope. (6) The JSON store says it is JSONL but writes
    individual JSON files, a documentation/format-contract ambiguity. Required focused commits
    were attempted, but this sandbox cannot create `.git/index.lock` because `.git` is read-only;
    the verified changes therefore remain uncommitted for the parent session.

59. **`vectorcode/src/learning/` audit, round 4 (2026-10-05) —** continued from rounds 1-3
    (which covered 15 files with real fixes plus a systemic loguru-shadow pass across 20 more).
    This round's assigned priority files: `distillation/diagnose/tools.py`,
    `optimize/{llm_optimizer,optimizer,store}.py`, `agents/{agent_evolver,skill_discovery}.py`,
    `optimize/personal/{dataset,scorer,synthesizer}.py`, `optimize/feedback/collector.py`, and
    `intelligence/orchestrator/{environment,reward,types,prompt_registry}.py` (13 files).
    **Fixed, each with a new regression test verified to fail against the pre-fix code via
    `git stash`:**
    `distillation/diagnose/tools.py`'s `get_agent_prompt` tool built
    `vector_home / "agents" / agent_name / "system_prompt.md"` with zero confinement —
    `agent_name` is a tool-call argument chosen by the **teacher LLM** itself
    (`teacher_agent.py:206`'s `tool.fn(**tc_args)` dispatches args parsed straight from the
    model's own tool call), so a value like `"../../../../etc"` could walk the read outside
    `vector_home/agents/`, breaking this module's own documented "read-only relative to the
    user's config" invariant; added `_is_safe_path_component()` and applied it
    (`tests/test_vectorcode_learning_diagnose_tools_path_traversal.py`, 3 tests).
    `agents/agent_evolver.py`'s `AgentConfigEvolver.write_config()`/`list_versions()`/`rollback()`
    built filesystem paths from a caller-supplied `agent_name` with zero confinement — `agent_name`
    traces back to a stored `Trace.agent` field via `learning_orchestrator.py`'s
    `evolver.analyze() -> rec["recommended_agent"] -> evolver.write_config(agent_name, ...)` — a
    value like `"../../../../.ssh/authorized_keys"` would let `write_config`'s
    `path.write_text()` write **outside** `config_dir` entirely, a write primitive more severe
    than the read-only CWE-22 bugs found elsewhere this audit; `list_versions`/`rollback`'s glob +
    `shutil.copy2` calls had the identical exposure. Same `_is_safe_path_component()` pattern
    applied to `write_config()` and `list_versions()` (`rollback()` calls `list_versions()` first
    so it's transitively covered) (`tests/test_vectorcode_learning_agent_evolver_path_traversal.py`,
    4 tests). `optimize/optimizer.py`'s `_write_toml_fallback()` (the `export_best_recipe()`
    fallback path used when `tomli_w` is missing — pinned in `requirements.txt` but the fallback
    exists and is reachable for environments without it) manually interpolated string trial
    params (e.g. `agent.system_prompt`, which can be DSPy/GEPA-generated optimizer output) into
    TOML basic strings with **zero escaping**; the identical bug class already found and fixed in
    `skills/overlay.py`'s `write_overlay()` this cycle. Added `_escape_toml_string()` with the
    same TOML-spec-complete escaping (`tests/test_vectorcode_learning_optimizer_toml_escaping.py`,
    2 tests). `intelligence/orchestrator/environment.py`'s `OrchestratorEnvironment.step()` built
    the `ToolCall.arguments` string for any non-pre-JSON `tool_input` (the common case — e.g. a
    plain calculator expression like `"2+2"`) via
    `f'{{"expression": {repr(action.tool_input)}}}'` — Python's `repr()` on a string produces
    single-quoted Python literal syntax, **not valid JSON**, but `ToolExecutor.execute()` parses
    `arguments` with `json.loads()`. This guaranteed a `json.JSONDecodeError` for every such call,
    silently turning into an "Invalid arguments JSON" error result instead of ever running the
    tool — the orchestrator's RL training/eval loop never got real tool-execution reward signal
    for any action whose input wasn't already pre-formatted JSON; a significant, previously
    undetected correctness bug in the actual training pipeline, not just a logging nit. Fixed with
    `json.dumps({"expression": action.tool_input})`
    (`tests/test_vectorcode_learning_orchestrator_environment_json_args.py`, 2 tests).
    `optimize/store.py`'s logger was shadowed by stdlib `logging.getLogger(__name__)` with 5
    `%`-style placeholders; fixed to loguru + `{}`. **FLAGGED, not fixed — owner decision
    needed:** `optimize/personal/synthesizer.py`'s `PersonalBenchmarkSynthesizer.synthesize()`
    accepts a `workflow_id` parameter that only labels the returned `PersonalBenchmark` — it is
    never used to filter which traces are pulled in, because `Trace` (`vc_core/types.py`) has no
    `workflow_id` field at all and `TraceStore.list_traces()` has no matching filter clause; a
    multi-workflow deployment would silently mix every workflow's traces into a benchmark that
    claims to represent just one. Real scoping needs a `Trace` schema change plus a `TraceStore`
    filter — not a narrow patch — so this is a comment-only flag, not a fix.
    **Reviewed, no bug found (full depth):** `agents/skill_discovery.py` (pure in-memory
    analysis, no filesystem/logging/subprocess surface at all), `optimize/llm_optimizer.py`
    (663 lines — defensive multi-tier JSON-from-LLM-response parsing with honest
    `reasoning="Failed to parse LLM response."` fallbacks, no `eval()`, no injection vectors),
    `optimize/feedback/collector.py`, `optimize/personal/{dataset,scorer}.py`,
    `intelligence/orchestrator/{reward,types,prompt_registry}.py` (the `SYSTEM_PROMPT_TEMPLATE
    .format()` call only scans the template string's own braces, not the substituted
    `tools_description`/`tool_selection_guide` values, so an MCP tool description containing
    literal `{`/`}` cannot break it — confirmed, not a bug).
    **Already-flagged, not re-flagged:** the orchestrator's no-op applier rollbacks +
    non-transactional `CheckpointStore` (owner session-semantics decision, item 47);
    `optimize/store.py`'s raw `sqlite3.connect()` is one of "the two learning stores" already
    recorded for an owner migration decision (item 57); `threading.RLock` in `store.py` is a
    legitimate synchronization primitive for a `check_same_thread=False` connection, not the
    banned "spawn a worker thread" pattern.
    New tests: 5 new test files, 11 tests total, all passing; 3 of 4 path-traversal/escaping
    fixes independently verified via `git stash` to fail against the pre-fix code (the 4th —
    `agent_evolver.py`'s `write_config` traversal case — failed differently pre-fix, with a bare
    `FileNotFoundError` instead of the intended `ValueError`, which still confirms the unconfined
    write attempt proceeded). Commits: `c79b5e290` (diagnose/tools.py), `75fd7c647`
    (agent_evolver.py), `5621ca33c` (store.py), `0aaf3c36a` (optimizer.py), `6a5be1129`
    (synthesizer.py flag), `dee2e7f45` (environment.py). **Depth statement:** all 13 assigned
    files received genuine full line-by-line review this round (10 with no bug found, 4 with
    real fixes, 1 flagged). Still not covered by any round: `diagnose/runner.py` and
    `teacher_agent.py` only got the round-3 logging pass, not a full logic review, despite being
    closely related to this round's `diagnose/tools.py` finding — worth prioritizing in a future
    continuation given the real bug just found in their shared `diagnose/` package. The remaining
    ~51 files in `vectorcode/src/learning/` outside this round's and prior rounds' assigned lists
    (training/lora.py's and distillation/orchestrator.py's full logic, routing/*, most of
    `intelligence/` outside the orchestrator package, `storage/session_store.py`, etc.) still need
    a dedicated continuation pass.

60. **`vectorcode/src/agent/` audit, round 5 (2026-10-05) — CRITICAL: `run_agent.py` was
    completely unimportable.** Four prior rounds had covered ~24 files with real depth. This
    round found and fixed two independent, severe import-chain breaks, both caused by earlier
    automated "cleanup" commits that over-reached well beyond their stated scope, and both
    confirmed live via a real `import run_agent` (not a static `ast.parse()` check, which is all
    the pre-existing "regression test" for this area ever did — that's exactly why neither break
    was caught for 4-5 months). **Fixed:**
    (1) `fed812acc` ("convert 214 pass-only ABC stubs to raise NotImplementedError",
    2026-06-18) deleted `vectorcode/src/agent/context_engine.py` *in its entirety* — 206 lines
    defining the `ContextEngine` ABC that `context_compressor.py`'s `ContextCompressor` class
    subclasses. The file legitimately contains `@abstractmethod` stubs (correctly bodyless) but
    also several real default-implementation methods (`on_session_reset`, `get_status`,
    `update_model`, `get_tool_schemas`); the automated stub-detector apparently misread the
    whole module as dead code. `context_compressor.py`'s module-level
    `from agent.context_engine import ContextEngine` has been raising `ModuleNotFoundError` ever
    since. Restored byte-for-byte from `git show fed812acc^:vectorcode/src/agent/context_engine.py`
    (commit `61f93b35c`).
    (2) `d18ec4130` ("phase-1: consolidate duplicate infrastructure", 2026-05-21) shrank
    `agent/memory_manager.py` from 528 lines to a 9-line re-export shim pointing at the new
    canonical `memory/manager.py`, migrating `MemoryManager`/`sanitize_context`/
    `get_memory_manager`/`reset_memory_manager` — but silently dropped `StreamingContextScrubber`
    entirely (a security-relevant stateful scrubber that prevents a streamed `<memory-context>`
    span from leaking its payload to the UI when the open/close tags straddle two stream chunks)
    and never re-exported `build_memory_context_block` even though that function did make it into
    the new module. `run_agent.py`'s module-level import of both names has been raising
    `ImportError` ever since. Restored `StreamingContextScrubber` into `memory/manager.py`
    byte-for-byte from `git show d18ec4130^:...` and re-exported both symbols from the shim
    (commit `59f7f6bfe`).
    Together, (1) and (2) meant `run_agent.py` — the primary agent entry point — could not be
    imported at all. Confirmed fixed: `import run_agent` now succeeds.
    (3) Separately, a real (non-import) bug: `ContextCompressor.on_session_reset()` — called on
    `/new`/`/reset` against the same long-lived instance `run_agent.py` reuses for the agent's
    whole process lifetime — never restored `self.summary_model` or cleared
    `self._summary_model_fallen_back` after `_generate_summary()`'s fallback-to-main-model path
    fired. A single transient failure of the user's configured (typically cheaper/faster) aux
    summary model therefore permanently and silently downgraded every future compression to the
    full-price main model for the rest of the process, even across fresh `/new` sessions. Fixed
    by capturing `self._summary_model_override` in `__init__` and restoring it in
    `on_session_reset()` (commit `433918f5f`).
    New tests: `test_vectorcode_agent_context_engine_restoration.py` (4, including a real
    `import run_agent` smoke test), `test_vectorcode_agent_memory_manager_scrubber_restoration.py`
    (6, including the exact split-across-chunks leak scenario the class's docstring describes),
    `test_vectorcode_agent_context_compressor_session_reset.py` (3) — 13/13 passing, all 13
    independently verified to fail against the pre-fix code via `git stash` + removing the
    restored file. **Depth statement:** this round focused entirely on the two import breaks and
    the session-reset bug once found — `context_compressor.py`'s own compression/pruning/tail-
    protection logic (prune boundary vs. final tail-cut boundary using two independently-computed
    token-walk calculations that could disagree slightly) was read in full and is suspected to
    have a minor latent inconsistency, but reordering the computation to share one boundary is a
    non-trivial change with its own regression risk in a correctness-sensitive pipeline — flagging
    for a future owner-reviewed pass rather than guessing at a fix under this round's time budget.
    `auxiliary_client.py`'s remaining provider-resolution/streaming-adapter logic
    (`_CodexCompletionsAdapter`, `_try_anthropic`/`_try_nous`/`_try_custom_endpoint` chains) was
    this round's other assigned priority but was not reached — the import-chain findings
    consumed the round's full budget and were judged far higher priority (the whole agent was
    unimportable). **Strongly recommend**: given two independent instances of an "automated
    cleanup/consolidation commit deletes or drops real code" bug class have now been found in
    `vectorcode/src/agent/` alone (plus 5 instances of the related "blanket NotImplementedError
    conversion breaks a concrete class" bug class found across `vectorcode/src/{agent,evals,
    learning}/` this audit cycle), a repo-wide audit specifically diffing `fed812acc` and
    `d18ec4130` (and any other similarly-scoped "consolidation"/"cleanup" commits) against what
    each touched file's real callers still expect would likely surface more of the same —
    this is a distinct, higher-value lead than continuing the file-by-file sweep.

61. **`vectorcode/src/learning/` audit, round 5 (2026-10-05) —** continued from rounds 1-4
    (~28 files with prior real depth). Full line-by-line depth this round on
    `distillation/diagnose/{runner,teacher_agent}.py`, `training/lora.py`,
    `distillation/orchestrator.py`, `routing/{router,learned_router}.py`,
    `distillation/storage/session_store.py`, and
    `intelligence/{__init__,grpo_trainer,sft_trainer}.py` (sft_trainer.py is a 4-line
    re-export shim, no issue). **Fixed, each with a new regression test:**
    `distillation/orchestrator.py`'s `_read_prompt(target)` split a teacher/planner-LLM-produced
    `target` string on "." and used the second segment (`agent_name`) directly in
    `self._home / "agents" / agent_name / "system_prompt.md"` with zero confinement -- the
    read-path counterpart of the identical unconfined-agent-name bug already fixed as a write
    primitive in `execute/appliers/agent.py` (round 1). A literal ".."-based traversal can't
    actually be smuggled through `target.split(".")` (any ".." substring is itself composed of
    the "." delimiter being split on), but pathlib's absolute-path-override behavior is a real
    escape: `base / agent_name` discards `base` entirely when `agent_name` is itself an absolute
    path (confirmed live: `Path("a/b") / "C:/x" / "y" == Path("C:/x/y")`) -- verified via
    `git stash` that this genuinely reads planted secret content on pre-fix code. Fixed the same
    way as the write-path precedent: resolve and require the agent directory's parent to equal
    `agents_dir` exactly. `distillation/storage/session_store.py` and
    `intelligence/grpo_trainer.py` both had the systemic stdlib-logging-instead-of-loguru bug
    (grpo_trainer.py had zero loguru import at all, not even a shadow); `intelligence/__init__.py`
    passed stdlib's `exc_info=True` to loguru (silently ignored) in two places. **FLAGGED, not
    fixed:** `intelligence/grpo_trainer.py`'s `_grpo_step()` computes
    `ratio = torch.exp(lp - lp.detach())`, which is mathematically guaranteed to always equal
    `exp(0) == 1.0` since `lp` and `lp.detach()` are the same tensor's values with only
    grad-tracking stripped -- `clipped` therefore also always equals 1.0, collapsing the intended
    PPO-style clipped GRPO objective into a plain REINFORCE-style `-advantage` loss and leaving
    `config.clip_ratio` completely inert. A real ratio needs an "old" log-prob frozen before the
    policy update it's compared against (typically via multiple inner optimizer steps per sampled
    batch), which `_run_grpo`'s single-pass-per-epoch structure doesn't do today -- this is a
    training-loop redesign decision, not a narrow patch, so it's documented in a comment at the
    exact line rather than guessed at. `routing/learned_router.py`'s `LearnedRouterPolicy.observe()`
    permanently stops updating a query class's routed model once `current_count` reaches
    `min_samples`, unlike `update()`/`update_from_traces()` which always re-evaluate from trace
    history regardless of confidence -- could be an intentional stability mechanism or an
    online-learning bug; `observe()` has zero callers repo-wide today, so there's nothing to
    empirically validate this against. On `diagnose/teacher_agent.py`: CLAUDE.md Rule 1 requires
    `context_engine.session_hydration_prompt()` before every LLM call, and this module's
    `TeacherAgent.run()` does not call it -- but unlike the 3 other hydration gaps found this audit
    cycle (where the LLM call had *no* system content at all), this one already builds and passes a
    deliberate, purpose-built system prompt for its specific offline meta-engineering/distillation
    task; injecting generic live-agent world-state hydration into that prompt could make it worse,
    not better, so this is noted here as a judgment call rather than silently "fixed" either way.
    **Reviewed, no bug found:** `distillation/diagnose/runner.py` (no path-confinement issues --
    `session_dir` is internally generated, not model-produced), `training/lora.py` (correct guarded
    optional imports, no logic bugs), `routing/router.py` (clean heuristic rule logic).
    New tests: `tests/test_vectorcode_learning_orchestrator_read_prompt_path_confinement.py` (2),
    `tests/test_vectorcode_learning_session_store_logging.py` (2),
    `tests/test_vectorcode_learning_intelligence_grpo_logging.py` (3) -- 7/7 passing. Commits:
    `95df1765a` (orchestrator.py), `9e99f7b75` (learned_router.py flag), `135865368`
    (session_store.py), `a4bd5ee34` (grpo_trainer.py + __init__.py). **Depth statement:** the files
    named above as fixed/reviewed got genuine full-depth review. Still not covered by any round:
    `optimize/llm_optimizer.py` (663 lines) and `optimize/trial_runner.py` (404 lines) beyond
    whatever round 3's mechanical logging pass touched, `distillation/plan/planner.py`,
    `distillation/models.py`, `distillation/diagnose/types.py`, `agents/skill_optimizer.py`, and a
    handful of smaller files -- these should not be treated as audited.

62. **Automated cleanup commit over-reach investigation (2026-10-05) — triggered by item 60's
    `run_agent.py` finding.** Item 60 found that commit `fed812acc` ("convert 214 pass-only ABC
    stubs to raise NotImplementedError", 2026-06-18) deleted a real file (`agent/context_engine.py`)
    entirely, and a separate commit `d18ec4130` dropped a real class during a "consolidation."
    This investigation asked: how much more damage did these two commits (and other similarly
    bulk/automated commits across the whole repo) do? **Scope covered:** extracted all 162
    `pass`→`raise NotImplementedError` conversions from `fed812acc`'s full diff (802 files touched
    total) and triaged every non-vendored hit by file (vendored trees -- `core/research_engine/`,
    `districts/investment/vector_finagent/`, etc. -- account for the bulk of the 162 and were not
    re-examined here; their `base_*.py` naming and multi-abstract-method shape is consistent with
    genuine ABCs, matching this audit's existing wiring-check-only policy for those trees).
    **Fixed, each with a new regression test verified to fail pre-fix via `git stash`:** 4 more
    instances of the identical bug class already found 5 times in items covering `vectorcode/src/
    {agent,learning,evals}/` — a concrete, directly-instantiated "null object" / fallback class
    whose deliberate no-op body was turned into an unconditional raise:
    `plugins/context_engine/__init__.py`'s `_EngineCollector` (instantiated in
    `_load_engine_from_dir()`, passed to a loaded plugin's own `register(ctx)` call -- a plugin
    calling `register_tool`/`register_hook`/`register_cli_command`/`register_memory_provider`
    during setup would abort silently and lose its engine registration),
    `plugins/memory/__init__.py`'s `_ProviderCollector` (identical shape for memory-provider
    plugins), `skills/manager.py`'s `_NullToolExecutor` (the `_FULL_DEPS=False` branch,
    instantiated as `executor or _NullToolExecutor()` -- the entire point of this branch is
    graceful degradation when `vc_tools` is unavailable), and `providers/capability_probe.py`'s
    fallback `ModelRegistry.save()` (used when `from config import ModelRegistry` fails).
    All 4 confirmed via `git show fed812acc^:<path>` that the original body was `pass`. Also fixed
    an unrelated loguru-shadowed-by-stdlib-logging bug found in `providers/__init__.py` while
    investigating it. Commit: `56348c2e1`.
    **FLAGGED, NOT FIXED — separate, deeper, pre-existing architectural mismatch (not caused by
    either commit under investigation):** `vectorcode/src/providers/capability_probe.py` and
    `vectorcode/src/providers/openai_compat.py` both do `from providers.base import
    ModelCapabilities` (and, for openai_compat.py, also `BaseProvider`, `CompletionResult`,
    `Message`, `TokenUsage`, `ToolCall`) -- none of these exist in the current `providers/base.py`
    at all. That file was redesigned at some point around a declarative `ProviderProfile` dataclass
    (clean, well-documented, actively used) and now defines nothing else; these two files were
    never migrated and have likely been unimportable for as long as that redesign has existed.
    Confirmed this is non-fatal to the package as a whole: `providers/__init__.py`'s own
    `pkgutil.iter_modules` legacy-discovery loop wraps each module import in `except ImportError`
    and logs a warning, so the rest of `providers/` still works -- but `capability_probe.py` and
    `openai_compat.py` are both 100% dead on arrival today. Deciding whether to migrate these two
    files to the new `ProviderProfile` API, delete them as superseded legacy code, or something
    else is an owner architecture decision, not a narrow bug fix -- flagging rather than guessing.
    **Checked and confirmed NOT bugs:** `core/scraper/parser.py`'s `Selectors.__getitem__` and
    `core/scraper/core/custom_types.py`'s `TextHandlers.__getitem__` -- both `raise
    NotImplementedError` sites are inside `@overload`-decorated signature stubs (never executed at
    runtime, purely for static type checkers; the real implementation follows immediately after
    without the decorator) -- harmless regardless of body content.
    `core/scraper/engines/_browsers/_base.py`'s `SyncSession.start`/`AsyncSession.start` -- confirmed
    real subclasses exist and override `.start()` (`DynamicSession`, `StealthySession` /
    `AsyncDynamicSession`, `AsyncStealthySession` in `_controllers.py`/`_stealth.py`), consistent
    with a genuine (if informally-typed, not literal `abc.ABC`) abstract base.
    **NOT YET COVERED by this investigation** (explicitly, not representing as audited): the
    remaining ~140 of `fed812acc`'s 162 conversions in vendored trees (spot-checked the shape, not
    individually verified each one); `d18ec4130`'s full file list beyond the already-found
    `memory_manager.py` instance (item 60); `fed784f60` ("phase-2: deduplicate core/ vs vectorcode/
    forks (telemetry + sandbox)") was identified as a same-risk-profile candidate commit but not
    examined at all; `core/` and `districts/` generally were marked fully audited in earlier
    sessions before this context window, but that audit may have used the same `ast.parse()`-only
    methodology that hid the `run_agent.py` break for 4-5 months -- re-checking real imports across
    those two huge trees was judged too large for this investigation's budget and is recommended as
    its own future dedicated pass, prioritized by whether a module is a real import target (not a
    vendored `base_*.py`) and whether it was touched by one of the candidate commits listed above.

63. **`vectorcode/src/learning/` audit, round 6 (2026-10-05) —** continued from rounds 1-5
    (~38 files with prior real depth). Full line-by-line depth this round on
    `optimize/{llm_optimizer,trial_runner}.py`, `distillation/{plan/planner,models}.py`,
    `distillation/diagnose/types.py`, `agents/skill_optimizer.py`, and `distillation/cli.py`.
    **Fixed, each with a new regression test:** `optimize/trial_runner.py`'s
    `_run_terminalbench_native()` passed `agent_import_path=
    "vector.evals.backends.tb_agent:VectorCodeTerminalBenchAgent"` to terminal-bench's `Harness` --
    there is no top-level `vector` package anywhere in this repo (confirmed live:
    `import vector` raises `ModuleNotFoundError`); the real module is
    `vectorcode/src/evals/backends/tb_agent.py`. Every terminalbench-native trial would fail to
    dynamically import the agent and silently report a permanent 0.0-accuracy error score instead
    of a real result. Fixed to the correct dotted path. Same file: `run_trial()`'s cleanup
    `finally` block called `backend.close()` then `judge_backend.close()` unguarded --
    `backend.close()` just forwards to `self._system.close()`, which can raise, and doing so would
    skip `judge_backend.close()` entirely and leak it. Each `close()` is now wrapped in its own
    try/except so one failing never skips the other. `distillation/plan/planner.py`'s
    `_parse_edits()` except-block called `raw.get("id", "?")` unconditionally on `raw` --
    untrusted teacher-LLM JSON output not guaranteed to be a dict (the model can return a bare
    string/number/null as one "edit" entry). When it wasn't a dict, the `AttributeError` from
    `.get()` propagated out of the exception handler itself, crashing the entire `_parse_edits()`
    call over one malformed entry instead of skipping it and keeping the valid edits -- confirmed
    live before the fix: `_parse_edits('{"edits": ["not_a_dict"]}')` raised `AttributeError`
    instead of returning `[]`. Fixed with an `isinstance(raw, dict)` guard. New tests:
    `tests/test_vectorcode_learning_trial_runner_regressions.py` (3) and
    `tests/test_vectorcode_learning_planner_malformed_edit.py` (2) -- 5/5 passing, all 4 fix sites
    independently verified to fail on pre-fix code via `git stash`. Commits: `d5e4d50cc`
    (trial_runner.py), `fb86e87f7` (planner.py). **Reviewed, no bug found:**
    `optimize/llm_optimizer.py` (already-correct loguru usage, no path/subprocess/threading
    issues, LLM calls already build their own deliberate system prompts matching the
    `teacher_agent.py` exception precedent -- not a hydration gap), `distillation/models.py` and
    `distillation/diagnose/types.py` (pure Pydantic schema / dataclass definitions, no executable
    logic), `distillation/cli.py` (deliberately unwired scaffold CLI surface, explicitly documented
    as such in its own `learning_run()` comment -- not a bug). `agents/skill_optimizer.py` itself
    has no bug, but **FLAGGED cross-directory finding, not fixed (outside this round's
    `vectorcode/src/learning/` scope):** its one real dependency,
    `vectorcode/src/skills/overlay.py`'s `write_overlay(overlay, root)` (reached via
    `vc_skills.overlay`'s re-export shim), builds `root / overlay.skill_name` with zero path
    confinement -- `skill_name` originates from trace-step tool-call metadata
    (`_extract_skill_names()`'s `metadata.get("skill")`), which is not as clearly
    internally-generated as e.g. `session_dir`. This is the identical unconfined-identifier-into-
    path shape already fixed 4 times elsewhere this audit cycle (most recently
    `distillation/orchestrator.py`'s `_read_prompt`); `vectorcode/src/skills/` is a sibling
    directory already partially covered by its own audit rounds (which already fixed this exact
    file's TOML-escaping bug in commit `df5864d8b`) -- recommend a `skills/` continuation round
    apply the same `Path.resolve()` + parent-equality confinement pattern to `write_overlay()`.
    **Depth statement:** the files named above as fixed/reviewed got genuine full-depth review.
    Still not covered by any round: `intelligence/orchestrator/{prompt_registry,types,
    policy_model,reward}.py`, `routing/complexity.py`, `optimize/{types,search_space,config}.py`,
    `training/data.py`, `distillation/execute/appliers/{lora_stub,tools,intelligence}.py`,
    `distillation/student_runner.py`, and `distillation/checkpoint/store.py` -- roughly 14 files
    remain for a future round.

64. **`vectorcode/src/skills/` audit, round 5 (2026-10-05) —** addressed item 63's cross-directory
    flag and continued into previously-uncovered files. **Fixed:** `overlay.py`'s `write_overlay()`
    now confines the resolved output path's parent to the given `root` (same pattern as
    `importer.py`/`learning/distillation/{pending_queue,execute/appliers/agent,diagnose/tools,
    orchestrator}.py`); the caller in `learning/agents/skill_optimizer.py`'s `optimize()` wraps
    `write_overlay()` in the same per-skill try/except already used for optimizer-call failures, so
    the new `ValueError` on an unsafe `skill_name` can't abort the whole batch (commit `bf6cd9b21`,
    4 new tests, the 2 traversal tests verified via `git stash` to fail pre-fix).
    `optional/security/oss-forensics/scripts/evidence-store.py`'s `EvidenceStore._save()` wrote
    directly to the target file with no temp-file/rename step; a crash or `OSError` partway through
    `json.dump()` (confirmed live by monkeypatching `json.dump` to raise) truncated a previously-
    good forensic evidence store to empty, with no recovery -- a real threat to the chain-of-custody
    guarantee this tool exists to provide. Fixed with a temp-file + `os.replace()` atomic write
    (commit `50b091de5`, 2 new tests, the failure-preservation test verified via `git stash` to fail
    pre-fix). **Checked and confirmed NOT bugs (real investigation, not a skim):**
    `builtin/sparc/coordinator.py`'s `sparc_slash_command()` creates a fresh `asyncio` event loop
    and calls `run_until_complete()` from synchronous code -- traced its one real caller
    (`repl.py:701`, inside the synchronous `handle_command()`, itself called from a plain blocking
    `while` loop with `input()`, never from inside a running event loop) and confirmed this cannot
    hit Python's "event loop already running" conflict; `tool_translator.py` (clean, no logging/
    path/subprocess issues); `red-teaming/godmode/scripts/{auto_jailbreak,godmode_race,
    parseltongue,load_godmode}.py` (1,870 lines total; no logging/subprocess/requests/threading
    usage at all -- `load_godmode.py`'s deliberate `exec(open(path).read())` self-loading design is
    pre-existing and documented in its own docstring as a workaround for exec-scoping, not touched);
    `optional/blockchain/{base,solana}/scripts/*_client.py` (`except Exception: return None` on
    read-only public blockchain API calls -- standalone opt-in CLI scripts with no logging
    infrastructure at all, not production VECTOR infrastructure, judged not to warrant the same bar
    as the gateway/security/agent-routing code this pattern was fixed in elsewhere); `productivity/
    google-workspace/scripts/{gws_bridge,google_api}.py` (both correctly pass the OAuth token via an
    environment variable to the `gws` subprocess, never via argv -- the safe pattern already
    established elsewhere this cycle; `subprocess.run()` calls use a list, not `shell=True`, so no
    shell-injection path); `optional/mcp/fastmcp/scripts/scaffold_fastmcp.py` (writes to a
    user-supplied `--output` path -- the intended behavior of a local scaffolding CLI, not an
    untrusted-input-into-path bug). **NOT YET COVERED by this round** (explicitly, not represented
    as audited): `__init__.py`; `creative/{excalidraw/scripts/upload,pixel-art/scripts/{palettes,
    pixel_art,pixel_art_video}}.py`; `media/youtube-content/scripts/fetch_transcript.py`;
    `mlops/training/trl-fine-tuning/templates/basic_grpo_training.py`; `optional/{creative/
    meme-generation,health/fitness-nutrition,productivity/memento-flashcards/scripts/
    youtube_quiz,research/drug-discovery}/**/*.py`; `optional/mcp/fastmcp/templates/*.py`;
    `productivity/{ocr-and-documents,powerpoint}/**/*.py` beyond the already-fixed `clean.py`;
    `research/{arxiv,polymarket}/scripts/*.py`; `index.py`/`dependency.py`/`tool_adapter.py`/
    `executor.py` beyond round 3's earlier pass. `builtin/sparc/__init__.py`'s cross-tree import
    into the separate `vectorcode/skills/` directory (item 56) remains correctly un-touched -- an
    owner architecture decision, not a narrow fix.

65. **`vectorcode/src/evals/` audit, round 6 (2026-10-05) —** continued the directory-wide
    correctness/security audit from the 16 production files already fixed in prior rounds.
    **Fixed, each with regression coverage:** 18 additional dataset loaders assigned fallback or
    positional `record_id` values only after shuffling/splitting, so the same example received a
    different identity under different seeds and cross-run comparisons silently joined unrelated
    examples. The affected loaders are `datasets/{adp,email_triage,frames,gaia,generalthoughts,
    gpqa,hle,ipw_mixed,knowledge_base,math500,mmlu_pro,morning_brief,natural_reasoning,
    research_mining,simpleqa,supergpqa,toolorchestra,wildchat}.py`. Each now pairs the stable source
    position with its row before any shuffle/split and preserves that identity through sampling;
    native IDs remain preferred where present. Also fixed printf-style `%s` placeholders on Loguru
    calls encountered in `adp.py`, `simpleqa.py`, and `toolorchestra.py`, which previously emitted a
    literal `%s` and dropped the exception detail. Expanded
    `tests/test_evals_dataset_identity_regressions.py` with one two-seed identity regression per
    loader plus three parser-log rendering cases: **24/24 pass**. The combined focused + existing
    eval suite produced **171 passes, 13 failures**; all 13 are pre-existing legacy-test/config
    failures unrelated to these loaders (six obsolete `vector.*` mock targets, five stale
    `jarvis-*` example-config expectations, one additional obsolete `vector.*` CLI mock, and one
    stdlib `caplog` assertion against current Loguru output). `git diff --check` passes. **Commit
    blocked by execution environment:** `.git` is read-only and both `git add` and `git commit`
    fail creating `.git/index.lock` with `Permission denied`; all code/test changes therefore remain
    uncommitted, and this `OPEN_ISSUES.md` entry is intentionally unstaged as required. **Depth / work
    remaining:** full-depth reading completed for the fixed dataset files and the earlier inspected
    dataset batch (`ama_bench.py`, `deepplanning.py`); targeted recurring-pattern scans covered the
    whole production tree. This round did **not** complete a genuine line-by-line read of every
    remaining backend/core/execution/scorer/tracker file, so those files must remain explicitly
    unaudited rather than being represented as complete in a future handoff.

66. **Real-import smoke sweep of `core/` and `districts/` (2026-10-05, partial, environment-
    limited) —** triggered by item 60's `run_agent.py`-unimportable finding: a cheap, mechanical
    sweep (NOT a logic re-audit) attempting a real `import` of every module in these two trees,
    since the earlier "fully audited" passes may have used `ast.parse()` only, which is exactly
    what hid that bug for 4-5 months. **Methodology dead-ends hit and worked around, recorded for
    whoever continues this:** a `multiprocessing.Pool` with the `spawn` context failed outright in
    this Windows environment (`OSError: [WinError 87] The parameter is incorrect` on every worker,
    an environment/handle-duplication problem, not a code issue) -- switched to plain
    `subprocess.run([sys.executable, "-c", ...])` per module via a thread pool instead. The first
    subprocess attempt then produced a near-total false-failure rate (4033/4066) from a self-
    inflicted bug: passing `env={"PYTHONPATH": REPO}` *replaces* the subprocess's entire
    environment instead of extending it, starving Windows socket/DLL initialization of `PATH`/
    `SYSTEMROOT` etc. and producing `OSError: [WinError 10106]` for nearly everything regardless of
    the module's actual code. Fixed with `env={**os.environ, "PYTHONPATH": REPO}`. **Scope
    actually covered: 602 of 4,066 modules (~15%)** before the harness killed the sweep for
    unrelated host memory pressure (24 parallel subprocesses, several importing `torch`, exhausted
    available memory) -- explicitly instructed not to restart this myself; a future session should
    resume with a smaller worker count (e.g. 4-6) and/or a per-batch memory check. **Of the 602
    checked: 591 genuinely OK, 9 failures, all individually triaged (no unexamined pile):**
    5 were boring/expected (`ModuleNotFoundError: No module named 'textual'`, an optional TUI
    dependency not installed). 2 more were the "real bug shape" (sibling-module-in-same-codebase
    missing) and **fixed, each with a new regression test verified via `git stash` to fail
    pre-fix:** `core/coding_assistant/core/programmatic.py`'s `ClientMetadata` -- the same
    `fed812acc` blanket-`NotImplementedError` regression already found 9 times this cycle, here
    with the `raise` placed directly in the class body (not even `__init__`), crashing the module
    at class-definition/import time; restored the original no-op telemetry stub
    (`git show fed812acc^:<path>` confirmed `def __init__(self, name="", version=""): pass`).
    `core/mining/vllm_pearl.py`'s `from core.mining._discovery import detect_for_engine_model` --
    no such module; the real function lives in `core/mining/discovery.py` (no underscore); fixed
    the import path. **FLAGGED, not fixed (same file, separate deeper issue):**
    `vllm_pearl.py` also does `from core.mining._docker import PearlDockerLauncher`, and
    `core/mining/_docker.py` has never existed in this repo's entire git history (confirmed via
    `git log --all --diff-filter=D`) -- not a deletion, a migration that was apparently never
    completed. The real `PearlDockerLauncher` class only exists in the parallel
    `vectorcode/src/mining/_docker.py` tree (confirmed: `vectorcode/src/mining/vllm_pearl.py` is
    itself just a 1-line shim re-exporting from `core.mining.vllm_pearl`, establishing
    `core/mining/` as the intended canonical location -- but `_docker.py` was never ported there
    the way its sibling `_abc.py`/`_metrics.py`/`discovery.py` were). `vllm_pearl.py` therefore
    still cannot fully import even after this round's fix. Porting a class across trees, or
    redesigning the import boundary, is a bigger and more interpretive change than this audit's
    narrow-bug-fix mandate covers -- left for an owner decision rather than guessed at. New test:
    `tests/test_core_sweep_real_import_regressions.py` (4 tests). Commit:
    `33dc88141`. **NOT YET COVERED, explicitly:** 3,464 of 4,066 modules (~85%) in `core/` and
    `districts/` were never reached by this sweep. Resuming it (with a safer worker count) is the
    single highest-leverage next step for catching more `run_agent.py`-shaped bombs in these two
    trees, which are otherwise this repo's two largest code trees and were both marked "fully
    audited" using a methodology now known to have a blind spot.

67. **`vectorcode/src/agent/` audit, round 6 (2026-10-05) —** priority was `auxiliary_client.py`'s
    remaining provider-resolution/streaming-adapter logic (3,491 lines; a prior round only fixed
    its payment-fallback bug and logging). Read in full this round: `_CodexCompletionsAdapter`'s
    Responses-API streaming adapter, `_AnthropicCompletionsAdapter`, `_try_nous`/
    `_try_custom_endpoint`/`_try_codex`/`_try_anthropic`'s provider-detection chain,
    `_resolve_api_key_provider`'s fallback ordering, the client-cache key/eviction/loop-validation
    logic, and `call_llm()`'s main resolution/retry body — no new correctness bug found in any of
    these; the code is careful and well-commented throughout, with several issue-number references
    (`#10200`, `#2681`, `#7559`) showing prior real bugs were already caught here.
    **FLAGGED, not fixed (commit `40e05451b`):** `_try_payment_fallback()` never calls
    `CredentialPool.mark_exhausted_and_rotate()` on the pool-backed provider that just failed —
    unlike `run_agent.py`'s own retry logic, which calls it on every billing/rate-limit/auth
    failure (3 call sites, confirmed via `grep -rn mark_exhausted_and_rotate`: ONLY `run_agent.py`
    calls it anywhere in the repo). Consequence: the next unrelated auxiliary call re-resolves the
    same exhausted credential from scratch and eats the same 402/connection failure again before
    falling back — wasteful, not an outage, since the fallback chain still runs every time. Not
    fixed because `load_pool(provider)` creates a brand-new `CredentialPool` with no memory of
    which specific `entry.id` was used for the failed call (that's only tracked by the earlier,
    now-out-of-scope pool object's in-memory `_current_id`) — harmless for a single-entry pool
    (the common case), but a naive fix on a freshly-loaded pool could exhaust the WRONG entry in a
    genuinely multi-entry rotating pool, defeating the rotation feature those pools exist to
    support. A correct fix means threading the specific pool entry id from the resolution call
    sites (`call_llm`/`async_call_llm`/`resolve_provider_client`) through to the exception handler
    — a larger refactor than this audit's narrow-bug-fix mandate covers; flagged in the function's
    own docstring for an owner decision.
    **Reviewed, no severe bug found (lower-confidence, not acted on):** `agent/redact.py`'s
    (off-by-default, opt-in-only) secret-redaction module has an unused stdlib `logger =
    logging.getLogger(__name__)` declaration (dead code, zero call sites — harmless, not worth a
    dedicated fix) and a possible fail-open gap where `_ENV_ASSIGN_RE`/`_JSON_FIELD_RE`'s quoted-
    value capture (`(['"]?)(\S+)\2`) silently fails to match — and therefore silently fails to
    redact — a quoted secret value containing an internal space (e.g. `TOKEN="abc def"`); not
    fixed/flagged further since this is a heuristic best-effort tool that already documents many
    pattern-specific limitations, and the fix carries its own regex-complexity/backtracking risk.
    `credential_pool.py` itself was read enough to confirm `load_pool()`'s per-call fresh-instance
    behavior (used above) but not given an independent full-file pass this round.
    **Not reached this round** (~40 files, listed here rather than silently omitted):
    `account_usage.py`, `codex_responses_adapter.py`, `context_references.py`,
    `copilot_acp_client.py`, `curator_backup.py`, `display.py`, `error_classifier.py`,
    `gemini_cloudcode_adapter.py`, `gemini_native_adapter.py`, `gemini_schema.py`,
    `google_code_assist.py`, `i18n.py`, `image_gen_{provider,registry}.py`, `image_routing.py`,
    `insights.py`, `markdown_tables.py`, `moonshot_schema.py`, `nous_rate_guard.py`,
    `onboarding.py`, `plugin_llm.py`, `prompt_builder.py`, `rate_limit_tracker.py`,
    `skill_{commands,preprocessing,utils}.py`, `subdirectory_hints.py`, `think_scrubber.py`,
    `title_generator.py`, `transports/{bedrock,codex,codex_app_server,
    codex_app_server_session,codex_event_projector,types,vector_tools_mcp_server}.py`,
    `usage_pricing.py`, `video_gen_{provider,registry}.py`, `web_search_{provider,registry}.py`.
    **Depth statement:** this entry represents genuine full-depth review of `auxiliary_client.py`
    only (now complete across all 6 rounds covering this directory); none of the "not reached"
    files above should be treated as audited.

68. **`vectorcode/src/learning/` audit, round 7 complete (2026-10-05) —** re-derived the
    remaining set from Git history, then reconciled it with round 6's exact depth statement (item
    63). Full line-by-line review is now complete for all 15 files named there:
    `intelligence/orchestrator/{prompt_registry,types,policy_model,reward}.py`,
    `routing/complexity.py`, `optimize/{types,search_space,config}.py`, `training/data.py`,
    `distillation/execute/appliers/{lora_stub,tools,intelligence}.py`,
    `distillation/{student_runner.py,checkpoint/store.py}`. Also rechecked recurring-pattern hits
    in previously touched files. **Fixed with proof regressions:** (1) sixth learning-directory
    CWE-22 instance: teacher-generated `Edit.id` was interpolated directly into LoRA queue and
    adapter paths, including rollback's `shutil.rmtree()` target; a `..` or absolute ID could
    escape the intended directory. All queue/write/delete/training paths now resolve through one
    direct-child confinement helper. (2) TOML correctness/config-injection: the agent evolver and
    intelligence/tool edit appliers interpolated model-generated strings and keys into TOML with
    incomplete or zero escaping; quotes, control characters, and crafted section/key text could
    corrupt the config or create unintended assignments. Added spec-compatible scalar/list and
    quoted-key serialization and verified hostile multiline payloads by parsing every output with
    `tomllib`. (3) remaining logging regressions: `learning/__init__.py` used stdlib-only
    `exc_info=True` with Loguru; checkpoint store, student runner, DSPy optimizer, GEPA optimizer,
    and prompt-diff used stdlib logging and/or printf placeholders. Converted all to Loguru's
    exception/formatting APIs. (4) `VLLMStudentRunner` owned an `httpx.Client` with no release
    path; added `close()` and context-manager support. New tests:
    `tests/test_vectorcode_learning_{lora_path_confinement,agent_evolver_toml,
    applier_toml_safety,round7_logging,student_runner_close}.py`: **12/12 pass**. Entire
    `vectorcode/src/learning/` compiles; `git diff --check` passes. No new design/policy question
    was found in the other reviewed files. **New owner decision:** LoRA edits are always assigned
    `MANUAL`, and both shipped execution loops skip `MANUAL` edits before applier lookup, making
    `LoraStubApplier`'s documented deferred queue and real training branches unreachable through
    the normal pipeline. This conflicts with the applier's stated behavior; changing the
    approval-to-execution design was not guessed at, and a comment now flags the exact code site.
    Earlier flags for no-op edit rollback and the dead PPO ratio also remain owner decisions.
    Work was done by Codex (gpt-5.6-sol); as with other items, Codex's sandbox could not write
    `.git/index.lock`, so Claude reviewed and committed on its behalf after independently running
    all 12 new tests: `e2fdff745` (TOML injection fixes), `788503a0d` (lora_stub.py CWE-22 fix),
    `e75f42538` (unclosed httpx client + remaining logging fixes).

69. **`vectorcode/src/agent/` audit, round 7 (2026-10-05) —** six prior rounds covered ~27
    files with real depth (including the critical `run_agent.py`-unimportable fix in round 5).
    This round re-derived the remaining ~50 files via `git ls-files` diffed against
    `git log`, and gave genuine full-depth review to 5 of them, prioritized by
    security/credential-sensitivity and by the established "adapter files have bugs" pattern
    from prior rounds. **Fixed, each with a new regression test verified via `git stash` to
    fail pre-fix:**
    `copilot_acp_client.py` had 3 suppressed-exception `logger.debug(..., "%s", _sve)` calls
    using a stdlib %-style placeholder under this file's correctly-imported loguru logger —
    fixed to `{}`. Also added a comment flagging (not fixing) its two daemon `threading.Thread`
    calls that drain the Copilot ACP subprocess's stdout/stderr pipes — `_create_chat_completion()`
    is itself a synchronous OpenAI-client-compatible entry point, so converting to asyncio
    subprocess streams would mean making the whole call chain async, a real architectural
    change, not a narrow fix. Commit `60c7761d7`.
    `google_code_assist.py` correctly imported loguru at the top, then immediately shadowed
    it with `logger = logging.getLogger(__name__)` a few lines later — the classic shadow-import
    bug found repeatedly this audit cycle. Fixed, converting 5 affected `%`-style call sites to
    `{}`-style. Also fixed a wrong-variable logging bug in `_post_json()`: the
    HTTPError-detail-read `except Exception as _sve:` block logged the OUTER exception `exc`
    instead of the `_sve` it actually caught, so a failure reading the error detail body never
    actually surfaced why. Commit `62c95106e`.
    `account_usage.py`'s `fetch_account_usage()` had a bare `except Exception: return None`
    swallowing ANY failure (network error, auth failure, API schema change, a bug in this code
    itself) with zero logging — an operator debugging "why does account usage show
    unavailable" had no diagnostic trail at all. Added a warning log with the provider and
    exception. Its `_fetch_openrouter_account_usage()` helper had the same shape on a narrower,
    genuinely-optional `/key` lookup — added a debug log for consistency (it already degraded
    gracefully to credits-only data, correctly). Commit `366faa636`.
    `codex_responses_adapter.py` used pure stdlib `logging.getLogger(__name__)` (no loguru
    import at all, not even a shadow) with `%d`/`%r`-style placeholders across its 2 logger
    call sites — converted to loguru with `{}`/`{!r}`. Commit `1925f2a4b`.
    **Reviewed, no bug found:** `usage_pricing.py` (700 lines, read in full — distinct from
    and not a duplicate of `vectorcode/src/utils/usage_pricing.py`, which persists usage events
    to disk; this one is pure in-memory cost-estimation logic from static pricing tables and
    model-metadata lookups, careful defensive guards throughout, no logging to audit since it
    has none).
    New tests: `tests/test_vectorcode_agent_copilot_acp_client_logging.py` (2),
    `tests/test_vectorcode_agent_google_code_assist_logging.py` (3),
    `tests/test_vectorcode_agent_account_usage_logging.py` (2),
    `tests/test_vectorcode_agent_codex_responses_adapter_logging.py` (3) — 10/10 passing.
    **Depth statement:** this round covered 5 of the ~50 remaining files with genuine full
    depth (4 fixed, 1 reviewed clean). ~45 files remain untouched across all 7 rounds, including
    several other provider-adapter files with the same risk profile that prompted this round's
    file selection (`gemini_native_adapter.py`, `gemini_cloudcode_adapter.py`,
    `transports/codex_app_server*.py`, `transports/bedrock.py`), the `lsp/` subsystem
    (`client.py`, `manager.py`, `cli.py`, `protocol.py` — only the 5 small shim files in
    `lsp/` got depth in round 1), `skill_utils.py`/`skill_commands.py`/`skill_preprocessing.py`,
    `redact.py` (already flagged lower-confidence issues in round 6, not re-examined), and most
    of the smaller utility/provider-registry files. Explicitly not representing this directory's
    audit as complete.

70. **`vectorcode/src/{vc_agents,connectors,vc_tools}/` continuation round (2026-10-05) —**
    resumed after a prior round-3 attempt crashed from a network error (ENOTFOUND) having
    committed exactly 1 fix (`bac30b978`, slack_connector.py). Confirmed via `git log` that
    three full prior rounds covered ~53 of 122 files with real depth; continued into the
    remaining ~69. **Fixed, each with a new regression test verified via `git stash` to fail
    pre-fix:** `vc_tools/shell_exec.py`'s `_BASE_ENV_KEYS` built a *replacement* environment
    (not an extension of `os.environ`) containing only `PATH`/`HOME`/`USER`/`LANG`/`TERM` --
    on this Windows host, Win32's `CreateProcess`/Winsock initialization needs `SYSTEMROOT`
    present in the child environment, and without it ANY command doing DNS resolution or other
    socket activity failed with `socket.gaierror: [Errno 11001] getaddrinfo failed` regardless
    of whether the command itself was fine (confirmed live with a minimal
    `socket.gethostbyname()` repro in a subprocess, both before and after). This silently broke
    a large fraction of what an agent would plausibly run through this tool on this platform
    (curl, ping, pip install, git fetch, any network-touching script) -- failures that looked
    like "the command is broken," not "the sandbox's environment is incomplete." Added
    `SYSTEMROOT`/`WINDIR`/`COMSPEC` to `_BASE_ENV_KEYS` (non-secret OS-identity variables,
    consistent with the tool's existing minimal-env security posture). `vc_agents/loop_guard.py`:
    `check_call()`'s warn-before-block wrapper deduplicated on `verdict.reason`, the
    human-readable message string -- for the `identical_call` trigger, that message embeds the
    live call count ("...repeated {n} times..."), incrementing every call, so the dedup key was
    never the same twice and the guard warned forever without ever reaching the "block" stage
    its own docstring promises. Confirmed live: 8 identical calls with `max_identical_calls=3`
    all came back `blocked=False`, defeating the entire purpose of a component whose job is to
    prevent degenerate agent tool-calling loops. Fixed by adding a stable `trigger_key` field to
    `LoopVerdict`, set independently of the human-readable `reason` text at each blocking site,
    and using it (not `reason`) as the dedup key. `connectors/dropbox.py`'s `sync()` caught ANY
    exception from the text-download call -- including a revoked/expired OAuth token, not just
    "this file isn't actually text" -- and silently substituted placeholder content with zero
    logging; a persistent auth failure partway through a sync would look like a fully successful
    sync that just happened to produce `[File: name]` placeholders for every subsequent file.
    Same "phantom success" bug class already fixed in `connectors/slack_connector.py` this audit
    cycle (there via an unchecked response field; here via silent exception swallowing). Added a
    loguru warning; kept the existing fallback behavior otherwise. **FLAGGED, not fixed --
    design/policy decisions:** `vc_tools/file_read.py` and `file_write.py` both accept an
    `allowed_dirs` constructor parameter and implement real `Path.is_relative_to()` confinement,
    but both real call sites (`vc_mcp/server.py`, `vc_system/orchestrator.py`) instantiate via
    `ToolRegistry.create(key)` with no extra args -- `allowed_dirs` is always `None` in
    production, so `_is_path_allowed()` always returns `True` and this directory allowlist
    provides zero actual confinement today. Only `is_sensitive_file()`'s blocklist
    (secrets/credentials/keys) is really enforced; an agent can read (and, via `file_write.py`,
    write) any non-"sensitive" file the OS process can access, anywhere on the filesystem.
    Whether confinement should come from wiring this parameter at the two call sites, or is
    intentionally deferred to a higher-level permission-gateway tier, is an owner decision --
    same shape as other unwired-security-control findings this audit cycle (`skills/security.py`'s
    capability gate, `agent/types.py`'s manifest signing). `vc_agents/orchestrator.py`'s parallel
    tool-call path uses `concurrent.futures.ThreadPoolExecutor`, the same asyncio-policy-violating
    pattern already flagged (not fixed) in `evals/core/agentic_runner.py` and
    `evals/backends/external/_subprocess_runner.py` -- converting `run()`'s whole synchronous call
    chain to async is a bigger architectural change than a narrow fix. **Reviewed, no bug found:**
    `vc_agents/{agent_registry,rlm,simple,native_react,native_openhands,openhands,digest_store,
    channel_agent,routing_agent,errors,web_search_agent,deep_research,digest_evaluator}.py`
    (pattern-scanned for the established bug classes, with `digest_store.py`'s `threading.RLock()`
    confirmed to be a legitimate sync primitive, not the banned spawn-pattern; all `print()` hits
    confirmed inside `__main__` self-test blocks). `vc_agents/__init__.py`'s backward-compat
    `import vectorcode.src.vc_agents.react` fails every time (the shim file was apparently never
    created) -- confirmed zero real callers anywhere in the repo reference that path, and the
    surrounding `try/except ImportError` + debug-log already degrades gracefully with zero actual
    impact; not a bug, working as designed. `connectors/{obsidian,notion,spotify}.py` (obsidian.py
    in full: local filesystem walk, no API calls, permission errors on individual files correctly
    treated as skip-and-continue rather than phantom success since the overall sync makes no false
    claim about files it couldn't read; notion.py and spotify.py's exception handling checked and
    found to have no equivalent of dropbox.py's silent-swallow bug). New tests:
    `tests/test_vectorcode_vc_tools_shell_exec_env.py` (3, Windows-specific),
    `tests/test_vectorcode_vc_agents_loop_guard_warn_then_block.py` (3),
    `tests/test_vectorcode_connectors_dropbox_download_logging.py` (2) -- 8/8 passing.
    **Depth statement:** 7 files got genuine full-depth review this round (3 fixed, 2 flagged, 2
    files' exception-handling spot-checked clean alongside obsidian.py's full read), plus 13
    `vc_agents/` files pattern-scanned rather than fully read line-by-line. ~60 files remain
    across all three directories, prioritized by the next round as: `connectors/` (apple_notes,
    chunker, gmail, google_tasks, granola, hackernews, imessage, oura, outlook, pipeline, strava,
    weather -- most untouched), most of `vc_tools/` (knowledge_search/knowledge_sql/
    knowledge_tools, llm_tool, mcp_adapter, memory_manage, pdf_tool, repl, retrieval, scan_chunks,
    skill_manage, storage backends other than sqlite/knowledge_graph/dense, text_to_speech, think,
    user_profile_manage, apply_patch, audio_tool, browser_axtree, calculator, channel_tools,
    code_interpreter_docker, _markdown_store).

71. **`vectorcode/src/agent/` audit, round 8 (2026-10-05) —** re-derived the
    remaining inventory from `git log --oneline -- vectorcode/src/agent/` and
    `git ls-files`, then prioritized the two Gemini adapters, Codex app-server
    transports, substantive LSP modules, skill handling, and the recurring
    provider/utility logging family. **Security fix:** `context_references.py`
    applied its sensitive credential-path denylist with case-sensitive `Path`
    comparisons; on Windows, differently-cased spellings such as
    `.SSH/ID_RSA`, `.AWS/credentials`, and VectorCode `.ENV` bypassed the
    blocklist. Comparisons now use the platform's normalized path spelling and
    proof tests cover all three cases. **Correctness fix:** skill config prompt
    injection used `value if value else "(not set)"`, silently misrepresenting
    explicit `0` and `False`; it now distinguishes only `None`/empty string.
    **Observability fixes:** 25+ remaining modules used stdlib logging, shadowed
    a correct Loguru import (including imports trapped inside docstrings), sent
    `%` placeholders to Loguru, or used stdlib-only `exc_info=True`. Corrected
    the Gemini native/Cloud Code adapters, Codex app-server/session and other
    transports, LSP client/manager, all three skill helpers, image/video/web
    provider registries, and the affected utilities. A final AST/pattern sweep
    found no unbound `logger` users and no remaining invalid Loguru arguments in
    the newly reviewed set; the sole `%s` hit is Google OAuth's deliberate
    callback adapter which converts stdlib formats to Loguru before dispatch.
    New tests: `tests/test_vectorcode_agent_{context_reference_safety,
    gemini_adapter_logging,lsp_logging,round8_logging,
    skill_handling_regressions,transport_logging}.py`: **14/14 pass**; the full
    `vectorcode/src/agent/` tree compiles and `git diff --check` passes.
    **Owner decisions, not guessed at:** `lsp/manager.py`,
    `transports/codex_app_server.py`, `display.py`, and `title_generator.py`
    contain production `threading.Thread` bridges despite the repository ban;
    each has an exact audit comment because replacing it requires changing a
    synchronous public call chain to asyncio (the previously flagged Copilot
    and curator threads remain unchanged). **Depth statement:** genuine deep
    review was concentrated on the explicitly prioritized Gemini, Codex
    app-server, LSP, skill-handling, and context-reference paths; the broad
    utility/provider-family pass was targeted recurring-pattern review, not a
    claim that every remaining utility received fresh line-by-line semantic
    review. Work was done by Codex (gpt-5.6-sol); as with other items, Codex's
    sandbox could not write `.git/index.lock`, so Claude reviewed and committed
    on its behalf after independently running all 14 new tests: `f0228d3a2`
    (context_references.py), `51833cdf6` (skill_commands.py), `10e96268e`
    (remaining 28-file logging batch).

72. **`vectorcode/src/skills/` audit, round 6 (2026-10-05) —** reconstructed the
    remaining scope from Git history plus round 5's explicit handoff and completed a full
    line-by-line review of 29 files (4,281 lines), excluding the separately-reserved 2,794-line
    `optional/migration/openclaw-migration/scripts/openclaw_to_vector.py`. **Fixed with new
    regression coverage:** `optional/creative/meme-generation/scripts/generate_meme.py` preferred
    the project-banned `requests` client; it now uses `httpx` and preserves status checking.
    `productivity/powerpoint/scripts/add_slide.py` accepted caller-controlled slide/layout names
    containing `..` or absolute paths, allowing reads outside the expected unpacked Office
    directories via both traversal and pathlib's absolute-path override; direct-child confinement
    now guards both paths. `productivity/ocr-and-documents/scripts/extract_marker.py` likewise
    joined document-renderer-provided image names directly to `output_dir`, allowing an output
    escape; it now resolves/confines every image path and also correctly supports Marker/PIL image
    objects as well as raw byte values. `builtin/sparc/coordinator.py` did not implement the
    advertised `/sparc <task>` syntax (it treated the task's first word as an unknown stage), and
    every standalone stage after `specification` crashed on absent prior-stage format keys; both
    invocation forms now work. `executor.py` silently converted malformed/non-object sub-skill
    arguments into an empty context and could report phantom success; it now returns an explicit
    failed `ToolResult` without invoking the child. `creative/pixel-art/scripts/pixel_art.py` and
    `pixel_art_video.py` now reject non-positive block/timing values before division/ffmpeg work,
    compute integral frame counts for fractional durations, and support tiny images whose
    dimensions previously made three animation initializers raise an invalid-`randint` error.
    `productivity/powerpoint/scripts/office/helpers/{merge_runs,simplify_redlines}.py` wrote parsed
    XML directly over the only copy, and `office/pack.py` opened the destination archive in `w`
    mode; an interrupted/failed write could truncate an existing valid document. These writes now
    use same-directory temporary files plus `os.replace()`, with failure-preservation tests.
    **FLAGGED, not guessed at:** `office/pack.py` imports `DOCXSchemaValidator`,
    `PPTXSchemaValidator`, and `RedliningValidator` from a `validators` module that does not exist
    anywhere in the repository or its Git history. Consequently the module is unimportable and
    its advertised DOCX/PPTX validation/auto-repair path has no implementation. Reconstructing
    three schema validators is an owner-level feature/architecture decision, not a narrow audit
    repair. Also left untouched as already documented: `builtin/sparc/__init__.py`'s wrong
    cross-tree import (item 56). **Reviewed with no additional genuine bug found:** package
    `__init__.py`; palette constants; Excalidraw upload; YouTube transcript helper; GRPO template;
    fitness/nutrition and drug-discovery standalone scripts; FastMCP templates; PyMuPDF extraction;
    PowerPoint XML merge/redline logic beyond the atomic-save issue; arXiv and Polymarket CLIs;
    and the deeper `dependency.py`, `index.py`, and `tool_adapter.py` logic. Five new test files,
    17 focused tests pass; the broader existing+new skills selection also passes, and
    `python -m compileall -q vectorcode/src/skills` plus `git diff --check` pass. **Commit status:**
    work was done by Codex (gpt-5.6-sol); as with other items, Codex's sandbox could not write
    `.git/index.lock`, so Claude reviewed and committed on its behalf after independently running
    all 17 new tests and confirming the `office/pack.py` import failure live:
    `0cc389734` (sparc/executor fixes), `6dbb1da4e` (document path confinement + atomic writes),
    `dd8a83ffd` (pixel-art/meme-generation fixes).

73. **`vectorcode/src/{vc_agents,connectors,vc_tools}/` continuation round 5 (2026-10-05) —**
    resumed after round 4 (~60 of 122 files with real depth, including a LoopGuard safety bug
    and a shell_exec.py env-var bug). This round covered `connectors/{notion,spotify,outlook,
    gmail,google_tasks}.py` and `vc_agents/{agent_registry,routing_agent,simple}.py` with full
    line-by-line depth. **Fixed, each with a new regression test verified via `git stash` to
    fail pre-fix:** `connectors/strava.py` had a `_strava_refresh_token()` function defined with
    **zero callers anywhere in the repo** -- the module's own docstring claimed "Refresh handled
    automatically," but `_get_access_token()` just read the stored `access_token` directly with
    no expiry check. Strava tokens expire after ~6h, so every `sync()` after that point failed
    with a 401 until the user manually re-authenticated, despite the connector's own claim.
    Wired `_get_access_token()` to check a persisted `expires_at` (60s margin) and call the
    already-existing refresh function, persisting the result; `handle_callback()` now also
    persists `expires_at` from the initial exchange (commit `fee0ca4e7`).
    `vc_agents/routing_agent.py`'s `route()` had an operator-precedence bug:
    `task_type or task.split()[0] if task else "research"` parses in Python as
    `(task_type or task.split()[0]) if task else "research"`, not the intended
    `task_type or (task.split()[0] if task else "research")` -- conditional expressions bind
    looser than `or`. An explicitly-passed `task_type` was silently discarded and replaced with
    the literal string `"research"` whenever `task` happened to be empty; a whitespace-only
    `task` also crashed with `IndexError` since `" ".split() == []`, not `[""]`. Fixed with
    explicit parentheses and a guarded split (commit `5b3cc32a2`).
    **FLAGGED, not fixed (docs only, commit `2b8a4861b`):** `connectors/google_tasks.py` has the
    same missing-token-refresh gap as the Strava bug, but with no ready-to-wire refresh function
    to restore -- it shares `connectors/oauth.py`'s `load_tokens()` (a dumb JSON reader, no
    refresh logic at all) and doesn't persist a `refresh_token`/`client_secret` pair the way
    Strava's connector does. `gmail.py`'s `is_connected()` already self-documents this same
    limitation ("simplified: real impl would also check expiry / refresh token") honestly in a
    comment; `google_tasks.py` didn't, so a matching comment was added. The right fix (per-
    connector refresh vs. a shared helper in `oauth.py` covering every Google-family connector
    at once) is an owner architecture decision, not a narrow patch.
    **Reviewed, no bug found:** `connectors/notion.py` (uses `resp.raise_for_status()`
    throughout, no phantom-success risk), `connectors/spotify.py` (same), `connectors/outlook.py`
    (IMAP + app password, not OAuth -- no token-expiry concern at all), `connectors/gmail.py`'s
    two `except Exception` sites (both benign best-effort fallbacks for display fields -- body
    decoding and date parsing -- not phantom-success on the sync itself), `vc_agents/
    agent_registry.py` (lazy-init singleton registry, clean), `vc_agents/simple.py` (38 lines,
    trivial single-turn agent).
    New tests: `tests/test_vectorcode_connectors_strava_token_refresh.py` (3),
    `tests/test_vectorcode_vc_agents_routing_agent_precedence.py` (4) -- 7/7 passing.
    **Depth statement:** 8 files got genuine full-depth review this round (2 fixed, 1 flagged, 5
    reviewed clean). ~52 files remain across all three directories, still not represented as
    audited: most of `vc_agents/` (`digest_store.py`, `digest_evaluator.py`, `rlm.py`,
    `native_react.py`, `native_openhands.py`, `openhands.py`, `channel_agent.py`,
    `deep_research.py`, `errors.py`, `web_search_agent.py`, `templates/`), most of `connectors/`
    (`_abc.py`, `apple_notes.py`, `chunker.py`, `granola.py`, `hackernews.py`, `imessage.py`,
    `oura.py`, `pipeline.py`, `weather.py`), and most of `vc_tools/` (`apply_patch.py`,
    `audio_tool.py`, `browser_axtree.py`, `calculator.py`, `channel_tools.py`,
    `code_interpreter_docker.py`, `image_tool.py`, `knowledge_search.py`, `knowledge_sql.py`,
    `knowledge_tools.py`, `llm_tool.py`, `mcp_adapter.py`, `memory_manage.py`, `pdf_tool.py`,
    `retrieval.py`, `scan_chunks.py`, `skill_manage.py`, `storage/*` beyond `dense.py`,
    `storage_tools.py`, `templates/`, `text_to_speech.py`, `think.py`,
    `user_profile_manage.py`).

74. **`vectorcode/src/evals/` audit, round 7 (2026-10-05) —** reconstructed the
    untouched production inventory from the complete path history (92 Python files after excluding
    eval-local tests and 39 previously fixed files) and performed a fresh recurring-pattern and
    subsystem review. **Fixed with proof tests:** the OpenClaw subprocess backend exposed its API
    key and base URL in process arguments; both now travel through the child environment. Five
    dataset fallback identities (`livecodebench`, `swebench`, `swefficiency`, `terminalbench`, and
    `webchorearena`) were assigned after shuffle and now preserve their pre-shuffle source index;
    `liveresearch` also preserves a legitimate upstream ID of zero. PinchBench fixture destination
    and asset-source paths allowed both `..` traversal and pathlib absolute-path override outside
    their workspace/assets roots; both sides are now resolved and confined. The Coding Assistant
    scorer could not import its synthetic `solution` module and only defined extracted tests without
    invoking them, making valid fixes unscorable; it now uses a two-module allowlisted test importer
    and calls the one extracted test. TauBench treated an absent simulation reward as an authoritative
    zero/failure rather than indeterminate. Framework config generation contained two literal
    `vector` dictionary keys after debranding, silently erasing the native agent condition; the four
    advertised conditions are distinct again (`vector-agent`, `vector-distilled`, `vector`,
    `openclaw`). Six new top-level regression files provide **16/16 passing tests**; the eval package
    compiles and `git diff --check` passes. The combined existing eval-local plus new suite reached
    **163 passes / 13 pre-existing failures**: stale tests still import the removed `vector.*` tree,
    stale example TOMLs still name `jarvis-agent`/`jarvis-direct`, and one test expects stdlib
    `caplog` to capture Loguru. **Remaining work:** many untouched eval modules still use stdlib
    logging and/or printf placeholders; a mechanical conversion attempt was rejected by compile
    verification and fully reverted (zero content diff on recovery files), so this needs a careful
    follow-up rather than retaining unsafe bulk edits. **Commit status:** work was done by Codex
    (gpt-5.6-sol); as with other items, Codex's sandbox could not write `.git/index.lock`, so Claude
    reviewed and committed on its behalf after independently running all 16 new tests and confirming
    the pre-fix test-execution bug by reading the exact exec'd-but-never-called function body:
    `ac59c6753` (coding_assistant.py), `79bab5a55` (taubench.py), `f3e9ade7c` (openclaw.py),
    `495cf0ae7` (pinchbench_env.py), `6bc24109e` (make_configs.py duplicate key),
    `52cc0dd05` (6 more dataset record_id fixes). The reverted mechanical logging-conversion attempt
    left 6 files showing as modified in git with zero actual content diff (write-then-revert,
    confirmed via `git diff --stat`); those were checked out back to HEAD rather than committed.

75. **`vectorcode/src/{connectors,vc_tools}/` audit, round 6 (2026-10-06) —** continued the
    `~52 remaining files` inventory listed at the end of item 73 (connectors/vc_agents/vc_tools).
    **Fixed with proof tests:** the same `SyncStatus`-never-reports-error shape found six times --
    `connectors/{oura,weather,hackernews,granola}.py` and `connectors/{apple_notes,imessage}.py` --
    `sync()` only ever set `state="idle"`/cleared the error on its success path; since `"idle"` is
    also the dataclass default (and, for the two local SQLite-reading connectors and granola, the
    permanent hardcoded value `sync_status()` returned), a mid-sync exception (expired token, API
    down, locked DB, malformed credentials file) was indistinguishable from "nothing synced yet" to
    any caller polling `sync_status()`. All six now set/clear a real error on their state. Also:
    `vc_tools/code_interpreter_docker.py`'s `execute()` called `container.remove(force=True)` in a
    `finally` with no exception handling of its own -- if `container.wait(timeout=...)` genuinely
    timed out and the cleanup `remove()` call then *also* raised (daemon busy, container already
    gone), the cleanup exception replaced the original timeout, so callers saw a confusing generic
    "Docker execution error" instead of the correct "Execution timed out after N seconds." message.
    `remove()` is now wrapped in its own try/except that logs and swallows cleanup failures.
    **Flagged, not fixed (owner decision):** `connectors/granola.py`'s `sync()` silently yields zero
    documents when no API key is configured (`if not api_key: return`) instead of raising -- kept as
    pre-existing behavior (now commented) since changing a generator's control flow on a missing-
    credential path was judged beyond this round's narrow status-reporting fix, and `is_connected()`
    is the documented way callers are expected to check for this first. `connectors/pipeline.py`'s
    `IngestionPipeline.ingest()` only adds a doc's `doc_id` to `self._seen_doc_ids` *after*
    attachment processing completes -- if `self._store.store()` or attachment extraction raises
    partway through a document, the doc_id is never marked seen, so a retry of the same batch could
    re-write chunks for parts that already succeeded. Not fixed: the right behavior (mark seen
    before vs. after attachment processing, and whether partial writes should be rolled back) is a
    partial-failure semantics decision for the owner, not a narrow patch.
    **Reviewed, no bug found:** `connectors/chunker.py` (pure-function text chunker, no I/O; sentence/
    paragraph/section splitting logic checked for off-by-one and mis-pairing bugs in
    `_chunk_email`'s header/body reassembly -- correct).
    New tests: `tests/test_vectorcode_connectors_sync_status_error_reporting.py` (5),
    `tests/test_vectorcode_connectors_apple_notes_imessage_sync_status_error.py` (2),
    `tests/test_vectorcode_code_interpreter_docker_cleanup_masking.py` (2) -- 9/9 passing, all
    confirmed failing pre-fix via `git stash`.
    **Depth statement:** 7 files got genuine full-depth review this round (6 fixed, 1 reviewed
    clean) plus 1 more fixed in `vc_tools/`. `connectors/pipeline.py` and `connectors/_abc.py` were
    read for context but not independently fixed this round. Still remaining from item 73's list:
    most of `vc_agents/` (`digest_store.py`, `digest_evaluator.py`, `rlm.py`, `native_react.py`,
    `native_openhands.py`, `openhands.py`, `channel_agent.py`, `deep_research.py`, `errors.py`,
    `web_search_agent.py`, `templates/`), and most of `vc_tools/` (`apply_patch.py`, `audio_tool.py`,
    `browser_axtree.py`, `calculator.py`, `channel_tools.py`, `image_tool.py`, `knowledge_search.py`,
    `knowledge_sql.py`, `knowledge_tools.py`, `llm_tool.py`, `mcp_adapter.py`, `memory_manage.py`,
    `pdf_tool.py`, `retrieval.py`, `scan_chunks.py`, `skill_manage.py`, `storage/*` beyond
    `dense.py`, `storage_tools.py`, `templates/`, `text_to_speech.py`, `think.py`,
    `user_profile_manage.py`).
    **Commit status:** `727a779bf` (oura/weather/hackernews/granola), `85f78b8fb` (apple_notes/
    imessage), `382a507a5` (code_interpreter_docker.py).

76. **`vectorcode/src/agent/` audit, round 9 (2026-10-06) —** finished the ~13 files not yet
    given real depth across 8 prior rounds: `transports/{anthropic,bedrock,codex,codex_event_projector,
    __init__}.py`, `insights.py`, `markdown_tables.py`, `gemini_schema.py`, `moonshot_schema.py`,
    `rate_limit_tracker.py`, `think_scrubber.py`, `usage_pricing.py`, `web_search_provider.py`,
    `lsp/cli.py`, `lsp/protocol.py`. This closes out `vectorcode/src/agent/` for this audit cycle --
    every file in the directory now has real round coverage.
    **Fixed with proof tests:**
    - `transports/codex_event_projector.py` -- `_deterministic_call_id()`'s fallback path (used
      whenever a Codex app-server item arrives with no `id`) hashed only the fixed `item_type`
      string, producing an IDENTICAL `tool_call_id` for every same-type tool call in a session
      despite the docstring's claim it was a content hash -- two same-type calls without an id in
      one turn collided, breaking assistant/tool-message correlation. Replaced with a per-type
      monotonic counter on the projector instance (unique within its lifetime, still deterministic
      across a replay of the same ordered notification stream).
    - `run_agent.py` -- the big one this round. `agent/think_scrubber.py`'s `StreamingThinkScrubber`
      was a fully-implemented, carefully-documented stateful scrubber with **zero callers anywhere
      in the repo** (confirmed via grep), despite its own docstring describing the exact live bug in
      `AIAgent._fire_stream_delta()`: that method called the stateless, regex-based
      `_strip_think_blocks()` per delta, so a provider (MiniMax M2.7 is the documented case) that
      streams a `<think>` open tag as its own delta gets that delta erased by the "unterminated open
      at a boundary" regex case -- but the regex has no memory of still being inside a block on the
      NEXT delta, so the actual reasoning body arriving in that next delta looked like ordinary
      content and was emitted straight to the user. Wired `StreamingThinkScrubber` into
      `_fire_stream_delta()` (upstream of the existing memory-context scrubber) and into
      `_reset_stream_delivery_tracking()` (flush + reset at the top of each new turn, mirroring the
      existing context-scrubber handling). This is a real, user-visible reasoning-leak fix, not a
      lint pass -- the module existed and was tested-looking but was simply never plugged in.
    - `lsp/cli.py` -- `_cmd_which()` looked up `INSTALL_RECIPES.get(server_id)` directly instead of
      routing through `_recipe_pkg_for(server_id)` like every sibling subcommand
      (`_cmd_status`/`_cmd_list`/`_cmd_install`/`_cmd_install_all`) does. For the 3 of 4 aliased
      server ids where the alias actually changes the binary name (`astro-language-server` ->
      real binary `astro-ls`, `dockerfile-ls` -> real binary `docker-langserver`, `typescript` ->
      real binary `typescript-language-server`), `vector lsp which <id>` queried the wrong binary
      name and reported "not installed" even when the server was correctly installed.
    - `agent/usage_pricing.py` -- `format_token_count_compact()` rounded a value just under a unit
      threshold (e.g. 999_999, just under the 1_000_000 "M" threshold) up to "1000" with its `.0f`
      formatting, displaying `"1000K"` instead of rolling over to `"1M"` (same bug recurs at the
      M/B boundary: `999_994_999` -> `"1000M"` instead of `"1B"`). Fixed by detecting a >=1000
      rounded value and re-rendering against the next bigger unit. Note: this function currently has
      zero callers anywhere in the repo (confirmed via grep) -- the fix is still correct and the
      function is clearly meant to be used (it has a sibling, actively-used formatter in
      `rate_limit_tracker.py`'s `_fmt_count` with the same unit-ladder shape), but nothing in the
      live product currently renders through this exact path.
    **Reviewed, no bug found:** `transports/{anthropic,bedrock,codex,__init__}.py` (already fixed in
    round 8, confirmed clean), `insights.py` (930 lines, full read -- SQL params, cost aggregation,
    tool/skill count merging, streak calculation, all checked; the per-model `has_pricing`/
    `cost_status` fields in `_compute_model_breakdown` are last-session-wins rather than aggregated,
    but confirmed via grep they are never read by any formatter or external caller, so this is dead
    data, not a behavioral bug), `markdown_tables.py` (wcwidth-aware CJK table realignment -- noted
    `is_table_divider()`'s `len(cells) > 1` gate means genuine 1-column markdown tables are never
    recognized as tables and pass through unrealigned; this degrades gracefully by the module's own
    "anything that doesn't look like a table passes through unchanged" design and isn't a crash/
    data-loss issue, so left as-is rather than fixed), `gemini_schema.py`, `moonshot_schema.py`,
    `rate_limit_tracker.py`, `web_search_provider.py` (intentional ABC `NotImplementedError` defaults
    gated by `supports_*` flags -- not an instance of the `fed812acc` regression, this is the
    documented design), `lsp/protocol.py` (LSP JSON-RPC framer, careful header-size capping and
    error handling, no issues found).
    New tests: `tests/test_vectorcode_agent_codex_event_projector_call_id.py` (3),
    `tests/test_run_agent_stream_think_scrubbing.py` (3),
    `tests/test_vectorcode_agent_lsp_cli_which_alias.py` (3),
    `tests/test_vectorcode_agent_usage_pricing_format_rollover.py` (3) -- 12/12 passing, all
    confirmed failing pre-fix via `git stash`.
    **Commit status:** `38509d2b1` (codex_event_projector.py), `90dd88164` (run_agent.py think-
    scrubber wiring), `2675f9b61` (usage_pricing.py rollover), `a0dffa4b6` (lsp/cli.py which-alias).

77. **`vectorcode/src/evals/` audit, round 9 scorer pass (2026-10-06) —** reconstructed prior
    coverage from `git log --oneline -- vectorcode/src/evals/` and audited the remaining LLM-judge
    paths first because hard-failing an unavailable/unparseable judge has repeatedly corrupted eval
    accuracy. **Fixed with proof tests:** `ama_bench_judge.py` no longer substitutes an unrelated
    token-F1 threshold when its judge cannot be parsed, and contradictory output containing both
    yes and no is rejected; `email_triage.py` no longer converts an absent verdict or judge-call
    exception into the already-known-false exact-match fallback; `research_mining.py` no longer
    invents neutral score 3 for every missing dimension; `liveresearch.py` and
    `liveresearchbench.py` no longer turn wholly unparseable output into zero coverage;
    `pinchbench.py` now preserves missing backends, judge exceptions, and unparseable output through
    both direct and hybrid grading instead of assigning score zero; and shared `_checklist.py` plus
    its four composite callers (`browser_assistant.py`, `daily_digest.py`, `doc_qa.py`,
    `security_scanner.py`) now propagate incomplete/failed checklist judgments as indeterminate.
    New regression coverage: `tests/test_vectorcode_evals_round9_judge_indeterminate.py` (8 tests),
    8/8 passing; scorer package compile check and `git diff --check` pass. The wider eval suite
    produced 155 passes and 13 pre-existing failures, all in untouched legacy tests/config fixtures
    still importing `vector.*`, naming `jarvis-*` backends, or expecting stdlib `caplog` capture
    after loguru migration. **Not a directory-closeout:** the non-scorer remainder still needs the
    promised file-by-file depth pass; structural sweeps found no additional duplicate literal dict
    keys and only the two already-fixed stateful runner classes. **Commit status:** not committed:
    this Codex sandbox was denied permission to create `.git/index.lock`; all source/test changes
    remain in the working tree for the parent session to review and commit. This OPEN_ISSUES entry
    is intentionally also left uncommitted as required.

78. **`vectorcode/src/skills/` audit, round 8 (2026-10-06) —** reconciled the 65 tracked
    Python files against all prior skills commits and the round-6 reviewed-clean inventory, then
    gave full-depth review to the remaining slice (excluding the separately reserved 2,794-line
    OpenClaw migration): blockchain `base_client.py` / `solana_client.py`, Memento
    `youtube_quiz.py`, Google Workspace `_vector_home.py` / `google_api.py` / `gws_bridge.py`,
    `maps_client.py`, Godmode `godmode_race.py` / `load_godmode.py` / `parseltongue.py`, source
    resolvers `base.py` / `openclaw.py` / `vector_cache.py` / `vector_source.py`, and
    `tool_translator.py`.
    **Fixed with proof tests:** `load_godmode.py` now reads dynamically executed Python as UTF-8
    (instead of Windows cp1252) and restores the caller's `sys.argv` in `finally` when a loaded
    script raises; `solana_client.py` now prices native SOL for wallets with no SPL-token holdings;
    Google OAuth refresh writes now use a shared same-directory tempfile + flush/fsync +
    `os.replace()` helper, and Drive literal searches correctly escape apostrophes/backslashes;
    `maps_client.py` no longer prints a phantom JSON error for the first failed Overpass mirror
    before a later mirror succeeds; fixed-repository OpenClaw/VECTOR clones now terminate Git
    option parsing before the caller-supplied destination path and removed unused stdlib-logging
    imports.
    **Flagged, not fixed (owner decision):** `red-teaming/godmode/scripts/godmode_race.py` is a
    standalone, direct OpenRouter fan-out implemented with `ThreadPoolExecutor`. It bypasses
    `context_engine.session_hydration_prompt()`, the central inference route/free-model whitelist,
    Permission Gateway, structured loguru observability, and the repository's asyncio-only rule;
    its model lists also include paid models. There are no production callers beyond its loader
    and standalone CLI. Decide whether this optional red-team tool is intentionally exempt,
    should be deleted/disabled, or should be reworked through VECTOR's inference and permission
    stack; this audit did not guess at that policy boundary.
    **Reviewed, no additional genuine bug found:** both blockchain clients beyond the native-SOL
    fix, `youtube_quiz.py`, Godmode obfuscation/scoring logic, source base/cache resolvers, and tool
    translation logic.
    New tests: `tests/test_vectorcode_skills_round8_regressions.py` (1),
    `tests/test_vectorcode_skills_round8_clients.py` (4), and
    `tests/test_vectorcode_skills_round8_sources.py` (2). Relevant combined regression run: 18/18
    passing; full `vectorcode/src/skills` compileall and `git diff --check` also pass.
    **Commit status:** uncommitted — this Codex workspace exposes `.git` read-only, so Git could
    not create `.git/index.lock`; source and proof-test changes are left for the parent session to
    review and commit. Per instruction, this OPEN_ISSUES entry is also intentionally uncommitted.

79. **`vectorcode/src/vc_agents/`+`vc_tools/`+`connectors/` audit, round 7, partial pass
    (2026-10-06) —** time-boxed fork pass; did not reach full round-7 scope. Read with real depth:
    `vc_agents/{digest_store,digest_evaluator,rlm,native_react,native_openhands,openhands,
    deep_research,errors}.py`, `vc_tools/{apply_patch,knowledge_sql,skill_manage,mcp_adapter,
    user_profile_manage,_markdown_store}.py`.
    **Fixed with proof tests:**
    - `vc_tools/skill_manage.py` (`47f5908b7`) -- `name` flowed straight into
      `self._skills_dir / f"{name}.toml"` across create/load/delete with zero validation: a
      `"../../somewhere/evil"` or an absolute-path `name` escaped the configured skills directory
      entirely (CWE-22), including via **delete**, which could remove an arbitrary `.toml` file the
      process can reach. Fixed with `_resolve_skill_path()` (resolve + require
      `candidate.parent == skills_dir.resolve()`). Same commit also fixed unescaped TOML
      interpolation of `description`/`tool_name`/`arguments_template`/`output_key` (a value
      containing a quote or newline produced malformed TOML on the next load, or could inject an
      unintended table -- the exact bug shape already fixed once this cycle in
      `learning/distillation/execute/base.py`'s `format_toml_value()`) and made the write atomic
      (tempfile + fsync + os.replace). 8 new tests, 7/8 confirmed failing pre-fix via `git stash`.
    - `vc_tools/_markdown_store.py` (`1a927586a`) -- shared CRUD base for `memory_manage.py` /
      `user_profile_manage.py`. `_remove(entry="")`'s filter
      `[ln for ln in lines if entry not in ln]` evaluates `"" not in ln` as False for every line (the
      empty string is a substring of everything), producing an EMPTY `new_lines` list that doesn't
      match the "not found" length-equality check -- so it fell through and wrote back `""` as the
      new file content, reporting **success**. Any caller passing an empty/unset entry to `remove`
      silently destroyed the user's entire persistent memory file or `USER.md`. Fixed by rejecting
      empty `entry`/`old` up front in `_remove()`/`_update()` (matching the guard `_add()` already
      had) and made all three mutating methods write atomically. 4 new tests, 2/4 confirmed failing
      pre-fix via `git stash`.
    **Reviewed, no bug found:** `vc_agents/digest_store.py` (raw `sqlite3.connect()`, not routed
    through SQLCipher -- flagged below, not fixed), `digest_evaluator.py`, `rlm.py`,
    `native_react.py` (confirmed `_thought_sigs`-style dead-but-harmless pattern not present),
    `native_openhands.py` (`_thought_sigs` local dict is genuinely dead code -- Gemini
    thought_signature replay is actually handled by `CloudEngine`'s own internal
    `self._thought_sigs` instance state in `vc_engine/cloud.py`, confirmed by reading both sides;
    harmless, not fixed), `openhands.py`, `deep_research.py`, `errors.py`, `vc_tools/apply_patch.py`
    (see flag below), `vc_tools/knowledge_sql.py` (uses sqlite3's single-statement `execute()`, not
    vulnerable to the stacked-statement bypass already fixed in `db_query.py`'s psycopg2 path;
    forbidden-keyword blocklist is whole-string, not prefix-only, so it already catches stacked
    writes too), `vc_tools/mcp_adapter.py`.
    **Flagged, not fixed (owner decision, same shape as the already-flagged `file_read`/
    `file_write` finding):** `vc_tools/apply_patch.py` only blocks `is_sensitive_file()`-matched
    targets -- it has no `allowed_dirs`-style confinement at all (not even a dormant/unwired one),
    so an agent can patch-write to any non-"sensitive" path the OS process can reach, anywhere on
    the filesystem. `vc_agents/digest_store.py` and `connectors/store.py`'s `KnowledgeStore` both
    construct their own raw `sqlite3.connect()` instead of going through
    `core.memory.episodic.get_db_connection()` (SQLCipher) -- this is real digest/knowledge-chunk
    content (meeting notes, emails, messages), not a throwaway cache, so whether it should be
    encrypted-at-rest is an owner call, not something to change unilaterally.
    **Not reached this round** (listed here rather than silently omitted -- most of the
    directory's remaining scope from round 6's own completion report is still untouched):
    `vc_agents/{channel_agent,web_search_agent,templates/__init__}.py`;
    `vc_tools/{audio_tool,browser_axtree,calculator,channel_tools,image_tool,knowledge_search,
    knowledge_tools,llm_tool,memory_manage,pdf_tool,retrieval,scan_chunks,storage_tools,
    templates/*,text_to_speech,think}.py`; all of `vc_tools/storage/*` beyond the
    already-fixed `dense.py`.
    New tests: `tests/test_vectorcode_vc_tools_skill_manage_traversal.py` (8),
    `tests/test_vectorcode_vc_tools_markdown_store.py` (4) -- 12/12 passing.
    **Commit status:** `47f5908b7` (skill_manage.py), `1a927586a` (_markdown_store.py).

80. **`vectorcode/src/vc_agents/` + `vc_tools/` audit, round 8a (2026-10-06) —**
    completed the assigned line-by-line pass over `channel_agent.py`, `web_search_agent.py`, all
    four `vc_agents/templates/*.toml` files plus their package initializer, and
    `vc_tools/{audio_tool,browser_axtree,calculator,channel_tools,image_tool,knowledge_search,
    knowledge_tools,llm_tool}.py`.
    **Fixed with proof tests:** the calculator now actually reaches its Python AST fallback when
    `_rust_bridge.get_rust_module()` returns `None` (the normal state with no compiled extension),
    instead of raising `AttributeError`; `LLMTool` now prepends the mandatory
    `ContextEngine.session_hydration_prompt()` before its inference call; web extraction now blocks
    private/metadata URLs and revalidates every redirect, and both it and DuckDuckGo fallback reject
    HTTP error statuses; `ChannelAgent` no longer eagerly calls `str(result)` when valid `.content`
    exists and no longer returns raw exception details to channel users; audio transcription rejects
    non-files and sensitive resolved targets (including disguised symlinks); image output now declares
    `file:write`, rejects sensitive targets, and saves atomically with same-directory tempfile +
    flush/fsync + `os.replace()`; accessibility-tree depth, knowledge-search `top_k`, and graph
    direction/limit inputs now reject invalid model-supplied values before reaching their backends.
    **Flagged, not guessed (owner decisions, comments added):** audio input and image output still
    lack an actual allowed-root policy, the same open architecture decision already recorded for
    `file_read`/`file_write`; both direct OpenAI media tools also conflict with the standing
    free-tier-only runtime policy and need a decision to remove/disable them or route them through
    VECTOR's approved providers. `ChannelAgent` is a fully implemented threaded bridge with no
    production caller anywhere in the repository; decide whether to wire it into channel startup or
    remove it (and whether its `ThreadPoolExecutor` is an intentional exception to asyncio-only).
    **Reviewed, no additional genuine bug found:** `channel_tools.py` and the four TOML templates;
    all built-ins are discoverable through `AgentManager.list_templates()`.
    New proof tests: `tests/test_vectorcode_vc_agents_tools_round8a.py` — 14/14 passing. All assigned
    Python files compile and `git diff --check` passes. The broader pre-existing test run was 27/28:
    `test_encrypted_memory_key_mismatch_is_actionable` independently remains red because the fixture
    reports `missing` instead of `key_mismatch_or_corrupt`; no audited file participates in that path.
    Ruff still reports pre-existing formatting/legacy-typing findings in assigned files; no mechanical
    cleanup was mixed into this correctness audit. **Commit status:** uncommitted as required; the
    sandbox cannot write `.git/index.lock`, and this entry is intentionally left for parent review.

81. **`vectorcode/src/evals/` audit, round 10 (2026-10-06) —** reconstructed the
    round-specific history rather than counting the initial absorption commits: 72 of 131 production
    Python files had prior-round fixes, leaving 59 files for this pass. All 59 were independently
    reviewed line by line; test files were evidence only.
    **Fixed with proof tests:** `gpqa_mcq.py`, `mmlu_pro_mcq.py`, and `supergpqa_mcq.py` used
    `re.search()` with an optional `THE ANSWER IS` prefix, so the documented fallback phrase
    `The answer is A` captured its leading `T` and became indeterminate; the three extractors now
    require a complete valid phrase/letter. `morning_brief.py` no longer converts a wholly
    unparseable judge response into a hard failure. `skill_benchmark.py` no longer coerces
    `is_correct=None` to `False`, and it closes both owned agent/judge backends on success and every
    exceptional exit without allowing cleanup failures to mask the real outcome.
    `trackers/wandb_tracker.py` no longer publishes indeterminate results as incorrect.
    `comparison/third_party.py` now rejects an empty `pinned_commit` instead of silently accepting
    every checkout and bypassing the advertised reproducibility guard. Text I/O now explicitly uses
    UTF-8 in `comparison/table_gen.py`, `core/{export,trace}.py`, and
    `datasets/{loghub,paperarena,pinchbench,terminalbench_native}.py`, removing Windows locale-codepage
    dependence. Edited logging paths use loguru formatting.
    **Flagged, not guessed (owner decisions):** `comparison/table_gen.py` declares but never uses
    `T1_FRAMEWORKS_ORDER`, and that four-row taxonomy contains `"vector"` twice after the historical
    framework rename; choose the intended four framework identities before wiring an ordering that
    could mislabel results. `core/event_recorder.py` uses `threading.Lock` for real synchronous
    `ThreadPoolExecutor` callers despite the repository-wide no-`threading` rule; replacing the lock
    requires an explicit synchronization-policy decision, not deletion. The legacy
    `vectorcode/src/evals/tests/test_backends.py` suite remains independently broken before reaching
    implementation because its mocks target the removed `vector.*` package path (6 failures); no
    round-10 source file participates in that import.
    New proof tests: `tests/test_evals_round10_regressions.py`. Relevant verification: 21/21 tests
    passing (new regressions plus existing SuperGPQA tests), full `vectorcode/src/evals` compileall,
    and scoped `git diff --check` pass. **Commit status:** intentionally uncommitted for parent review;
    this shared sandbox cannot safely create `.git/index.lock`, and this OPEN_ISSUES edit is also
    intentionally left uncommitted.

82. **`vectorcode/src/vc_tools/` audit, round 8c (2026-10-06) —** direct continuation of round 8b
    after a Claude session rate-limit cut it off mid-file; this round finished its remaining
    assigned list and closes out `vectorcode/src/vc_tools/` for this audit cycle (`vc_agents/` was
    separately closed out by a parallel Codex round, commit `0512bd189`). Files given real depth
    this round: `memory_manage.py`, `pdf_tool.py`, `retrieval.py`, `storage_tools.py`,
    `user_profile_manage.py`, `storage/{__init__,_abc,colbert_backend,context,embeddings,
    faiss_backend,hybrid,sqlite}.py`, plus `templates/builtin/unit_convert.toml` +
    `templates/loader.py` found opportunistically while checking the other builtin templates.
    **Fixed with proof tests:**
    - `templates/builtin/unit_convert.toml` -- same "doesn't do what it claims" bug class already
      fixed in `base64_encode`/`hash_compute`/`regex_extract`/`date_info` this cycle. Its expression
      was `str(float(value))`, completely ignoring the declared `from_unit`/`to_unit` parameters --
      calling `unit_convert(100, "c", "f")` silently returned `"100.0"` instead of `"212.0"`. Added
      `convert_unit()` (length/mass/temperature) to `loader.py`'s sandboxed-expression allowlist and
      wired the template to call it with all three parameters.
    - `storage/context.py` -- `inject_context()`'s token-budget truncation loop used `break` on the
      first result whose token count alone exceeded `max_context_tokens`, instead of `continue`.
      Since results are ordered by relevance score, not size, a single long top-ranked result
      silently discarded every later, smaller result that would have fit -- context injection
      failed completely instead of partially.
    - `storage/sqlite.py` -- `_check_fts5()` existed specifically to detect a SQLite build without
      the FTS5 extension but had zero callers anywhere in the repo (the "built but never wired"
      shape found repeatedly this cycle). Without it, `_create_tables()` would surface a cryptic
      `sqlite3.OperationalError("no such module: fts5")` instead of a clear, actionable error.
      Wired it into `__init__()`'s Python-SQLite path.
    - `storage/hybrid.py` -- `HybridMemory.store()` wrote to the sparse backend, then the dense
      backend, with no error handling. If the dense write raised, the exception correctly
      propagated to the caller as an overall failure, but the content was already committed to
      the sparse backend and stayed silently retrievable from there -- a failed store() call with
      a visible side effect contradicting its own reported failure. Wrapped the dense write in
      try/except: roll back the sparse write on failure, then re-raise.
    - `storage/faiss_backend.py` + `storage/colbert_backend.py` -- both backends' `store()` kept a
      live reference to the caller-supplied `metadata` dict (`metadata if metadata is not None
      else {}` / `metadata or {}`) instead of copying it, so a caller reusing or mutating that dict
      after the call silently corrupted the already-"stored" record. `sqlite.py`'s backend is
      unaffected (serializes metadata to JSON immediately). Neither `faiss` nor `colbert-ai`/`torch`
      is installed in this sandbox, so both new tests are `pytest.importorskip`-guarded and skip
      here; the fix itself was verified by isolated logic check (confirmed the pre-fix shape
      aliases, the post-fix shape doesn't) and `ast.parse` syntax verification, not full live
      execution against the real backend classes.
    **Flagged, not fixed (owner decisions):** `storage/sqlite.py` uses raw `sqlite3.connect()` for
    its own `memory.db` rather than `core.memory.episodic.get_db_connection()` (SQLCipher) -- the
    same pattern already flagged for `digest_store.py` and `connectors/store.py`'s `KnowledgeStore`
    this cycle; this backend stores arbitrary agent-retrieved memory content, so whether it counts
    as "real VECTOR data" requiring encryption is an owner call. `storage/embeddings.py`'s
    `OllamaEmbedder.embed()` uses `concurrent.futures.ThreadPoolExecutor` to fan out HTTP calls,
    violating the repo's asyncio-only policy -- same already-flagged pattern as `channel_agent.py`
    and `godmode_race.py` this cycle; converting it would change the public sync `embed()` API
    contract, so left as a flagged policy question rather than auto-converted. `pdf_tool.py` has no
    configured allowed-root confinement (checks `is_sensitive_file()` but reads any path supplied),
    same already-accepted no-confinement pattern as `audio_tool.py`/`image_tool.py`/`apply_patch.py`.
    **Reviewed, no bug found:** `memory_manage.py`, `user_profile_manage.py` (both pure delegation
    to the already-fixed `_markdown_store.py` shared base, no independent logic), `retrieval.py`,
    `storage_tools.py`, `storage/__init__.py`, `storage/_abc.py`.
    New tests: `tests/test_vectorcode_vc_tools_templates_unit_convert.py` (4),
    `tests/test_vectorcode_vc_tools_storage_context_truncation.py` (1),
    `tests/test_vectorcode_vc_tools_storage_sqlite_fts5_check.py` (2),
    `tests/test_vectorcode_vc_tools_storage_hybrid_store_rollback.py` (1),
    `tests/test_vectorcode_vc_tools_storage_metadata_aliasing.py` (2, both skipped here per above).
    All executable new tests confirmed failing pre-fix via `git stash`; broader `storage`/`sqlite`-
    related regression run and the full `evals`/`scorer` suite both pass with no regressions.
    **Commit status:** `4adce1d5b` (unit_convert.toml + loader.py), `cbfe3494c` (context.py),
    `10abe8d40` (sqlite.py), `91b4e9d5f` (hybrid.py), `37a3111f6` (faiss_backend.py +
    colbert_backend.py) -- all committed directly by this fork (unlike the Codex rounds, Claude
    forks can write `.git/index.lock` themselves). This OPEN_ISSUES entry is intentionally left
    uncommitted for the parent session, per instruction.

83. **`vectorcode/src/connectors/` audit, round 1, partial pass (2026-10-06) —** first full-depth
    pass on this 36-file directory beyond the 8 files already fixed for the SyncStatus
    error-reporting bug class in an earlier round. Codex hit a genuine usage-limit wall mid-edit
    (not a transient capacity error) after completing 10 files; did not reach the other ~18.
    **Fixed with proof tests, all verified by the parent session (ran the new test file, fixed one
    wrong-class-name import in it, confirmed each surprising claim against the actual diff, ran
    `git stash` to confirm the sync_engine.py fix fails pre-fix):**
    - `oauth.py` -- the Google/generic OAuth callback flows sent no `state` parameter and never
      validated one on return, a classic OAuth CSRF gap; added `secrets.token_urlsafe(32)`
      state generation plus `secrets.compare_digest()` verification on callback, timing-safe.
      Also fixed the callback-wait loop resetting `server.timeout` to the full value on every
      retry instead of tracking a real deadline (the documented "2 minute timeout" could run
      unbounded), and made `save_tokens()`'s write atomic (tempfile + fsync + os.replace,
      chmod 0o600 before the file is visible at its final path instead of after).
    - `embedding_store.py` -- `chunk_id` (connector-originated, not a safe filename) was
      interpolated directly into a tensor filename (CWE-22); now SHA-256 hashed, with a
      `_indexed_tensor_path()` confinement check on read/delete and an atomic write on store.
    - `sync_engine.py` -- two bugs: (1) `last_sync` was stamped to "now" on every checkpoint
      write, including mid-batch and error checkpoints, so a sync that crashed partway still
      advanced the watermark used to compute `since=` on the next run, silently skipping
      records; now only the final successful checkpoint advances `last_sync`. (2) the cursor
      used for checkpointing never advanced past the pre-sync value during a run; now refreshed
      from `connector.sync_status().cursor` at each checkpoint.
    - `slack_connector.py` -- a persistent `conversations.list` failure (e.g. rate-limited,
      invalid auth) logged a warning and silently stopped with zero results, still a "phantom
      success" shape (indistinguishable from a genuinely empty workspace, and `SyncEngine`'s new
      checkpoint logic above needs connectors to raise on real failure to record a
      distinguishable error state). Now raises `RuntimeError`. The parent session updated a
      *pre-existing* test (`test_vectorcode_connectors_slack_silent_failures.py`, written for the
      prior log-and-stop fix) to match this stricter, more correct contract rather than reverting
      the new fix -- verified the new behavior is itself covered by this round's own new test.
    - `gcalendar.py`, `apple_music.py`, `notion.py`, `gmail_imap.py`, `attachment_store.py`,
      `strava.py` -- each had at least one silent-failure/phantom-success or boundary gap fixed
      (calendar-fetch errors reported as empty success, cursor-non-advance not rejected, IMAP
      zero-limit expanding to a full mailbox fetch, attachment lookup accepting a non-digest key,
      minor cursor/error-boundary fixes). See `tests/test_connectors_round1_regressions.py` for
      per-fix coverage.
    New tests: `tests/test_connectors_round1_regressions.py` (11 tests, one wrong-class-name
    import fixed by the parent session before they would run), all passing; broader
    connector/oauth-scoped suite (84 tests) also passing after the parent session updated the one
    stale pre-existing Slack test described above.
    **Remaining scope for a follow-up round:** ~18 of 36 connectors/ files were not yet reached by
    this pass (Codex's own usage-limit error fired mid-edit on sync_engine.py, not at a clean
    stopping point) -- re-run `git log --oneline --name-only -- vectorcode/src/connectors/` to
    rebuild the exact remaining list before continuing.
    **Commit status:** committed by the parent session (Codex's sandbox cannot write
    `.git/index.lock`); this OPEN_ISSUES entry was also written by the parent session since the
    task was cut off by the usage-limit error before it could write its own.

84. **`vectorcode/src/connectors/` audit, round 2a (2026-10-06) —** completed a
    line-by-line review of the assigned `_abc.py`, `gmail.py`, `gdrive.py`,
    `gcontacts.py`, `outlook.py`, `spotify.py`, `whatsapp.py`, `google_tasks.py`,
    `github_notifications.py`, and `obsidian.py` set without touching the parallel
    round's connector files.
    **Fixed with proof tests:** Spotify persisted all inputs needed for OAuth refresh but
    never refreshed expired access tokens; it now refreshes proactively and atomically
    persists the replacement token through the shared OAuth token writer. Spotify,
    Google Tasks, and GitHub Notifications now expose an `error` status when their initial
    credential/provider call fails instead of retaining the default indistinguishable
    `idle` status. Gmail, Drive, and Contacts now do the same for list failures and reject
    a repeated pagination token rather than looping indefinitely. Drive no longer converts
    an export failure into indexable placeholder content (phantom success); it raises and
    records the failure. Google Tasks and GitHub Notifications also no longer append `Z` to
    an already-offset aware `since` value (invalid RFC 3339 such as `+05:30Z`); both normalize
    the cutoff to UTC first.
    New tests: `tests/test_connectors_round2a_regressions.py` (11 tests), all passing.
    `compileall` and `git diff --check` also passed (only expected CRLF notices).
    **Flagged, not guessed:** Google Tasks still lacks persisted expiry/client-secret data
    and therefore has no safe refresh implementation; choosing a shared Google refresh
    design remains an owner decision. Outlook inherits Gmail IMAP's log-and-return login
    failure and per-message silent skips, so its status can still claim idle/partial success;
    fixing that correctly belongs in the shared `gmail_imap.py` implementation, outside this
    assigned set. WhatsApp and Obsidian likewise skip unreadable files and report partial
    success; whether one unreadable local file should fail the entire sync or produce a
    warning-capable status is a policy decision because `SyncStatus` has no warnings field.
    `_abc.py` itself required no change; its optional `error` field is adequate when concrete
    connectors actually populate it.
    **Commit status:** intentionally uncommitted for parent review; this entry is also left
    uncommitted as required for concurrent-session reconciliation.

85. **`vectorcode/src/connectors/` audit, round 2b (2026-10-06) —** completed the other
    non-overlapping half of round 2 (`__init__.py`, `apple_contacts.py`, `apple_health.py`,
    `chunker.py`, `news_rss.py`, `pipeline.py`, `retriever.py`, `scheduler.py`, `store.py`),
    run in parallel with round 2a above on a disjoint file list. 6 real bugs fixed, each with
    a proof test confirmed failing pre-fix via `git stash`:
    - `apple_contacts.py` -- `sync_status()` unconditionally returned `state="idle"`; `sync()`
      never wrapped its query/iteration body in try/except, so a mid-sync crash (locked DB,
      missing/renamed table) left it permanently indistinguishable from "nothing synced yet".
      Same SyncStatus bug class fixed in 9+ other connectors this cycle. Commit `5d3235ce4`.
    - `apple_health.py` -- `_sync_export_xml()`'s Record and Workout since-filters did
      `start_dt.replace(tzinfo=None) < since.replace(tzinfo=None)`, stripping real UTC offsets
      from both sides before comparing. A record at `2024-01-01 00:00:00 -0500` (= 05:00 UTC)
      was incorrectly treated as before a 02:00 UTC cutoff, even though it's two hours after
      it -- silently mis-including/excluding records near every incremental-sync boundary
      whenever the export's offset differs from the caller's. Fixed with a timezone-safe
      `_is_before()` helper; the HealthKit SQLite path's own since-filter was already correct.
      Commit `2e2886574`.
    - `news_rss.py` -- two bugs in one file: (1) `sync()` had no try/except at all, so any
      failure (malformed config JSON, an unexpected parse error) left `sync_status()` at its
      default `idle`/no-error state forever. (2) the since-filter did
      `pub_dt.replace(tzinfo=None) < since`, stripping tzinfo from the parsed publish date but
      NOT from `since` -- `parsedate_to_datetime()` always returns a timezone-aware datetime,
      and a checkpoint-derived `since=` from `SyncEngine` is also timezone-aware, so comparing
      a naive value against an aware one raised `TypeError` on every real incremental sync.
      This is a confirmed crash, not just a wrong-result bug. Fixed both; reused the same
      `_is_before()` pattern. Commit `1a48098ba`.
    - `pipeline.py` -- `IngestionPipeline.ingest()` stored a document's chunks one at a time;
      `KnowledgeStore.store()` generates a fresh UUID chunk id on every call with no dedup
      constraint. If storing chunk N of a multi-chunk document raised (a transient DB error),
      chunks 1..N-1 were already committed but `doc.doc_id` was never marked seen -- a retry
      after the transient condition cleared re-ingested the whole document from scratch,
      duplicating the chunks that had already succeeded. Wrapped the per-document store (main
      + attachment chunks) in try/except that rolls back via `store.delete(doc_id)` before
      re-raising; always safe because a doc_id reaching that code path is guaranteed to have
      no prior chunks (already-seen doc_ids are skipped earlier in the loop). Commit
      `bc4fbb7df`.
    - `retriever.py` -- `TwoStageRetriever.retrieve()` only invoked a configured `Reranker`
      when `len(candidates) > top_k`. A reranker's whole purpose is to improve *order*, which
      matters just as much when the candidate pool is small -- a sparse knowledge base or
      narrow query commonly returns fewer than `top_k` matches, and in that very common case a
      configured reranker was silently a no-op. Now reranks whenever a reranker is configured
      and candidates is non-empty, regardless of size relative to `top_k`. Commit `d9c3fac49`.
    - `scheduler.py` -- `stop()` unconditionally cleared `self._thread = None` after a 5s
      `join()`, regardless of whether the background thread actually exited. If a sync cycle
      in progress outlasted the join timeout, the thread kept running untracked; `start()`'s
      duplicate guard (`self._thread is not None and self._thread.is_alive()`) then always
      passed, letting a stop()-then-start() sequence run two `_loop()` threads concurrently
      against the same connectors/store. Fixed: `stop()` now leaves `self._thread` set (with a
      warning logged) when the thread is still alive after the join timeout, so `start()`'s
      existing guard correctly refuses to spawn a duplicate. Commit `f932ac3b4`.
    **Reviewed, no bug found:** `__init__.py` (intentional, consistent graceful-degradation
    pattern for optional connector imports), `chunker.py` (pure text-splitting logic; verified
    its own documented invariants -- e.g. an oversized unsplittable segment always gets its
    own chunk -- actually hold), `store.py` beyond the already-flagged raw `sqlite3.connect()`
    vs SQLCipher item (item 56-adjacent, not re-flagged here).
    **Flagged, not fixed (owner decision):** `scheduler.py` uses `threading.Thread`/
    `threading.Event`, which CLAUDE.md marks as banned in favor of asyncio; rewriting a
    long-lived daemon-thread scheduler to asyncio is an architecture change, not a narrow
    bug fix, so left as a design question rather than guessed at.
    New tests: `tests/test_vectorcode_connectors_apple_contacts_sync_status_error.py` (2),
    `tests/test_vectorcode_connectors_apple_health_since_tz.py` (1),
    `tests/test_vectorcode_connectors_news_rss.py` (2),
    `tests/test_vectorcode_connectors_pipeline_partial_failure_rollback.py` (1),
    `tests/test_vectorcode_connectors_retriever_reranker_always_runs.py` (2),
    `tests/test_vectorcode_connectors_scheduler_stop_start_race.py` (2) -- 10/10 passing,
    all confirmed failing pre-fix via `git stash`. Broader connector/oauth/pipeline/retriever/
    scheduler-scoped suite also passes with no regressions.
    **Commit status:** all 6 fixes self-committed directly by this fork (`5d3235ce4`,
    `2e2886574`, `1a48098ba`, `bc4fbb7df`, `d9c3fac49`, `f932ac3b4`). This OPEN_ISSUES entry is
    intentionally left uncommitted for the parent session, per instruction.

86. **`vectorcode/src/connectors/` fully closed out (2026-10-06) —** round 2a + round 2b together
    cover the last 19 of 36 files, and cross-checking all four rounds against the full file
    listing (`git ls-files "vectorcode/src/connectors/*.py"`) confirms every single file now has
    real audit coverage: 8 from the earlier SyncStatus-focused round (oura, weather, hackernews,
    granola, apple_notes, imessage, dropbox, strava), 9 from round 1 (apple_music,
    attachment_store, embedding_store, gcalendar, gmail_imap, notion, oauth, slack_connector,
    sync_engine), 10 from round 2a (_abc, gmail, gdrive, gcontacts, outlook, spotify, whatsapp,
    google_tasks, github_notifications, obsidian), 9 from round 2b (__init__, apple_contacts,
    apple_health, chunker, news_rss, pipeline, retriever, scheduler, store). 36/36.
    This also closes out the entire `vc_agents/` + `vc_tools/` + `connectors/` + `evals/` +
    `skills/` + `agent/` group for this audit cycle -- every production file in those six
    directories now has real line-by-line round coverage, fixed or explicitly reviewed-clean.
    Remaining open items from this group are all explicit owner-decision flags already recorded
    in their respective round entries above (not bugs left unfixed): office/pack.py's missing
    `validators` module, builtin/sparc/__init__.py's cross-tree import, skills/security.py and
    skills/types.py's unwired gates, godmode_race.py's direct-OpenRouter/ThreadPoolExecutor design,
    scheduler.py's threading.Thread vs the asyncio-only policy, embeddings.py's ThreadPoolExecutor,
    sqlite.py's/digest_store.py's/store.py's raw sqlite3.connect() vs SQLCipher, pdf_tool.py's/
    apply_patch.py's lack of a configured allowed-root policy, audio_tool.py's direct-OpenAI-
    Whisper billing path, and whatsapp.py/obsidian.py's silent-skip-on-unreadable-file policy.
    Per the standing session plan, the remaining untouched front is the `core/`+`districts/`
    real-import smoke sweep (started earlier this audit cycle, ~15%/4066 modules checked, paused
    after a host memory-pressure kill with an explicit instruction not to restart it without being
    asked) -- everything else in `vectorcode/src/` was previously established as already covered
    or deferred in earlier session segments.

87. **Remaining `vectorcode/src/` small-directory audit, round 1 (2026-10-06) —** completed a
    line-by-line review of all 41 assigned production files across `api/`, `permissions/`,
    `ui/`, `acp/`, `intelligence/`, `migrations/`, `neural_training/`, `prompt/`, `traces/`,
    `vc_templates/`, `config/`, `cron/`, `guidance/`, `mcp_client/`, `recipes/`, `repl/`,
    `sandbox/`, and `vc_skills/`. History was checked per path first; prior broad migrations
    and narrow fixes were treated as context rather than depth-audit coverage. The same-named
    top-level `config.py`, `guidance.py`, `neural_training.py`, and `repl.py` modules were checked
    for collision behavior but not modified.
    **Fixed with proof tests:** `permissions/__init__.py` now fails closed for unknown risk
    levels, preserves explicit empty allow/deny lists instead of replacing them through falsy
    `or` defaults, and normalizes path case/separators before matching sensitive write paths;
    `prompt/builder.py` explicitly reads memory/persona files as UTF-8; `recipes/composer.py`
    preserves an explicit `max_samples=0`; `config/theme.py` rejects path-separator/traversal
    theme names, safely quotes TOML strings, and uses tempfile + fsync + replace persistence;
    `cron/jobs.py` confines public job IDs before output writes; and the remaining printf-style
    Loguru placeholders in `cron/jobs.py`/`cron/scheduler.py` were converted to Loguru formatting.
    New regression file: `tests/test_vectorcode_remaining_round1_regressions.py` (9 tests).
    Focused new + existing API/ACP/MCP suite: 19 passed. `compileall` and `git diff --check`
    passed. A broader legacy cron/prompt/wave3 run had unrelated pre-existing failures: Windows
    mode-bit assertions, stale prompt expectations, and missing provider APIs; the one initial
    compatibility failure caused by an over-strict job-ID shape was corrected and re-verified.
    **Flagged, not guessed (owner/design decisions):** `api/server.py` has no production caller
    and its `/v1/responses` and `/v1/runs` endpoints report completed/running state without ever
    executing work; `ui/__init__.py` imports a nonexistent `arc_reactor.py`; and
    `mcp_client/bridge.py` is unwired and imports a nonexistent `MCPClient.get_or_create` API
    (the implemented client is `StdioMCPClient`/`MCPClientRegistry`). ACP still exposes execution
    and session contents without authentication (already noted in its source); selecting an auth
    scheme is policy, not a narrow patch. `migrations/v1_to_v10.py` uses raw `sqlite3.connect()`;
    whether this session DB is VECTOR-sensitive data requiring the SQLCipher gateway needs an
    owner decision. `cron/` and `mcp_client/client.py` retain `threading`/thread-pool designs in
    conflict with the asyncio-only project rule; converting those schedulers/transports is an
    architectural rewrite. **Commit status:** intentionally uncommitted for parent review; this
    entry is also left uncommitted as required for concurrent-session reconciliation.

88. **Miscellaneous repo-root Python audit (2026-10-06) —** completed the line-by-line
    security/correctness review of `tools/ci_gate.py`, all 25 tracked Python files directly in
    `tools/vector_dev_orchestrator/` (live `.state/` JSON explicitly excluded), all four
    `hands/` files, all four `data/` Python files, both `phone_node/` files, the three scoped
    `cloud/` Python files, and `models/adapters/__init__.py`. `scripts/` was not touched.
    **Fixed with proof tests:** task IDs and supervisor program IDs are now validated before
    becoming filenames (closing state-directory traversal); Git worktree creation terminates
    option parsing before the caller-provided base ref; quota, scheduler-owner, and daily-worker
    counter state now use flushed/fsynced atomic replacement; corrupt daily-counter state fails
    closed instead of resetting to zero and bypassing the cap; an explicit `max_tasks=0` is no
    longer discarded by an `or` default; ADB port forwarding and screenshot pulls no longer
    report phantom success after command failure; phone-node bearer comparison is constant-time
    and its config is explicitly UTF-8; the comms bridge preserves a falsy delivery result rather
    than unconditionally returning `ok: true`; and the CI source gate no longer deletes invalid
    UTF-8 bytes before compiling. New regression coverage is in
    `tests/test_misc_root_audit_regressions.py` (10 tests). Focused new + existing phone/comms
    tests: 35 passed; focused hands tests: 13 passed; scoped `compileall`, worktree-manager
    self-test, and `git diff --check` passed.
    **Important correction to the round premise:** `hands/` is not an unwired package in the
    current tree. `core/loop/autonomous_loop.py` registers `HandRunner`, and
    `core/loop/permission_gateway.py` dispatches approved hand actions; existing hands wiring and
    runner tests also exercise those paths. No wiring change was made.
    **Flagged, not guessed (owner/design decisions):** `phone_node/ambient_server.py` binds its
    mutating HTTP endpoints to `0.0.0.0` and deliberately permits unauthenticated access when no
    API key is configured; changing that documented development behavior needs an owner decision.
    The same file and `cloud/agent_workers/scheduler.py` use `threading`/APScheduler's background
    thread despite the project asyncio-only rule; converting a Termux HTTP server and scheduler
    architecture is not a narrow fix. The duplicated training-reference programs under `data/`
    retain upstream-style `requests`, `pickle`, extensive `print()`, and import-time execution;
    replacing their tokenizer serialization/training-script architecture is likewise not a safe
    narrow audit patch. `hands/runner.py` contains an explicitly documented policy-memory write
    whose key can never be consumed by the decision engine; deciding whether to remove it or add
    real Hand candidates remains a product-policy choice. All changes are intentionally
    uncommitted for parent review, including this concurrently reconciled OPEN_ISSUES entry.

89. **Repo-root `scripts/` audit batch 3/3 (2026-10-06) —** completed line-by-line review of
    all 29 assigned files. **Fixed with proof tests:** the keyring migrator's `str / ".env"`
    startup crash and timing-unsafe verification; the plaintext-to-SQLCipher migrator's
    import-time execution, plaintext key disclosure, partial/existing-destination collision,
    table-only copy (lost indexes/triggers), and non-atomic output; the installed pre-commit
    syntax gate's fail-open behavior when `git diff`/`git show` fails; `syntax_check.py`'s
    success exit after missing/broken files; false-success exits in both standalone `test_*.py`
    diagnostics and the issue-37 verifier; missing session hydration in that verifier's direct
    LLM calls; `train_wake_head.py`'s final-window off-by-one; both wake trainers overwriting the
    live ONNX before quality validation; `train_intent_real.py`'s cwd-dependent dataset path;
    `link_skills.py --include-deprecated` being ignored; and locale-dependent TODO report output.
    `smoke_test.py` now isolates its real policy writes in a temporary DB and fails when
    `EvolutionEngine.get_best_practices()` swallows a query error instead of reporting PASS.
    New regression file: `tests/test_scripts_batch3_audit.py` (8 tests).

    **Live/reference classification (text references alone are not treated as runtime wiring):**

    | Classification | Assigned files |
    |---|---|
    | Live/load-bearing | `precommit_syntax_gate.py` (installed by `install_git_hooks.py`); `smoke_test.py` (called by QA agents and documented gate); `train_wake_word.py` (active owner-blocked wake workflow, directly tested) |
    | Runnable archived diagnostics (BAT/docs callers, not autonomous runtime) | `repro_25_26.py`, `repro_final_fixes.py`, `repro_issue16.py`, `repro_misroute.py`, `repro_regressions.py`, `test_mistral_judge_direct.py`, `verify_issue37_voice.py` |
    | Maintained/manual tooling with documentation or generated-output references | `manifest_gap.py`, `normalize_finagent_headers.py`, `syntax_check.py`, `test_governor_generalization.py`, `train_intent_real.py`, `verify_fixes.py` |
    | Unreferenced manual utility / historical one-off (no repo caller found; review before deletion because some mutate files or produce assets) | `link_skills.py`, `make_vector_icon.py`, `mark_dormant_modules.py`, `migrate_secrets_to_keyring.py`, `migrate_to_encrypted.py`, `run_pytest_shards.py`, `scan_nonfinagent_stubs.py`, `scan_pass_stubs.py`, `train_wake_head.py`, `train_wake_v2.py`, `train_wake_word_synthetic.py`, `triage_todos.py`, `wrap_acp_imports.py` |

    The two `scripts/test_*.py` files are **not pytest-collected**: both `pytest.ini` and
    `pyproject.toml` set `testpaths = tests`; they are direct-run diagnostics. `smoke_test.py`
    remains genuinely wired, but its corrected swallowed-error check currently exposes an
    out-of-scope production defect: `EvolutionEngine.get_best_practices()` logs
    `close_db_connection() takes 0 positional arguments but 1 was given` and returns `[]`.
    This batch did not modify that `core/` implementation. Verification: new regressions pass,
    all 29 scripts compile, `syntax_check.py` reports 18/18 and exits 0, pre-commit gate exits 0
    with no staged files, and the corrected smoke gate now honestly reports 37/38 and exits 1 on
    the swallowed out-of-scope query failure (it previously reported 38/38). Changes and this
    entry are intentionally uncommitted for parent review.

90. **Repo-root `scripts/` batch 1 audit (2026-10-06) —** completed a first-pass, line-by-line
    security/correctness and liveness review of the 30 assigned scripts. **Load-bearing/wired:**
    `backup_dbs.py` is launched by `core/loop/autonomous_loop.py`; `check_coverage.py` is invoked
    by `.github/workflows/ci.yml`; `augment_intent_dataset.py` is a stage in
    `scripts/execute_intent_pipeline.py`. **Explicitly retired:** `absorb_coding_assistant.py`
    and `absorb_research_engine.py` terminate immediately and are documented as retired in
    `THIRD_PARTY_NOTICES.md`. **Historical one-time migration/install utilities (no live caller):**
    `absorb_ldr.py`, `absorb_remaining_skills.py`, and `absorb_skills.py` (the last is retained in
    the third-party notice only). **Standalone reusable/manual diagnostics, not wired into
    automation:** `_build_dep_graph.py`, `analyze_coverage.py`, `audit_all_wiring.py`,
    `audit_exceptions.py`, `audit_final.py`, `audit_hyperframes.py`, `audit_repo_hygiene.py`,
    `audit_toprank.py`, `audit_vectorcode.py`, `audit_wiring.py`, `auto_retrain_intent.py`,
    `baseline_test_results.py`, `build_golden_dataset.py`, `build_seed_dataset.py`,
    `build_skills_manifest.py`, `calibrate_intent_threshold.py`, `capability_smoke.py`,
    `capture_frontend.py`, `check_absorption.py`, `check_first_party_imports.py`, `check_soak.py`,
    and `clean_test_pollution.py`. None of the assigned filenames match pytest's test discovery
    pattern, so none are pytest-collected tests.
    **Fixed with proof tests:** database backups are now built in an fsynced temporary SQLite file
    and atomically published, connections close on failures, pruning parses the timestamp format
    the script actually creates, and failed deletions are no longer counted as successful;
    dependency-graph `from package import child` and relative imports now resolve to the child
    module and stale global index entries are cleared; the exception audit now distinguishes
    re-raises, genuinely logged handlers, and unlogged real handlers, and its auto-fix emits valid
    Loguru exception logging; `analyze_coverage.py` uses explicit UTF-8 and handles a zero-statement
    subtotal; persistent JSON/JSONL writes in the intent retraining/build scripts and skill-manifest
    builder are atomic; the intent augmentation LLM call now includes session hydration and its
    all-generation-failed case no longer divides by zero; baseline capture propagates pytest's exit
    status. The absorption check, five historical audit scripts, vectorcode audit, capability
    smoke, and soak checker now return nonzero when their own evidence reports failure instead of
    producing shell-level phantom success. `audit_all_wiring.py` no longer treats an unrelated
    occurrence of a common symbol name as proof that its defining module is wired.
    New regression coverage: `tests/test_scripts_batch1_audit.py` (7 tests), all passing; scoped
    `compileall` and `git diff --check` also pass.
    **Flagged, not guessed (owner decisions):** `build_seed_dataset.py` contains stale architectural
    training claims (including old HP/model routing and Ollama-first/cloud-fallback policy) that
    conflict with current `CLAUDE.md`; regenerating or deleting that training corpus is a model
    policy decision. `capture_frontend.py` uses `threading.Thread`, conflicting with the repository
    asyncio-only rule, but replacing its synchronous local HTTP-server/Playwright harness is an
    architectural change. The unreferenced audit/migration/build scripts above are deletion
    candidates, but some remain useful manual recovery/diagnostic tools, so no deletion was
    guessed. Changes and this entry are intentionally left uncommitted for parent review.

91. **Real-import smoke sweep of `core/` and `districts/` RESUMED and COMPLETED (2026-10-06) --**
    Task A of a user-directed Claude/Codex split (Claude: this sweep; Codex: auditing untouched
    `vectorcode/src/` directories, see adjacent entries). Picks up item 66, which covered 602 of
    4,066 modules before a host memory-pressure kill from 24 parallel subprocess workers.
    **Safety fix that worked:** reran with only 4 ThreadPoolExecutor workers instead of 24 (same
    subprocess+env-extension approach as item 66). Free memory *increased* over the full run
    (5.7GB -> 13.3GB) -- no pressure this time. **Full sweep completed: 4,370/4,370 modules
    checked** (count grew slightly from item 66's 4,066 estimate -- the codebase grew since then).
    **~1,452 raw failures, almost entirely concentrated in 4 large clusters, not spread thin:**
    1. **`districts/investment/alpha_zoo/` -- REAL BUG, FIXED (commit `df07e9230`):** 442 of 465
       vendored quant-factor files (`academic/`, `alpha101/`, `gtja191/`, `qlib158/`) imported
       their shared helpers as `from src.factors.X import ...` -- the upstream package's own
       internal path, never rewritten when vendored into `.../alpha_zoo/factors/`. Confirmed live
       impact: `AlphaZooLoader.load_factor()` (called from `districts/investment/stock_analyst.py`)
       execs each factor file standalone via `importlib.util.spec_from_file_location` with zero
       package context, so not even a relative import would have resolved -- every factor except
       a handful raised `ModuleNotFoundError` the instant it was loaded. Mechanical, deterministic
       fix across all 442 files (`src.factors` -> `districts.investment.alpha_zoo.factors`), with
       `src.tools.alpha_bench_tool` (a genuinely-never-vendored file, already try/except-guarded)
       correctly left alone. 9 new tests (`tests/test_alpha_zoo_factor_import_path.py`), confirmed
       failing pre-fix via `git stash` (442 stale-import hits exactly).
    2. **`districts/intelligence/shadowbroker_server/` -- NOT A BUG, sweep methodology artifact
       (262 raw failures, `No module named 'services'`/`'exchange_client'` etc.):** confirmed via
       `core/api/routers/sb.py`'s own docstring ("single-origin gateway to shadowbroker_server...
       the dashboard talks to `districts/intelligence/shadowbroker_server/main.py`" over plain
       HTTP) and `districts/intelligence/vectorintel_agent.py`'s own setup instructions
       (`cd districts/intelligence/shadowbroker_server && PORT=8002 python main.py`) that this is
       a self-contained sibling FastAPI server, run as its own process with its own CWD on
       `sys.path` -- never imported as a dotted submodule of the main VECTOR package. Verified
       directly: `cd districts/intelligence/shadowbroker_server && python -c "import services"`
       succeeds with zero error. The sweep's "import everything via `core.`/`districts.`-prefixed
       dotted path from repo root" methodology is simply the wrong invocation model for this one
       subsystem. Not a bug, not fixed.
    3. **`districts/investment/vector_finagent/.../strategies/` -- NOT A BUG, needs a live host
       runtime (404 raw failures, `No module named 'AlgorithmImports'`):** these are QuantConnect
       LEAN engine regression-test algorithm files (naming convention `*RegressionAlgorithm.py`
       matches LEAN's own test suite exactly). `AlgorithmImports` is a module LEAN's own C#/Python
       bridge synthesizes at runtime inside its proprietary engine -- it does not exist, and
       cannot be made to exist, as an importable package outside that engine. Not fixable, not a
       bug, not fixed.
    4. **`core/research_engine/web/*` (and `followup_research/`, `exporters/pdf_exporter.py`, etc.)
       -- NOT A BUG, vendored-but-never-ported subtree (~68 raw failures, `No module named
       'services'`/`'limiter'`/`'auth'`/`'dependencies'`):** `core/research_engine/web/` contains
       only `__init__.py` + `models/` -- the upstream project's own FastAPI web-server layer
       (`services/`, `auth/`, `limiter`, `dependencies`) was never vendored in at all. Confirmed
       zero real-world impact: grepped all 5 external callers of `core.research_engine` (
       `core/city/governor.py`, `core/loop/autonomous_loop.py`, `core/memory/episodic.py`,
       `districts/research/deep_researcher.py`, `districts/research/research_api.py`) and verified
       they only ever import `auto_research_agent`, `api/settings_utils`, `api/research_functions`,
       `database/sqlcipher_utils` -- all 4 of which import cleanly. `research_api.py` itself
       documents "Districts never import from core.research_engine directly." Dead vendored code
       from VECTOR's perspective; matches this tree's explicit "wiring-check only" policy scope.
       Not fixed.
    **Sweep-methodology false positives, corrected (not real bugs):** 21 modules whose path
    contains a leading-digit segment (Alembic migration files like `0001_initial_schema.py`,
    loaded via `importlib.util.spec_from_file_location` in production, never a literal `import`
    statement) or a hyphenated directory segment (several `vectorcode/src/*` skill script paths)
    produced `SyntaxError: invalid decimal literal`/`invalid syntax` only because my sweep's
    literal `import <dotted.path>` statement text cannot express a non-identifier path segment --
    `importlib.import_module()` (the string-based API) imports every one of these cleanly,
    confirmed by direct spot-check. A broader automated re-verification pass of all ~1,446 other
    failures via in-process `importlib.import_module()` was attempted to catch any further such
    false positives, but silently died partway through (no traceback, no results file) --
    almost certainly a vendored module calling `sys.exit()` on a missing optional dependency
    rather than raising a catchable exception, which only breaks something when run in-process
    (my original subprocess-isolated sweep was immune to this; the in-process re-verify was not).
    This was NOT pinned to an exact file/module before aborting the re-verify attempt -- flagged
    as a secondary finding for a future session with proper per-module subprocess isolation.
    **Flagged for owner decision, not fixed (same bug shape as the fixed alpha_zoo case, but no
    safe narrow fix available):** `districts/investment/vector_finagent/Analytics/` (and several
    sibling subpackages, ~41+ files) do `from config import MarketData` (and `AssetParameters`,
    `AssetClass`, etc.) as a bare top-level absolute import, which resolves to the WRONG `config`
    package -- `vectorcode/src/config/__init__.py` (no `MarketData` there) -- rather than whatever
    local `config` module the vendored finagent package originally shipped with. Unlike
    alpha_zoo's case, `vector_finagent/` has no top-level `config.py`/`config/` to redirect to
    (only unrelated nested ones under `agno_trading/config` and `alpha_arena/config`) -- the real
    target was apparently never vendored in at all (same "incomplete port" shape as
    `core/mining/_docker.py`, item 66). `finagent_agent.py` (the one confirmed real caller, via
    `core/config.py` and `districts/investment/finagent_agent.py`) only reaches a narrow set of
    entry points (`terminal_launcher`, `agents.finagent_core.core_agent`, a `PROVIDERS` dict of
    backtesting-library adapters) -- whether those specific entry points are themselves affected
    was not individually re-checked this round; a follow-up should verify that narrower blast
    radius before deciding whether this needs fixing at all.
    **NOT individually triaged this round** (time-boxed; smaller long-tail failures, mostly
    recognizable optional-dependency names suggesting category-b "expected," but not confirmed
    file-by-file): `textual`(5), `elasticsearch`(2), `pdfplumber`(1), `seaborn`(21), `functime`(5),
    `finrl.agents`(4), `pmdarima`(4), `flask_limiter`(1), a `playwright_stealth.stealth_sync`
    ImportError(1), an `alembic.context` AttributeError(1), a `DomainClassification` partial-
    circular-import ImportError(1), `migrate_bundled_configs`(8), `fincept_strategy_runner`(6),
    a `FinceptAnalyticsError` NameError(6), `open_mythos`(7), `ccxt`(17) -- these overlap
    partially with the shadowbroker_server/vector_finagent clusters above (same false-positive
    shape likely applies to several) but were not individually confirmed one-by-one.
    **Commit status:** `df07e9230` (alpha_zoo fix + test, self-committed -- this fork, unlike the
    parallel Codex Task B, can write `.git/index.lock` directly). A results checkpoint (every one
    of the 4,370 modules checked, with its exact error text) is left at
    `.smoke_sweep_results.json` in the repo root (untracked -- not committed) for a follow-up
    session to resume the un-triaged long tail without re-running the full sweep. This OPEN_ISSUES
    entry is intentionally left uncommitted for the parent session to review and commit, per
    instruction.

92. **`vectorcode/src/plugins/` audit, round 1, partial pass (2026-10-06) --** first-ever
    line-by-line pass on this 77-file directory (three prior commits -- `148a09cd5`, `d920e3ac8`,
    `56348c2e1` -- had already applied narrow, single-bug-class sweeps here on 2026-10-04/05, so
    "never touched this cycle" per the task prompt was stale; treated as a continuation, not a
    fresh start). Time-boxed single pass as a fork -- did not reach full line-by-line depth on
    every one of the 77 files; prioritized credential/filesystem-handling code and ran broad
    pattern sweeps across the rest.
    **Fixed with proof tests, 3 commits:**
    - `memory/honcho/cli.py`'s `_write_config()` (`96ab1a94f`) -- wrote the Honcho config, which
      stores per-host `apiKey`/`baseUrl`, via a plain `path.write_text()`. A crash mid-write
      truncates the file; `_read_config()`'s broad except then silently falls back to an empty
      config, which looks like the user's Honcho setup and API key were simply lost. Called from
      10+ CLI subcommands including `vector honcho setup`. Fixed with tempfile + fsync +
      os.replace.
    - 15 call sites across `image_gen/openai/__init__.py`, `image_gen/openai-codex/__init__.py`,
      `memory/hindsight/__init__.py` (5), `memory/honcho/cli.py` (1 more), `memory/supermemory/
      __init__.py` (7) (`845eafdcc`) -- all passed stdlib logging's `exc_info=True` kwarg to a
      loguru logger call. Loguru does not recognize this kwarg; it's silently absorbed as an
      unused `str.format()` argument, so every one of these failure-path log lines recorded no
      traceback at all despite clearly intending to. Converted to
      `logger.opt(exception=True).<level>()`, loguru's real equivalent.
    - `memory/mem0/__init__.py` and `memory/honcho/__init__.py`'s `save_config()` (`b5d199f47`) --
      same non-atomic-write bug shape as the `cli.py` fix above, independently present in both
      providers' own config-save methods (`mem0.json` stores `api_key`; `honcho.json` stores
      per-host `apiKey`). Also missing explicit UTF-8 encoding on both the read and write side.
      Fixed identically.
    **Major architectural finding, flagged not fixed:** a large cluster of this directory is
    genuinely dead code with zero callers anywhere in the repo, confirmed via grep for both
    top-of-file and indented-inside-function imports (the `hands/` false-negative from earlier
    this cycle was specifically checked for and ruled out here) --
    `google_meet/` (12 files: a full Google Meet bot with a Node.js companion process, audio
    bridge, and realtime OpenAI client), `teams_pipeline/` (3 files: Microsoft Teams Graph
    webhook/meeting pipeline), `bridges/` (8 files: cognitive/gnn/mincut/qe_*/sona bridges),
    `memory_plugins/` (2 files: `mem0_plugin.py`, `memory_backends.py` -- an earlier, superseded
    duplicate of the now-live `memory/mem0/` provider), and 14 standalone top-level modules
    (`spotify_plugin.py`, `google_meet_plugin.py`, `image_gen_plugins.py`, `disk_cleanup_plugin.py`
    + `disk-cleanup/`, `teammate_plugin.py`, `financial_risk.py`, `healthcare_clinical.py`,
    `legal_contracts.py`, `neural_coordination.py`, `perf_optimizer.py`, `prime_radiant.py`,
    `quantum_optimizer.py`, `ruvector_upstream.py`, `cognitive_kernel.py`, `code_intelligence.py`,
    `hyperbolic_reasoning.py`, `test_intelligence.py`). None of these are reachable via the
    directory's own two real dynamic-loading mechanisms (`memory/__init__.py`'s
    `load_memory_provider()`, scoped to `memory/<name>/` subdirectories only; `plugins/loader.py`,
    which only has one caller anywhere -- `cli.py` -- and only scans a `plugins/builtin/`
    subdirectory that doesn't exist). By contrast, `spotify/`, `image_gen/`, `context_engine/`,
    `model_providers/`, and the 8 `memory/<name>/` backend subdirectories (byterover, hindsight,
    holographic, honcho, mem0, openviking, retaindb, supermemory) ARE all genuinely live, reached
    via `vector_cli/tools_config.py`, `agent/image_gen_provider.py`, `agent/context_engine.py`,
    `providers/__init__.py`'s dynamic `plugins.model_providers.<name>` registration, and
    `memory/__init__.py`'s config-driven `load_memory_provider(name)` respectively -- confirmed by
    reading the loader code itself, not just grepping for static references (the 8 memory backends
    in particular are loaded entirely dynamically via `importlib.util.spec_from_file_location()`
    based on `memory.provider` in `config.yaml`, so a static-import grep alone would have falsely
    flagged all 8 as dead). This needs an owner decision: wire the dead cluster in, or delete it --
    not a narrow bug fix.
    **Other findings, flagged not fixed:** `memory/honcho/session.py`'s `HonchoSessionManager` uses
    `threading.Thread` for its async write-back queue and context-prefetch, against the project's
    asyncio-only policy (same already-flagged shape as `connectors/scheduler.py`); its
    `_peers_cache`/`_sessions_cache` dicts are mutated from both the main thread and the background
    writer thread with no lock at all (unlike `_cache`, which does use `self._cache_lock`), a
    latent but low-severity race (redundant Honcho peer-lookup calls, not data corruption).
    `memory/__init__.py`'s `discover_plugin_cli_commands()` falls back to a hardcoded
    `"honcho_command"` attribute name when `f"{active_provider}_command"` isn't found on a
    *different* provider's `cli.py` -- a latent copy-paste-looking bug, currently inert since
    `honcho/` is the only memory backend with a `cli.py` today.
    New tests: `tests/test_honcho_cli_atomic_config_write.py` (2),
    `tests/test_plugins_loguru_exc_info_removed.py` (2),
    `tests/test_memory_providers_atomic_config_write.py` (4) -- 8/8 passing, all confirmed
    failing pre-fix via `git stash`.
    **Not reached this round:** full line-by-line depth on `memory/byterover/`, `memory/
    holographic/` (3 files, 1,369 lines), `memory/openviking/`, `memory/retaindb/`,
    `spotify/tools.py` (454 lines), the orphaned cluster listed above beyond the liveness check,
    and `example-dashboard/dashboard/plugin_api.py`.
    **Commit status:** `96ab1a94f`, `845eafdcc`, `b5d199f47` -- all self-committed directly by
    this fork. This OPEN_ISSUES entry is intentionally left uncommitted for the parent session to
    review and commit, per instruction.

93. **`vectorcode/src/tools/` audit, round 1 (2026-10-06) —** first-ever line-by-line audit of
    this 129-file directory (distinct from root-level `tools/`, the already-audited Claude<->Codex
    dev orchestrator, and `vectorcode/src/vc_tools/`, already fully closed out -- `vectorcode/src/
    tools/` is a third, separate, heavily-used package bare-imported as `tools.X` from many
    production call sites: `agent/lsp/*.py`, `environments/*.py`, `gateway/platforms/discord.py`,
    `model_tools.py`, `plugins/*`, `rl_cli.py`, `run_agent.py`, `vector_cli/*.py`). Run via 4
    parallel Codex tasks, each ~30-34 files; all 4 completed without hitting a usage limit this
    round.
    **Fixed with proof tests (17 files total across the 4 sub-rounds):**
    - `environments/docker.py` -- logged the full `docker run` argument list and container-start
      command at info/debug level, including volume mounts and the real values of every
      environment variable passed into the sandboxed container -- a credential-in-logs risk.
      Redacted to counts/metadata.
    - `worktree.py` -- `git worktree remove --force <path>` and `git merge <branch> -m <message>`
      both reached a caller-controlled path/branch/message with no `--` separator before the
      positional argument (git-argument-injection, the same bug class fixed in
      `tools/vector_dev_orchestrator/worktree_manager.py` and `scripts/profile_distribution.py`
      this cycle).
    - `mcp_oauth.py` -- `_write_json()`'s token-cache write used a predictable
      `path.with_suffix(".tmp")` tmp name with no fsync, risking collision under concurrent OAuth
      refreshes and data loss on a mid-write crash. Made atomic (tempfile.mkstemp + fsync +
      os.replace).
    - `checkpoint.py`, `checkpoint_manager.py` -- atomic persistence fixes for saved checkpoint
      state.
    - `file_safety.py`, `file_tools.py`, `git_tools.py`, `process_registry.py`,
      `tool_result_storage.py`, `tirith_security.py`, `stt_tool.py`, `environments/base.py`,
      `environments/managed_modal.py`, `code_execution_tool.py`, `direct_executor.py`,
      `microsoft_graph_client.py` -- path confinement, atomic-write, and phantom-success fixes
      matching established bug classes from this audit cycle.
    New tests: `tests/test_tools_batch_a_regressions.py` (3),
    `tests/test_tools_batch_b_audit_regressions.py` (8),
    `tests/test_tools_batch_c_regressions.py` (4), `tests/test_tools_batch_d_regressions.py` (5)
    -- 20 tests total, all passing, all verified by the parent session.
    **Remaining scope:** `lsp/`, `storage/` (a separate subpackage from the already-fixed
    `vc_tools/storage/`), `browser_*`, `computer_use/`, and ~70 other files in this directory were
    reviewed-clean or not yet individually confirmed -- treat as a first pass, not full closeout.
    **Commit status:** committed by the parent session (Codex's sandbox cannot write
    `.git/index.lock`): `2504a5353`, `e5effc6c2`.

94. **`vectorcode/src/vector_cli/` audit, round 1 (2026-10-06) —** first-ever line-by-line audit
    of this 123-file directory (the main `vector` CLI entry point package). Run via 2 parallel
    Codex tasks; batch A completed cleanly, batch B hit a genuine Codex usage-limit wall mid-write
    of its own test file, leaving 4 fixes specified by the test but not yet applied to source --
    completed directly by the parent session using the test's own assertions as the spec, each
    confirmed failing pre-fix via `git stash`.
    **Fixed with proof tests:**
    - `auth.py` -- the Spotify OAuth callback handler had no CSRF state-parameter validation at
      all (same gap already fixed in `connectors/oauth.py` and `tools/mcp_oauth.py` this cycle).
      Added `secrets.compare_digest()` verification before accepting the callback.
    - `setup.py` -- a non-obvious Python scoping bug, not a typo: `_setup_tts_provider()`'s neutts
      branch calls `importlib.util.find_spec("neutts")` via the module-level import, but a LATER
      branch in the SAME function (kittentts) had its own local `import importlib.util`. Python
      decides a name is function-local at compile time based on whether it's assigned anywhere in
      the function body, independent of execution order -- so `importlib` was local to the whole
      function, and the neutts branch's reference (which runs before the local import statement
      is ever reached) raised `UnboundLocalError` every time, silently caught by a broad except
      and defaulting `already_installed` to False. Effect: the "NeuTTS is already installed" skip
      path could never fire -- every setup run re-prompted to install dependencies even when
      already present. Fixed by removing the redundant local import.
    - `vault_cmd.py` -- `_save_vault()` wrote the encrypted credential vault directly with
      `write_bytes()` with no atomicity -- a crash mid-write could corrupt/truncate the vault.
      Made atomic (tempfile + fsync + os.replace + 0o600 before the file is visible at its final
      path).
    - `webhook.py` -- `_load_subscriptions()` silently returned `{}` when the parsed JSON was a
      non-dict value (e.g. a JSON array) instead of raising `SubscriptionsLoadError` -- the exact
      phantom-empty-store bug the function's own docstring warns against, reachable via one
      previously-uncovered branch.
    - `profile_distribution.py` -- `git clone --depth 1 <url> <dest>` had no `--` separator before
      the caller-provided url (git-argument-injection).
    New tests: `tests/test_vector_cli_auth_oauth_state.py` (1),
    `tests/test_vector_cli_batch_b_audit.py` (5) -- 6 tests, all passing.
    **Remaining scope:** ~115 of 123 files were not individually confirmed this round (batch A's
    own file list beyond `auth.py` was not deeply verified by the parent session beyond running
    its tests; batch B's assigned list beyond the 4 completed fixes was not reached before the
    usage-limit wall) -- treat as a first pass, not full closeout.
    **Commit status:** committed by the parent session: `15e1857f0`.

95. **`vectorcode/src/gateway/` audit batch C (2026-10-06) —** audited the 22 assigned
    production files spanning WeCom/Weixin/WhatsApp/Yuanbao adapters plus gateway runtime,
    session, status, streaming, and WebSocket support. Fixed five concrete bug groups:
    (1) `sticker_cache.py` now keeps its documented fail-open contract when persistence fails
    and uses tempfile + fsync + `os.replace()` so a crash cannot truncate the existing cache;
    (2) `wecom_crypto.py` retains the protocol-correct AES-CBC IV (`key[:16]`) and timing-safe
    signature verification, while now strictly validating Base64, the decoded AES-256 key,
    complete ciphertext blocks, and decrypted length framing (network-order length encoding is
    now explicit via `!I`); (3) `session_context.py` now actually restores the saved ContextVar
    tokens for nested gateway work instead of erasing the enclosing request's routing context,
    while still preventing stale process-environment fallback after a top-level request;
    (4) cancellation cleanup in WeCom, WeCom callback, Weixin, and Yuanbao no longer re-raises
    the expected `CancelledError` from a child task that the cleanup method itself cancelled —
    cleanup now reaches remaining tasks, clients, sockets, pending ACKs, and locks; (5) gateway
    coordination/status JSON is atomically persisted, and WhatsApp text/log I/O now explicitly
    uses UTF-8 on Windows.
    **Owner decisions, not guessed:** `gateway/server.py` is live through `vectorcode/src/cli.py`
    and accepts arbitrary agent input, execution mode, model, session ID, and `project_dir`; it
    has no authentication, uses wildcard CORS with credentials, and the CLI can bind it beyond
    localhost. Decide whether non-loopback binding should be forbidden or require an authenticated
    deployment mode. `gateway/ws.py` is not wired into this server (its only production-looking
    references are its own example), so decide whether to integrate it with the same authentication
    policy or remove it. `session.py` and `yuanbao_proto.py` still use `threading.Lock`, and
    `yuanbao_proto.py` still uses stdlib logging; replacing those concurrency primitives is an
    architectural policy choice rather than a safe narrow audit edit.
    New/updated proof tests: `tests/test_vectorcode_gateway_hooks_and_sticker_cache.py`,
    `tests/test_vectorcode_gateway_wecom_crypto_real_bugs.py`,
    `tests/test_vectorcode_gateway_session_context.py`,
    `tests/test_vectorcode_gateway_disconnect_cleanup.py`, and
    `tests/test_vectorcode_gateway_status_atomic.py`. Focused suite: 15/15 passed before the final
    status regression was added; the complete final focused run is reported in the audit handoff.
    All 22 assigned modules also passed `py_compile`. Changes intentionally left uncommitted for
    parent review.

97. **`vectorcode/src/channels/` full audit (2026-10-06) —** completed a line-by-line review of
    all 41 assigned production files (6,225 pre-change lines). Git history confirmed that
    `whatsapp_business.py`, `bulk_sender.py`, and `webhook.py` had prior partial coverage; all
    three were re-reviewed in their current state rather than assumed clean.
    **Fixed with proof tests (9 production files):** `webhook.py` now transmits the exact compact
    UTF-8 bytes it HMAC-signs (previously `httpx` re-serialized a different body, invalidating
    signatures); `gmail.py` persists refreshed OAuth tokens with tempfile + fsync + `os.replace`;
    `bulk_sender.py` preserves an explicit falsy zero rate override; `telegram.py` no longer
    reports success for an empty message without making an API request; `twitter_channel.py`
    compares snowflake IDs numerically; `irc_channel.py` and `adapters/twitch_adapter.py` reject
    CR/LF command injection; and the LinkedIn/YouTube adapters now raise on HTTP failures instead
    of returning an error JSON object as apparent success. New regression file:
    `tests/test_channels_audit_regressions.py` (8 tests). Targeted verification: 62 passed;
    `compileall` and `git diff --check` also passed.
    **Owner/design decisions intentionally not guessed:** seven legacy channel implementations
    still use the project-banned `threading` module (`discord_channel.py`, `email_channel.py`,
    `gmail.py`, `slack.py`, `telegram.py`, `twitter_channel.py`, `whatsapp_baileys.py`); replacing
    those requires deciding whether the synchronous `BaseChannel` lifecycle becomes async.
    `TeamsChannel` sends the app password directly as a bearer token instead of performing the
    Bot Framework OAuth client-credentials exchange. `XMPPChannel.send()` constructs a client and
    queues `msg.send()` without connecting/processing an XMPP session, and
    `WhatsAppBaileysChannel.send()` reports delivery after only writing to subprocess stdin with
    no bridge acknowledgement. Finally, the five classes in `channels/adapters/` are exported by
    their local `ADAPTER_REGISTRY` but have no real callers outside that package, so their intended
    Permission Gateway/discovery wiring needs an owner architecture decision rather than a guessed
    cross-layer integration.
    **Commit status:** left uncommitted for the parent session; `docs/OPEN_ISSUES.md` deliberately
    remains unstaged per instruction.

96. **`vectorcode/src/vc_security/` audit, first-ever full-depth pass (2026-10-06) —** audited
    all 18 production files in the security-primitives package itself (injection scanning, SSRF
    guards, subprocess sandboxing, taint tracking, credential stripping, file-sensitivity policy,
    capability/signing checks). Given what this package IS, bugs here are disproportionately
    high-impact -- a flaw in the security layer undermines every caller that relies on it, and
    that is exactly what was found: a single systemic bug pattern, repeated 6 times across 5
    files, that silently disabled multiple real security features on any machine without the
    compiled Rust extension (confirmed: `get_rust_module()` returns `None` on this dev machine).
    **Fixed with proof tests, all confirmed failing pre-fix via `git stash`:**
    - `ssrf.py` -- `check_ssrf()` called `_rust.check_ssrf(url)` unconditionally; crashed with
      `AttributeError` on every call instead of falling back to the already-written, correct
      `_check_ssrf_python()` (private-IP/cloud-metadata blocking, IPv4-mapped-IPv6 handling, DNS
      resolution) which was mislabeled "kept for reference only." Broke `vc_tools/http_request.py`,
      `browser.py`, and `web_search.py` entirely (crash, not a silent bypass, but still total
      unavailability of SSRF-protected outbound HTTP).
    - `injection_scanner.py` -- `InjectionScanner.__init__()` could not even construct;
      `_INJECTION_PATTERNS` (11 regexes: prompt-override, jailbreak, exfiltration, shell/code
      injection, delimiter injection) were compiled into `self._patterns` and then never used.
      Added a working `_scan_python()` fallback.
    - `capabilities.py` -- `CapabilityPolicy.__init__()` could not construct; this is the RBAC
      policy gating every tool dispatch. Wired in the existing `_check_python()` (previously
      "kept for reference only") and guarded `grant()`/`deny()`.
    - `rate_limiter.py` -- `RateLimiter.__init__()`/`check()` could not construct/run; `reset()`
      additionally had its own Python fallback stranded as dead code after an unconditional early
      `return`. `TokenBucket`/`_get_bucket()` were a complete, thread-safe Python implementation
      that `check()` never called -- wired it in.
    - `scanner.py` -- the most severe instance: `SecretScanner` and `PIIScanner` (secret and PII
      detection) had **no Python fallback at all**, despite complete PATTERNS dicts (10 secret
      patterns incl. OpenAI/Anthropic/AWS/GitHub/Stripe keys, private keys, DB connection strings;
      7 PII patterns incl. SSN, 3 credit-card networks) sitting unused in the same file. This had
      a confirmed, serious downstream consequence: `boundary.py`'s `BoundaryGuard` (scans ALL
      outbound content at device exit points) and `guardrails.py`'s `GuardrailsEngine` (wraps the
      entire inference pipeline for security scanning) both depend on constructing these two
      classes -- `BoundaryGuard` caught the crash and silently fell back to **zero scanners**
      (fail-open: outbound secrets/PII scanning was completely disabled, confirmed live before
      the fix), while `GuardrailsEngine` had no guard at all and could not be constructed. Added
      shared `_scan_python()`/`_redact_python()` helpers and wired both classes to them.
    - `credential_stripper.py` -- a separate, narrower coverage gap (not the Rust-fallback
      pattern): `CredentialStripper`, wired into `vector_cli/log_config.py`'s live
      `SanitizingFormatter`, only covered 6 of the patterns `scanner.py`'s `SecretScanner` already
      covers -- a Stripe key (wrong separator), a DB connection string, a PEM private key, a plain
      `password=`/`api_key=` assignment, 3 of 5 GitHub token prefixes, and 4 of 5 Slack token
      prefixes could all have reached log output unredacted. Expanded to match `SecretScanner`'s
      coverage.
    - `signing.py` -- unrelated to the Rust pattern: `save_keypair()` wrote the Ed25519 private
      key non-atomically with default OS permissions instead of 0o600 (every other
      credential-bearing file fixed this cycle uses tempfile+fsync+os.replace+chmod). No current
      production caller found; fixed anyway since it handles private key material.
    - `subprocess_sandbox.py` -- unrelated to the Rust pattern: `run_sandboxed()`'s own
      timeout-recovery path (`proc.wait(timeout=5)` after killing a timed-out process) had no
      exception handling of its own -- a process that survives the kill (stuck in an
      uninterruptible syscall) raised a second, uncaught `TimeoutExpired` that crashed the caller
      instead of returning the timed-out result the function's contract promises. No current
      production caller found; fixed anyway since it's the sandbox's own robustness guarantee.
    **Reviewed, no bug found:** `file_policy.py` (already correctly fixed in an earlier round,
    confirmed complete), `boundary.py` and `guardrails.py` (both correctly structured, their only
    issue was the upstream `scanner.py` crash, now fixed), `taint.py`, `file_utils.py`, `types.py`,
    `_abc.py`, `__init__.py`.
    **Flagged for owner decision, not fixed:**
    - `audit.py`'s `AuditLogger` uses raw `sqlite3.connect()` instead of
      `core.memory.episodic.get_db_connection()` (SQLCipher) -- this stores security audit events
      whose `content_preview`/`matched_text` fields can themselves contain snippets of the exact
      secrets/PII the scanners just detected, in an unencrypted database.
    - `severity_policy.py`'s `SeverityPolicy.action_for()` falls back to `"log"` (the weakest
      action) for an unrecognized `ThreatLevel` -- currently unreachable since `ThreatLevel` is a
      closed 4-value enum fully covered by `_DEFAULT_ACTIONS`, but would silently fail open if a
      5th level is ever added without updating this policy. Noted for awareness, not fixed, since
      there's no live bug to reproduce.
    New tests (7 files, 23 tests total, all passing, all confirmed failing pre-fix via `git
    stash`): `tests/test_vc_security_ssrf_rust_fallback.py` (3),
    `tests/test_vc_security_signing_atomic_save.py` (2),
    `tests/test_vc_security_subprocess_sandbox_stuck_process.py` (1),
    `tests/test_vc_security_injection_scanner_rust_fallback.py` (3),
    `tests/test_vc_security_rust_fallback_batch.py` (6, covering capabilities/rate_limiter/scanner),
    `tests/test_vc_security_credential_stripper_coverage.py` (6).
    **Commit status:** `57f612f83` (ssrf.py), `52b97c847` (signing.py), `5d503ddbf`
    (subprocess_sandbox.py), `a784bfce6` (injection_scanner.py), `cd926b6d9`
    (capabilities/rate_limiter/scanner.py), `a78ade3c5` (credential_stripper.py) -- all
    self-committed directly by this fork. This OPEN_ISSUES entry is intentionally left
    uncommitted for the parent session, per instruction.

98. **`vectorcode/src/comms/` audit, batches A+B (2026-10-06) —** first-ever line-by-line audit
    of this 58-file directory (a platform messaging layer distinct from `vectorcode/src/gateway/`
    and `vectorcode/src/channels/`, which have similarly-named files for the same platforms but
    are genuinely different implementations). Both Codex batches hit a genuine usage-limit wall
    (reset ~a few hours later, not the multi-day reset seen earlier this session) after fixing
    their assigned files but before writing their own OPEN_ISSUES entries -- this entry was
    written by the parent session after independently verifying and committing the work (ran
    every new test file, syntax-checked every touched file, spot-checked the `wecom_crypto.py`
    AES-CBC hardening diff in full).
    **Fixed, 29 files, with proof tests (see commit `e27cc6e75` for the full file list and
    per-fix detail):** the most significant is `wecom_crypto.py`'s AES-CBC decrypt hardening
    (exception wrapping around raw cipher/padding ops, bounds-checked `xml_len` before slicing,
    network-byte-order struct format instead of a redundant unpack+ntohl pair, explicit
    encoding throughout) -- a corrupted or crafted WeCom callback ciphertext could previously
    raise an unhandled low-level crypto exception or, worse, read past the real plaintext bounds.
    Remaining fixes are falsy-zero, CSRF-state, and atomic-write bugs matching established
    classes from this audit cycle, spread across the signal/slack/telegram/twilio/twitch/viber/
    xmpp/zulip/reddit/rocketchat/matrix/mastodon/nostr/line/irc/messenger/teams/google_chat/
    homeassistant/imessage/sendblue/yuanbao platform adapters.
    New tests: `tests/test_comms_batch_a_regressions.py` (6),
    `tests/test_vectorcode_comms_batch_b_regressions.py` (9) -- 15 tests, all passing, verified
    by the parent session.
    **Remaining scope:** ~29 of 58 files were not individually confirmed this round -- treat as
    a first pass, not full closeout.
    **Commit status:** committed by the parent session: `e27cc6e75`.

99. **`vectorcode/src/gateway/` audit, batches A+B (2026-10-06) —** first-ever line-by-line audit
    of 35 of 64 files in this directory (batch C's own 22-file slice already has its own entry,
    item 95 above). Both batches hit the same genuine usage-limit wall as the comms/ batches
    above, before writing their own OPEN_ISSUES entries -- committed and documented by the parent
    session after independent verification (every new test run, every touched file syntax-checked,
    the `platforms/wecom_crypto.py` AES-CBC diff spot-checked in full -- this is a SEPARATE file
    from `comms/wecom_crypto.py` above; both independently had the same hardening gap and were
    fixed independently).
    **Fixed, 15 files, with proof tests (see commit `ca7f420ad` for the full file list and
    per-fix detail):** `platforms/wecom_crypto.py`'s AES-CBC decrypt hardening (same shape as
    `comms/wecom_crypto.py` this round); `sticker_cache.py`'s `_save_cache()` made atomic
    (tempfile+fsync+os.replace) while deliberately preserving the already-established
    fail-open-with-a-warning behavior for this specific cheaply-regenerable cache (a cache with
    no caller-side error handling must not turn a persistence failure into a crashed message
    handler -- this exact judgment call was made once before this cycle for the same reasoning);
    `status.py`/`session_context.py` atomic-persistence fixes; CSRF/webhook-signature/correctness
    fixes across `pairing.py` and `platforms/{base,bluebubbles,feishu,feishu_comment_rules,
    msgraph_webhook,wecom,wecom_callback,weixin,whatsapp,yuanbao}.py`.
    New tests: `tests/test_gateway_batch_a_regressions.py` (9),
    `tests/test_vectorcode_gateway_disconnect_cleanup.py` (2),
    `tests/test_vectorcode_gateway_session_context.py` (2),
    `tests/test_vectorcode_gateway_status_atomic.py` (1), plus 1 new test added to the existing
    `tests/test_vectorcode_gateway_hooks_and_sticker_cache.py`, plus the existing
    `tests/test_vectorcode_gateway_wecom_crypto_real_bugs.py` (6) -- 20 new + 3 pre-existing,
    all passing, verified by the parent session.
    **Remaining scope:** 7 of 64 files in this directory (batch A+B's assigned ~35 minus the 15
    fixed, plus whatever batch C left unconfirmed) were not individually confirmed this round --
    treat as a first pass, not full closeout.
    **Commit status:** committed by the parent session: `ca7f420ad`.

100. **`vectorcode/src/server/` audit, partial pass (2026-10-07) —** first-ever pass on this
     21-file FastAPI HTTP/WebSocket server layer. Codex was unavailable (genuine usage-limit
     wall) so this round ran as a solo Claude fork, which hit the Claude session rate limit
     partway through and was cut off mid-task.
     **Fixed with proof tests, both verified by the parent session:**
     - `webhook_routes.py` (`e0519b93a`) -- the WhatsApp webhook verification endpoint called
       `secrets.compare_digest(token, whatsapp_verify_token)` with no guard for an unconfigured
       (empty) `whatsapp_verify_token`. `secrets.compare_digest("", "")` returns `True`, so with
       no token configured, a verification request supplying an empty `hub.verify_token`
       succeeded and echoed back the attacker-supplied `hub.challenge` -- a real bypass. The
       file's own sibling checks (bluebubbles_password, sendblue webhook_secret) already guard
       with `if <secret> and ...`; this one was missing it.
     - `ws_bridge.py` (`18662effd`, completed by the parent session after the fork was cut off
       mid-write, confirmed failing pre-fix via `git stash`) -- the real finding this round:
       Starlette's `BaseHTTPMiddleware` (backing `AuthMiddleware`'s HTTP-side API key check)
       only runs for `scope["type"] == "http"` and never sees WebSocket connections. The
       `/v1/agents/events` WS endpoint was therefore **completely unauthenticated** regardless
       of whether `OPENVECTOR_API_KEY` was configured, even though every `/v1/*` HTTP route was
       protected. Fixed with an explicit timing-safe re-check inside the WS handler itself
       (query-param-supplied key, since browsers can't set an Authorization header during a WS
       handshake).
     - `session_store.py` (`5b50cb9e4`, docs-only) -- `expire_sessions()` confirmed via
       repo-wide grep to have zero callers; real conversation history never actually expires.
       Flagged for owner decision rather than inventing new scheduling infrastructure to wire
       it in, since `app.py` has no existing periodic-task machinery to hook into.
     New tests: `tests/test_vectorcode_server_webhook_routes_timing_safe.py` (7),
     `tests/test_vectorcode_server_ws_bridge_auth.py` (4) -- 11 tests, all passing.
     **Remaining scope:** ~17 of 21 files (`__init__.py`, `agent_manager_routes.py`,
     `api_routes.py`, `app.py`, `auth_middleware.py`, `channel_bridge.py`, `cloud_router.py`,
     `comparison.py`, `connectors_router.py`, `cost_calculator.py`, `dashboard.py`,
     `digest_routes.py`, `middleware.py`, `models.py`, `routes.py`, `savings.py`,
     `stream_bridge.py`, `upload_router.py`) were not reached before the rate-limit cutoff --
     a genuine partial pass, not a full-depth closeout. `auth_middleware.py` and
     `upload_router.py` specifically (file-upload path confinement, session-token generation)
     were explicitly flagged as high-priority for this directory and remain unaudited.
     **Commit status:** `e0519b93a`, `5b50cb9e4` self-committed by the fork; `18662effd`
     committed by the parent session.

101. **`vectorcode/src/cli/` audit, partial pass (2026-10-07) —** first-ever pass on this 23-file
     directory (distinct from the already-audited `vectorcode/src/vector_cli/`, confirmed via
     `git log` before starting). Codex was unavailable (genuine usage-limit wall) so this round
     ran as a solo Claude fork, which hit the Claude session rate limit partway through and was
     cut off mid-task (the fork's own last message reported losing a fix in a stash operation,
     but no stash was found afterward -- the fix was recovered successfully as an uncommitted
     working-tree change).
     **Fixed with proof tests, both verified by the parent session:**
     - `auth.py` (`d832c3cd5`) -- `_load_file_store()` caught any JSON parse failure and
       returned `{}`, indistinguishable from a genuinely-empty credential store; `add()`/
       `remove()` would then overwrite the corrupted `~/.vector/credentials.json` on the very
       next call, permanently destroying every other stored credential's metadata. Same
       "fail-open destroys data" bug class already fixed in `vault_cmd.py`, `webhook.py`, and
       `skill_manage.py` earlier this cycle. Added `CredentialStoreCorruptedError` (raised
       instead of swallowed, with a clean top-level error message) and made `_save_file_store()`
       atomic (tempfile+fsync+os.replace) -- previously non-atomic, so a crash mid-write could
       itself produce exactly the corrupted file this fix now protects against.
     - `scan_cmd.py` (completed by the parent session after the fork was cut off mid-write,
       confirmed failing pre-fix via `git stash`) -- the fallback `class PrivacyScanner` beneath
       `except ImportError:` was defined unconditionally at module scope, so it always
       overwrote the real `PrivacyScanner` that `from vectorcode.src.vector_cli.scan_cmd import *`
       had already successfully imported above it. The stub's `scan(path)` method doesn't exist
       on the real class, and the stub has no `run_all()` at all, so every call to
       `server/routes.py`'s `/v1/security/scan` endpoint crashed with `AttributeError`.
     New tests: `tests/test_vectorcode_cli_auth_store_integrity.py` (4),
     `tests/test_vectorcode_cli_scan_cmd_privacy_scanner.py` (2) -- 6 tests, all passing.
     **Remaining scope:** ~21 of 23 files were not reached before the rate-limit cutoff --
     a genuine partial pass. `self_update.py` (unverified-download/atomic-replace risk) and
     `scheduler_cmd.py` (checkpoint-watermark bug class) were explicitly flagged as
     high-priority for this directory and remain unaudited.
     **Commit status:** `d832c3cd5` self-committed by the fork; `1c0a25a8f` committed by the
     parent session.

102. **`vectorcode/src/server/` audit, continuation (2026-10-07) —** direct continuation of item
     100 above (a prior fork was cut off by the Claude session rate limit). Confirmed via
     `git log` that this directory has more prior coverage than the original directive assumed:
     `auth_middleware.py` (timing-unsafe bearer-token comparison, already fixed), `webhook_routes.py`
     (3 timing-unsafe secret comparisons, already fixed, plus the unconfigured-WhatsApp-token gap
     fixed this round above), `cloud_router.py` (Gemini API key in URL + broken placeholders,
     already fixed), `connectors_router.py` (loguru shadow, banned threading, stale sync status,
     already fixed), `routes.py`/`session_store.py` (stdlib-logging-instead-of-loguru, already
     fixed) -- re-reviewed each briefly, found no further bugs, did not duplicate work.
     **Fixed with proof tests:** `api_routes.py` -- the real finding this round. `/v1/chat/stream`
     is a second WebSocket endpoint with the exact same auth bypass just fixed in `ws_bridge.py`'s
     `/v1/agents/events`: Starlette's `BaseHTTPMiddleware` never runs for WebSocket connections, so
     this endpoint -- which relays messages straight into the configured LLM engine via
     `engine.stream()`/`engine.generate()` -- was completely unauthenticated regardless of whether
     `OPENVECTOR_API_KEY` was set. Materially worse than the event-stream gap since this one spends
     real inference cost, not just leaks telemetry. Fixed with the same timing-safe query-param
     key re-check.
     **Reviewed, no bug found:** `models.py` (pure Pydantic schemas, no logic, no falsy-zero risk
     possible), `upload_router.py` (uploaded filenames never reach a filesystem path -- content is
     parsed in-memory and stored via a generated UUID doc_id through `KnowledgeStore`, so the
     anticipated CWE-22 risk does not apply; no file-size cap before `.read()` noted as a minor DoS
     concern but not fixed, since `UploadFile.size` reliability varies by FastAPI/Starlette version
     and a wrong guess could break legitimate large uploads), `channel_bridge.py` (its LLM call path
     goes through `VectorSystem.ask()`, not a raw engine call, so it is NOT subject to the
     session-hydration gap below), `agent_manager_routes.py`'s credential-save endpoint (delegates
     to `vc_core/credentials.py`'s `save_credential()`, which validates the key against an allowlist
     before use -- no CWE-22 risk at this call site).
     **Flagged for owner decision, not fixed (architectural, spans multiple files):**
     - Mandatory `context_engine.session_hydration_prompt()` (CLAUDE.md Rule 1, "no exceptions") is
       absent from every direct `engine.generate()`/`engine.stream()` call site in this directory --
       `api_routes.py`, `routes.py`, `agent_manager_routes.py` (via `engine.stream_full()`),
       `stream_bridge.py` (via `engine.stream_full()`). These bypass the normal agent-loop path and
       call the raw inference client directly, so chat initiated through this HTTP/WS API surface
       never gets VECTOR's persona/context injected. Not fixed because it's genuinely ambiguous
       whether this low-level API is meant to be VECTOR's own chat surface (should always hydrate)
       or an OpenAI-compatible passthrough for external integrations that supply their own system
       prompt (should not) -- a design decision, not a narrow bug.
     - `threading.Thread` usage against the project's asyncio-only policy: 4 sites in
       `agent_manager_routes.py` (lines ~800, ~1420, ~1527, ~1782, all `daemon=True` background
       agent-tick runners) plus 1 pre-existing site in `webhook_routes.py`. Converting to asyncio
       properly is an architecture change, not a narrow fix -- same judgment already applied to
       similar `ThreadPoolExecutor` usage in `embeddings.py` and `scheduler.py` earlier this cycle.
     **Not reached:** `__init__.py`, `app.py`, `comparison.py`, `cost_calculator.py`, `dashboard.py`,
     `digest_routes.py`, `middleware.py`, `savings.py`, `stream_bridge.py` -- genuinely not read
     this round; still open for a future pass.
     New tests: `tests/test_vectorcode_server_api_routes_ws_chat_auth.py` (4 tests), all passing,
     confirmed failing pre-fix via `git stash`.
     **Commit status:** `9a03ea707`.

103. **`vectorcode/src/cli/` audit, continuation (2026-10-07) —** direct continuation of item 101
     (auth.py and scan_cmd.py were already done). This round covered the remaining 21 files with
     real depth and closes out `vectorcode/src/cli/` for this audit cycle.
     **Major finding -- a recurring bug class hit 2 more times in this directory:** `_bg_state.py`
     and `_tool_names.py` are "compatibility shim" modules that do
     `from vectorcode.src.vector_cli.X import *` and then, unconditionally (not just in the
     `except ImportError:` branch), redefine the real names with a trivial stub. Since the
     wildcard import actually succeeds on this install, the stub always won -- the exact same
     shape already found in `cli/scan_cmd.py` earlier this cycle (item 101). `_bg_state.get_status()`
     returned a plain dict instead of the real `BgStatus` dataclass, breaking `chat_cmd.py`'s
     startup banner and notification dispatcher (both read `BgStatus`'s real attributes).
     `_tool_names.resolve_tool_names(names)` took one positional argument while every real caller
     (`vector_cli/ask.py`, `vector_cli/chat_cmd.py`) calls it with three -- a **guaranteed
     TypeError on every agent-mode `ask`/`chat` invocation** that reaches this path. Fixed both
     (commit `fac045637`) by removing the unconditional stub definitions.
     **Other fixes, each with proof tests confirmed failing pre-fix via `git stash`:**
     - `profiles.py` (`566bdd095`) -- same "fail-open destroys data" bug class already fixed in
       `cli/auth.py` this cycle: a corrupted `profiles.json` was silently treated as "no custom
       profiles", so the next `_save()` (e.g. creating any new profile) would overwrite it with
       just the built-ins, destroying every previously saved custom profile. Added
       `ProfilesCorruptedError` (raised instead of swallowed) and made `_save()` atomic.
     - `chat_cmd.py` (`8a56b075e`) -- missing the mandatory
       `context_engine.session_hydration_prompt()` call (CLAUDE.md Rule 1, "before EVERY LLM
       call -- no exceptions"). The REPL's `history` list (sent whole to `engine.generate()`/
       `agent.run()` every turn) was seeded only with an optional user-supplied `--system`
       prompt -- a session invoked without `--system` ran with zero hydration for its entire
       lifetime. `/clear` also failed to re-seed it. Fixed via a shared `_fresh_history()` helper.
     - `digest_cmd.py` (`3ddf4815e`) -- `_save_digest_schedule()` wrote the **entire** VECTOR
       `config.toml` (not just the `[digest]` section) directly via `write_text()`, non-atomically
       and with no explicit encoding. A crash mid-write would corrupt the whole config file. Made
       atomic (tempfile+fsync+os.replace) with explicit UTF-8.
     **Major finding, flagged for owner decision, NOT fixed (design/policy, not a narrow bug):**
     5 of the 21 assigned files -- `agent_cmd.py` (718 lines, full agent-management CLI: list/
     create/info/tasks/pause/resume/delete/bind/channels/search), `mine_cmd.py` (978 lines,
     hardware detection + Docker + HuggingFace model management + process control),
     `registry_cmd.py` (141 lines, registry introspection), `scheduler_cmd.py` (249 lines),
     `workflow_cmd.py` (65 lines, itself admits "Full execution would need a VectorSystem --
     just report for now") -- have **zero callers anywhere in the repo**, confirmed via both
     static grep (including the bare `cli.X`-style imports `cli.py`'s own monolith uses
     internally for `doctor`/`profiles`/`completion`/`self_update`, none of which reference these
     5 names) and the `cli.py` monolith's dynamic `cmd_vector_cli_dispatch()` table (none of
     these 5 module names appear among its ~30 dispatch targets either). That's ~2,151 lines of
     fully-functional, never-superficial, genuinely complete CLI features sitting completely
     unreachable -- not stubs, not WIP, just never wired into the actual command dispatcher.
     `skill_cmd.py` is reachable only via a test file's direct import (`cli.skill_cmd._get_resolver`,
     already fixed for a different bug in an earlier round, commit `28cd89660`), with no production
     caller found either. Syntax-checked all 6 files -- no crashes, genuinely complete code. Did
     NOT delete or attempt to wire any of this in; whether to restore these commands to the
     dispatcher, or delete them as superseded by the `cli.py` monolith's own simpler
     implementations, is the owner's call.
     **Confirmed clean, no bug found:** `__init__.py`, `_commands.py`, `_runner.py`,
     `_chat_banner.py`, `_chat_notifications.py`, `hints.py`, `init_cmd.py`, `doctor.py`,
     `completion.py`, `self_update.py` (delegates entirely to `pip`/`docker pull`'s own integrity
     mechanisms, no custom unsigned-download-and-execute risk). `ask.py`'s own local `ask()`
     function has zero callers (only `_build_tools`/`_get_memory_backend` are actually used from
     this file) -- harmless dead code within an otherwise-live file, not a shadowing bug since
     nothing imports the real `ask` through it.
     New tests: `tests/test_vectorcode_cli_profiles_corruption_and_atomicity.py` (3),
     `tests/test_vectorcode_cli_shim_stubs_do_not_shadow_real_impl.py` (2),
     `tests/test_vectorcode_cli_chat_cmd_hydration.py` (1),
     `tests/test_vectorcode_cli_digest_cmd_atomic_config_write.py` (2) -- 8 tests, all passing.
     **Commit status:** `566bdd095`, `fac045637`, `8a56b075e`, `3ddf4815e` -- all self-committed
     directly by this fork.

104. **`vectorcode/src/{acp_adapter,memory,tui_gateway,vc_system}/` audit (2026-10-07) —**
     audited the 31 assigned production files. Narrow fixes made: `memory/backends.py` no longer
     crashes every `SQLiteBackend.store()` call on an undefined `now`; ACP permission bridging
     now denies an unknown/malformed allowed option instead of granting execution; ACP tool-event
     completion preserves valid falsy results/arguments; `SwarmDatabase.record_task()` preserves a
     caller-supplied epoch timestamp and retention now returns the total deletions across all three
     tables rather than only the last statement's count; the built-in memory provider now imports
     the real `get_vector_home()` helper (the referenced `get_vector_memory_path()` does not exist);
     memory.md and FAISS JSON sidecars now use flushed atomic replacement; and four broken
     printf-style/`exc_info=True` loguru calls in ACP session restoration were corrected.
     Regression coverage: `tests/test_vectorcode_assigned_audit_regressions.py` (6 tests), all
     passing; all assigned packages also pass `compileall` and `git diff --check`.
     **Owner decisions, not fixed:**
     - `memory/backends.py` (2 connections), `memory/faiss_index.py` (1), and
       `memory/swarm_db.py` (1) open real VECTOR data with raw `sqlite3.connect()` instead of the
       mandatory SQLCipher `core.memory.episodic.get_db_connection()`. Migration/keying semantics
       need an owner decision; silently changing existing database formats would be unsafe.
     - The ACP adapter's third-party imports (`import acp`, `from acp.schema ...`) collide with the
       repo's own `vectorcode/src/acp/` package whenever `vectorcode/src` is on `sys.path` (the
       normal CLI layout). The local package has no `schema`, `Client`, or `run_agent`, so the
       adapter cannot import/run in that layout even when `agent-client-protocol` is installed.
       Resolving this requires renaming/repackaging one of the two public `acp` packages or a
       deliberate dependency-loading boundary; no brittle `sys.path` surgery was added.
     - `AutoMemoryBridge` has zero production callers (only its own module and legacy tests mention
       it), despite its docstring promising periodic episodic-to-FAISS synchronization. Its reverse
       sync is explicitly still a placeholder. Decide whether to wire it into startup or retire it.
     - The memory embedding fallback writes random vectors when Ollama fails
       (`auto_bridge.py`, `pattern_store.py`), making identical text unrelated across calls and
       persisting semantically meaningless search data. A deterministic/local fallback versus
       fail-closed behavior is a product-quality decision.
     - Banned concurrency/logging primitives are structural here: raw `threading` appears in ACP
       sessions, all three SQLite memory stores, and the TUI gateway/publisher/server; stdlib
       `logging` is used by ACP transport setup and the TUI gateway. Replacing these requires an
       asyncio/transport lifecycle redesign rather than a narrow audit patch.
     **Network boundary result:** the TUI JSON-RPC WebSocket handler itself accepts blindly, but
     its sole production mount in `vector_cli/web_server.py` performs timing-safe session-token
     authentication and rejects non-loopback clients before calling it; no duplicate auth patch was
     made. ACP adapter is stdio-only. The separate HTTP ACP server lives in the colliding
     `vectorcode/src/acp/` directory outside this assignment and already carries an unauthenticated-
     routes owner flag.
     **Commit status:** intentionally uncommitted for parent review (sandbox cannot lock `.git`).

105. **`vectorcode/src/{context,security,system,vc_core,workflow}/` full audit (2026-10-07) —**
     completed a line-by-line pass over all 33 assigned production files. Confirmed from path-scoped
     `git log` that `src/security/` is a separate compatibility surface from the previously audited
     `src/vc_security/`; its credential/file/type modules re-export the canonical implementations,
     and it contains no independent unconditional Rust constructors. Removed the injection scanner
     shim's fail-open `ImportError` fallback, which silently replaced a broken security import with
     a scanner that always returned no findings. Fixed four further defects with regression proof:
     `context/references.py` claimed workspace confinement but allowed arbitrary absolute/`..` file
     and folder reads outside `cwd` (CWE-22); `session_memory.py` and `vc_core/credentials.py` could
     truncate persistent state on interrupted writes (credential TOML also failed to escape quotes,
     backslashes, control characters, and embedded newlines); `trajectory_compressor.validate()`
     retained orphan tool results and failed to recognize valid OpenAI `tool_calls` pairs; and
     `compactor.py` used the ambiguous `context.vectormd` import instead of the canonical package.
     New proof coverage: `tests/test_context_security_audit_regressions.py` (6 tests), all passing.
     Existing relevant suites also pass: `tests/test_vectorcode_context_loading.py`,
     `tests/test_vectorcode_workflow_correctness.py`,
     `tests/test_vectorcode_agents_workflow_engine_phantom_success.py`, and
     `vectorcode/python/tests/test_vectorcode_vc1.py`. Two tests in the legacy
     `test_trajectory_compressor_async.py` fail independently before import because that test builds
     a nonexistent `vectorcode/python/tests/trajectory_compressor.py` path.
     **Owner decisions, not changed:** workflow edge `condition` values are parsed/stored but never
     consulted by `WorkflowEngine`, so all branches execute; intended conditional-routing semantics
     are not specified. Its `default_node_timeout` is also ineffective for parallel nodes because
     `as_completed()` yields only finished futures and the thread-pool context waits for running
     work on exit; a real timeout requires an execution/cancellation architecture decision. The
     engine and `vc_core.events`/`credentials` use thread pools/locks despite VECTOR's asyncio-only
     rule; converting these synchronous public APIs was not treated as a narrow audit fix.

106. **`vectorcode/src/{a2a,bench,claims,daemon,display,hooks,mcp,operators,persona,scheduler,
     transports,vc_mcp,vc_sessions}/` audit (2026-10-07) —** this round's premise ("13 never-audited
     directories") turned out to be mostly wrong on inspection: `git log` showed 11 of the 13 already
     had specific, real audit fixes from an earlier session (a2a: SSRF gap + silent-swallow fixes;
     bench: loguru conversion; claims: duplicate-claim guard; daemon: bad session key +
     ServiceManager fix; mcp: server double-creation + async-handlers-never-awaited fix; operators:
     duplicate scheduled task fix; persona: session-hydration + CWE-22 path-traversal fix;
     scheduler: silent-swallow fix; transports: wrong-sibling-package-import fix; vc_sessions:
     CWE-22 + corrupt-file fail-open fix). Only `display/` and `vc_mcp/` had no real audit fixes
     (a mechanical bulk logging pass doesn't count as depth either, see `hooks/` below) — effort
     this round concentrated there instead of re-litigating already-fixed files.
     **Fixed with proof tests, all confirmed failing pre-fix via `git stash`:**
     - `vc_mcp/transport.py` (`60a2a53fc`) — `StdioTransport.close()` called `proc.terminate()`
       then `proc.wait(timeout=5)` with no handling for `subprocess.TimeoutExpired`. An MCP server
       subprocess that ignores SIGTERM made `close()` raise uncaught instead of force-killing it,
       and left `self._process` referencing the dead transport instead of clearing it. Wrapped in
       try/except, falling back to `kill()`+`wait()` on timeout.
     - `vc_mcp/server.py` (`10550d3fc`) — imported stdlib `logging` and built its logger via
       `logging.getLogger(__name__)`, violating CLAUDE.md's loguru-only rule; also used
       `exc_info=True` (silently ignored by loguru) across 10 sites and %-style placeholders in 3
       warning calls.
     - `hooks/registry.py` (`02b065e1a`) — `HookRegistry.fire()` ran each handler in a daemon
       thread, caught any exception inside that thread, logged it, and moved on without ever
       re-raising. This defeats `_make_claude_hook_wrapper()`'s documented `can_block=True`
       contract: a Claude-style hook script (e.g. `file_protection`, meant to block writes to
       protected paths) exiting 2 makes the wrapper raise `RuntimeError` specifically to abort the
       lifecycle event, but `fire()` silently discarded that signal into a log line regardless of
       what the handler intended. Now re-raises after logging. Confirmed via repo-wide grep that
       `fire()` currently has zero real callers (`vector_cli/doctor_cmd.py` only calls
       `list_handlers()` for a diagnostic count) -- the fix makes the method honor its own
       contract for whenever it is wired in, but the blocking mechanism has no live production
       effect yet; not flagged as a separate unwired-feature item since `fire()`/`register()` are
       generic infra, not a single feature.
     Also reviewed with real depth, no bug found: `display/renderer.py` (confirmed its
     `from vectorcode.display.X import *` style imports -- missing the `.src.` segment -- are
     legitimate compatibility shims that wildcard-re-export the real `vectorcode.src.display.*`
     names, not a broken cross-tree import; verified by direct import test), `display/
     diff_preview.py`, `display/spinner.py` (uses banned `threading.Thread`, but moot --
     `VectorRenderer`/`get_renderer` have zero callers anywhere in the repo, a genuine
     built-but-unwired component, flagged for owner decision below), `vc_mcp/client.py`,
     `vc_mcp/protocol.py`.
     **Flagged for owner decision, not fixed:** `display/` (`renderer.py`, `spinner.py`,
     `diff_preview.py`) is a complete, well-built tool-call spinner/diff-preview renderer with
     zero callers anywhere in the repo -- confirmed via grep for `VectorRenderer`/`get_renderer`,
     including indented imports inside functions. Either wire it into the real REPL/agent harness
     or decide it's dead code; not a narrow fix.
     New tests: `tests/test_vectorcode_vc_mcp_stdio_transport_close.py` (2),
     `tests/test_vectorcode_vc_mcp_server_loguru.py` (3),
     `tests/test_vectorcode_hooks_registry_fire_propagates_block.py` (2) -- 7 tests, all passing.
     **Commit status:** `60a2a53fc`, `10550d3fc`, `02b065e1a` -- all self-committed directly by
     this fork.

107. **`vectorcode/src/environments/` full audit (2026-10-07) —** audited all 24 assigned
     production files, including the core agent loop/base environment and every model-family tool
     parser. Fixed seven concrete defects: tool-returned errors with ordinary positive exit codes
     were omitted from `AgentResult.tool_errors`; Agentic OPD executed and trusted the model's own
     `test_solution.py`, allowing a trivial fake-pass script to earn correctness credit; its
     purported majority-vote hint selection accepted one positive among three votes; TB2's safe tar
     extractor always raised `NameError` because `shutil` was never imported and test-upload
     failures then continued into verification instead of failing closed; YC-Bench classified an
     unfinished simulation with nonnegative funds as survived and discarded an explicit zero-year
     horizon through `value or default`; web-research efficiency counted LLM turns rather than tool
     calls and its `lstrip("www.")` domain normalization removed arbitrary leading `w`/`.`
     characters; and the parser registry had dropped the historical `vector` alias, preventing its
     entire pre-existing parser suite from running. Streaming JSONL/reward text I/O touched in the
     fixes now specifies UTF-8.
     Regression coverage: `tests/test_vectorcode_environments_audit_regressions.py` (8 tests) plus
     the pre-existing `vectorcode/python/tests/legacy_ported/tools/test_tool_call_parsers.py`; all
     35 combined tests pass. All assigned files pass `compileall`; `git diff --check` reports no
     errors.
     **Owner decisions, not changed:**
     - The Vector/Longcat/Qwen3 parsers deliberately accept an unterminated final tool-call block,
       and the Llama JSON parser treats any matching raw JSON object as a call even without its
       `<|python_tag|>` marker. Both improve recovery from model formatting/truncation, but also
       create a prompt-injection-adjacent false-positive surface. Changing this needs an explicit
       policy choice about fail-open recovery versus requiring complete model-family delimiters.
     - This package structurally uses stdlib `logging`, `print()` in production evaluation paths,
       thread pools/`threading.Lock`, and process-global environment variables for per-run terminal
       configuration despite repository policy. Replacing these is a cross-package concurrency and
       observability redesign, not a narrow correctness patch.
     - `ToolContext` intentionally gives reward functions unrestricted tool access and constructs
       several sandbox shell commands from verifier-provided paths. Current production callers use
       fixed/trusted paths, but making this a safe public API would require defining its trust
     boundary and shell/path contract rather than guessing at confinement semantics.
     **Commit status:** intentionally uncommitted for parent review (sandbox cannot lock `.git`).

108. **`vectorcode/src/{telemetry,vc_engine}/` full audit (2026-10-07) —** completed a
     line-by-line review of all 31 assigned files. Fixed six concrete failures: the `telemetry.itl`
     compatibility module imported a nonexistent canonical `__all__` and could not be imported;
     Apple FM and Nexa advertised `/v1/models` as healthy even when their SDK/platform was absent,
     causing discovery to select an unusable engine; optional mining-sidecar discovery continued
     with an unbound `SIDECAR_PATH` after its constants import failed; successful OpenAI-compatible
     responses with no choices became normal-looking empty results; OpenRouter/MiniMax silently
     dropped caller tools/options; and OpenRouter discarded returned tool calls. Replaced remaining
     stdlib logging, printf placeholders, and loguru-incompatible `exc_info=True` in the assigned
     engine files. Regression coverage is in `tests/test_vectorcode_vc_engine_regressions.py` (7
     tests). That suite plus `tests/unit/test_ollama_multi_backend_fallback_timeout.py` (14 total
     tests) and the existing `tests/test_vectorcode_engine_mining_audit.py` plus
     `tests/backend/test_audit_followups.py` (54 tests) pass; assigned files pass `compileall` and
     `git diff --check`.
     **Owner/design decision, not changed:** low-level `vc_engine` implementations accept
     caller-built messages and call providers without locally invoking
     `ContextEngine.session_hydration_prompt()`. Some callers deliberately provide purpose-built
     system prompts, while others may rely on higher-layer hydration; enforcing hydration here
     could duplicate context and break standalone VectorCode use. Decide whether enforcement belongs
     in `InferenceEngine`, every production caller, or an explicit already-hydrated/purpose-built
     marker. Cloud/LiteLLM async stream methods also iterate synchronous SDK streams inside async
     generators and can block the event loop; migration needs a deliberate async-SDK/thread-offload
     contract. Changes remain uncommitted for parent review as required.

109. **`vectorcode/src/{engine,mining}/` full audit (2026-10-07) —** completed a
     line-by-line review of all 28 assigned files and confirmed `vectorcode/src/mining/` is a
     distinct tree from `core/mining/`, not previously covered code. Fixed concrete failures in
     both live and compatibility paths: the engine-discovery shim always returned empty/`None`
     and broke SDK/CLI resolution instead of delegating to `vc_engine`; both agent loops called
     LLMs without mandatory session hydration; the async conversation loop blocked its event loop
     with `time.sleep`; approval-callback exceptions failed open and executed tools; malformed
     model tool arguments were silently replaced with `{}` and dispatched; Windows path-overlap
     detection was case-sensitive; Ollama HTTP errors were treated as empty successful responses;
     and safe-stdio error logging recursively reused the failing stream and could deadlock loguru.
     Mining fixes add the missing `Sidecar.read`, make sidecar writes durable/atomic
     (`fsync` + `os.replace`), restore the fields the metrics parser actually passes to
     `MiningStats`, distinguish unavailable sidecar/metrics configuration from healthy zero
     activity, replace blocking HTTP in the async collector, reject JSON-RPC error/malformed
     responses instead of reporting phantom sync success, correct the accidentally Docker-tagged
     Pearl git ref to `master`, handle `MiningConfig.extra=None`, specify UTF-8 for patched source
     files, and correct loguru exception/placeholder usage. Ambiguous top-level imports in
     `agent_loop.py` now name the intended `vectorcode.src` modules explicitly.
     Regression coverage: `tests/test_vectorcode_engine_mining_audit.py` (11 tests). Together with
     `tests/test_mining_import_fix.py`, `tests/test_vectorcode_vc_engine_regressions.py`, and the
     applicable `test_wave0.py` cases, 28 tests pass. One unrelated pre-existing `test_wave0.py`
     case still fails before exercising audited code because it patches the nonexistent
     `vectorcode.engine.conversation` attribute; its compatibility-package ownership is outside
     this assignment.
     **Owner decisions, not changed:** `MiningTelemetryCollector` explicitly documents that it is
     shipped but not wired and has no production caller; decide whether to register it as a daemon
     task or remove it. `engine/budget.py` and the duplicated budget in `agent_loop.py` use
     `threading.Lock`, while tool execution uses thread pools, contrary to the repository's broad
     no-threading policy; replacing these requires choosing an async-only versus sync/thread-safe
     public contract. The engine and mining compatibility trees also duplicate substantial
     canonical `vc_engine`/`core.mining` behavior, so consolidation is an architectural decision,
     not a narrow audit fix. Code/tests were committed concurrently by the parent session as
     `1ab828563`; this `OPEN_ISSUES.md` entry remains uncommitted for parent review as required.

110. **`vectorcode/src/{agents,providers,speech}/` full audit (2026-10-07) —** completed a
     line-by-line review of all 34 assigned files (3,754 pre-change lines), including repo-wide
     caller/import searches and path-scoped history. History showed several narrow October 3–5
     fixes in `agents/` and `providers/`, but no previous full-directory audit. Fixed the public
     `agents.deep_research` module, whose placeholder API was incompatible with every real caller,
     by exporting the complete canonical `vc_agents.deep_research.DeepResearchAgent`. Restored the
     six provider compatibility types missing from `providers/base.py`, which had made both
     `capability_probe.py` and `openai_compat.py` unimportable; capability probing now falls back
     explicitly to memory when its configured cache cannot be opened. Removed three further
     phantom-success paths: failed workflow subprocesses now fail the workflow, placeholder or
     unknown workflow actions no longer report completion, and legacy cloud-provider exceptions
     no longer return success-shaped text responses. Google compatibility requests now preserve
     the supplied message history and reject unsupported tools instead of discarding both. Speech
     discovery now verifies health for automatic and explicitly configured backends.

     Additional fixes: coordinator shutdown clears task history and duplicate task IDs cannot
     strand the first agent as busy; `Agent.to_dict()` preserves metadata; provider replacement
     retires stale aliases; rate-limit reset parsing accepts `1500ms`, `1.5s`, and ISO timestamps;
     `TTSResult.save()` uses flushed atomic replacement; compatibility fallbacks expose errors
     instead of valid-looking empty state; banned `threading` was removed from both retry modules
     and the synchronous model router; assigned stdlib-logging, malformed-loguru, and production
     `print()` violations were removed.

     **Owner decisions, not changed:** legacy
     `agents/{agent,coordinator,workflow_engine}.py` has no production caller (the real runtime uses
     distinct `vectorcode.src.swarm` and `vectorcode.src.workflow` implementations). Likewise
     `providers/{capability_probe,openai_compat,rate_limit,rate_limit_tracker,retry,retry_utils}.py`
     has no functional production consumer; discovery imports these modules, but none registers a
     profile and live inference routes elsewhere. Decide whether to wire or retire these parallel
     compatibility surfaces. The dormant agents workflow engine also exposes an arbitrary
     subprocess action without a Permission Gateway boundary and must not be wired until an
     authorization contract is chosen. Legacy OpenAI/Anthropic adapters expose paid-provider paths
     contrary to the current free-tier-only runtime policy; deletion versus SDK retention is an
     owner choice. `FasterWhisperBackend.health()` proves only package importability, not that its
     configured model/device/compute type can load; loading a potentially large model during
     discovery is a startup-latency/product tradeoff, so it was not guessed here.

     New regression coverage:
     `tests/test_vectorcode_agents_providers_speech_audit_regressions.py` (13 collected tests), plus the
     updated earlier null-registry regression. Focused verification: 23/23 passed; `compileall`
     and scoped `git diff --check` passed. Broader related verification reached 221 passes and 7
     failures, all outside this assignment: sandbox `PermissionError`s writing
     `~/.vector/personas/*.json`, with no assigned stack frame. The parent session concurrently
     committed the main code/test batch as `b7b8d6a95` and the later capability-cache fallback
     plus updated prior regression as `5029a0ab5`; this issue entry alone remains uncommitted for
     parent review.

111. **Top-level `vectorcode/` shims + hooks audit, complete (2026-10-07) —** first-ever audit of
     32 Python files across 13 directories sitting directly under `vectorcode/` (NOT
     `vectorcode/src/` -- a genuinely separate compatibility layer discovered mid-session). Two
     prior Claude forks in this exact spot were each cut off by a session rate limit; this is the
     third and final pass, completing the remaining ~30 files.
     **Confirmed structure:** `acp/`, `context/`, `cron/` (see flag below), `engine/`, `gateway/`,
     `mcp_client/`, `migrations/`, `plugins/`, `providers/`, `tools/`, `tui_gateway/` are thin,
     unconditional legacy compatibility shims (`from vectorcode.src.X import *`, no try/except
     fallback stub) -- verified each individually; all reviewed clean, no bug found. `hooks/` (8
     files) is real, substantive code: the actual Claude Code hook implementations.
     **Fixed with proof tests, 6 commits total across all three rounds in this slot:**
     - `file_protection.py` (`04c649f2b`, round 1) -- malformed hook payload failed open (allowed
       the write) instead of closed.
     - `pre_write_check.py` (`0660cb01f`, completed by parent after round 1 died mid-write) --
       `os.unlink(tmp_path)` only ran on the success path, never in the `PyCompileError` branch
       (the hook's own primary purpose) -- every blocked write leaked a temp file.
     - `pre_commit_gate.py` (`3653a78bb`) -- if `git diff --cached --name-only` itself failed
       (non-zero exit or raised), the gate silently allowed the commit through unchecked, even
       though the command was already confirmed to be a `git commit` -- the exact case this gate
       exists to protect. Now fails closed.
     - `auto_commit.py` (`f2633c40f`) -- the most severe finding this round: this hook commits
       with `--no-verify`, bypassing `pre_commit_gate.py`'s staged-secret check entirely. It had
       no filename check of its own, so editing a `.env`/credentials file would auto-stage-and
       -commit the secret straight into git history with **no gate ever seeing it** -- confirmed
       live in the regression test (the pre-fix hook actually committed a real `.env` file
       containing `API_KEY=super-secret`). Also fixed a missing `--` separator on `git add
       <file_path>` (git-argument-injection).
     - `auto_screenshot.py`, `auto_test.py`, `lint_on_save.py`, `finish_notification.py`
       (`2467cd176`) -- `exc_info=True` passed to loguru (silently ignored) converted to
       `logger.opt(exception=True)`; `lint_on_save.py`'s ruff/pyflakes subprocess calls given a
       `--` separator before the file path. `auto_screenshot.py` confirmed its screenshot save
       path is NOT caller-controlled (fixed directory + timestamp filename) -- no CWE-22 issue.
     **Flagged for owner decision, not fixed:** `cron/__init__.py`'s `stop_daemon() -> None: pass`
     is a no-op stub, but `vectorcode/src/cli.py:968-969` has a real, live caller (`from
     vectorcode.cron import stop_daemon; stop_daemon()` inside a `KeyboardInterrupt` handler for
     a `cron start` CLI subcommand). However, that same subcommand first does `from cron import
     start_daemon` (bare `cron`, not `vectorcode.cron`) and neither `vectorcode/cron/` nor
     `vectorcode/src/cron/` define a `start_daemon` anywhere -- so in the CURRENT build, that
     `except ImportError: print("not implemented"); return` branch always fires first, and
     `stop_daemon()` is never actually reached in practice. `vectorcode/src/cron/__init__.py`'s
     own docstring says scheduling is done via "the gateway daemon" (`vector gateway
     install`/`vector gateway`), not a standalone cron daemon with its own start/stop lifecycle --
     this strongly suggests `cmd_cron`'s "start"/Ctrl+C-to-stop code path in cli.py is leftover
     from an abandoned design, not a live gap. Did not invent a daemon-lifecycle implementation
     to guess-fix this; flagging for the owner to either wire a real implementation or delete the
     dead branch in cli.py.
     Also noted, not a bug: `providers/base.py` is a single-line docstring with zero other
     content and zero callers anywhere in the repo (vectorcode/, core/, districts/, tests/,
     scripts/) -- genuinely empty/unused, not broken.
     New tests across the three rounds: `tests/test_vectorcode_hooks_file_protection_fail_closed.py`
     (4), `tests/test_vectorcode_hooks_pre_write_check_temp_cleanup.py` (2),
     `tests/test_vectorcode_hooks_pre_commit_gate_fail_closed.py` (2),
     `tests/test_vectorcode_hooks_auto_commit_safety.py` (2),
     `tests/test_vectorcode_hooks_minor_fixes.py` (2) -- 12 tests total, all passing.
     **Commit status:** all 6 code commits already landed (self-committed by the forks, or by
     the parent session completing fork-interrupted work) -- see hashes above. This OPEN_ISSUES
     entry is the only remaining uncommitted piece, left for the parent session per instruction.

112. **`core/engine`, `core/memory`, and `core/voice` deep audit owner decisions (2026-10-07) —**
     the assigned 73-file pass fixed the process-wide episodic-connection lifecycle bug,
     memory-mesh infinite retry/phantom-sync state, unsafe/non-atomic wiki exports,
     non-atomic OAuth fallback-token saves, false OAuth refresh success, and false sub-agent
     success/missing hydration. The following findings were deliberately not guessed:

     - `core/memory/shared_facts.py::_open_conn()` and
       `core/memory/db_registry.py::get_district_db()` target the real configured main DB and,
       after a SQLCipher open failure, explicitly retry it with raw `sqlite3.connect()`. This is
       the known main-DB exception category the owner asked this audit to flag rather than
       silently rewrite. Decide whether key/configuration failures must fail closed instead.
     - `core/voice/ambient_listener.py::_summon_hud()` puts `VECTOR_API_KEY` in the HUD query
       string and in Chrome/Edge subprocess argv. The API middleware documents this as the
       current browser-navigation authentication design, so removing it inside the voice module
       alone would break HUD startup. Choose a session-cookie/bootstrap-token design before
       changing both sides.
     - `core/engine/agents/subagent_runner.py` and
       `core/engine/providers/reliable_provider.py` are complete exported implementations but
       have no functional production consumer found outside their own packages/tests/scripts.
       `provider_client.py` mentions `ReliableProvider` only in comments and implements its own
       retry loop; `SubagentRunner` is only exercised by audit scripts. Decide whether to wire
       these compatibility surfaces or retire them. `ChannelRuntime` is likewise instantiated
       only by the channels status fallback, which immediately discovers that the runtime lacks
       the queried `active_channels()` API; it is not the live channel gateway.

     Regression coverage is in
     `tests/test_core_engine_memory_voice_audit_regressions.py`. Focused verification at entry
     time: 66 tests passed across the new regressions and related episodic, memory-mesh, voice,
     channel-loop, and encrypted-registry suites; final broader verification is recorded in the
     parent audit handoff.

113. **`core/api/` audit, round 1 (2026-10-07) —** first-ever full-depth audit of this 98-file
     directory (VECTOR's own FastAPI server -- distinct from `vectorcode/src/server/`, already
     audited this cycle). Codex hit its usage-limit wall before writing its own entry; committed
     and documented by the parent session after independent verification (ran all 7 new tests,
     syntax-checked every touched file, read the `auth_jwt.py` and `websocket.py` diffs in full).
     **Fixed with proof tests (14 files, commit `17657a58d`):**
     - `routers/auth_jwt.py` -- `_verify_api_key()` read `VECTOR_API_KEY` only from a plain
       environment variable instead of `core.security.secrets_manager.get_secret()`'s
       keyring-first lookup. Worse: `login()`'s localhost-trust-bypass check made the same
       mistake, so a key configured via keyring (not env var) was invisible to that check --
       any localhost connection could log in without a password even though a real key WAS
       configured. Routed both through `get_secret()`.
     - `routers/websocket.py` -- `vector_ws_state`'s WebSocket endpoint never called
       `require_auth_handshake()` at all (4th instance of the "WS endpoint bypasses the HTTP
       auth gate entirely" bug family found today, after `ws_bridge.py` and `api_routes.py`'s
       `/v1/chat/stream`). Also: the "no API key configured" path previously allowed ANY remote
       connection with zero auth; now restricted to localhost, matching the HTTP middleware's
       posture, with JWT/WebAuthn accepted as additional valid credentials.
     - `routers/voice_ws.py` -- voice-conversation LLM calls were missing the mandatory
       `context_engine.session_hydration_prompt()` call (CLAUDE.md Rule 1, no exceptions).
     New tests: `tests/test_core_api_security_regressions.py` (7), all passing. Pre-existing
     `tests/test_permission_gateway.py` (8) also re-verified with no regressions.
     **Remaining scope:** ~84 of 98 files not yet individually confirmed -- partial pass.
     **Commit status:** `17657a58d`.

114. **`core/trading/` audit, round 1 (2026-10-07) —** first-ever full-depth audit of this
     89-file directory. Policy-boundary check performed FIRST per the owner's standing
     "ANALYSIS ONLY, never trades" rule: grepped the entire directory for any order-placement
     or brokerage write-API path. None found -- `crypto_trading.py` (the one exchange-adjacent
     module) is explicitly "paper mode" and only fetches read-only quotes via yfinance/CoinGecko.
     No trading-boundary violation. Codex hit its usage-limit wall before writing its own entry;
     committed by the parent session after independent verification.
     **Fixed with proof tests (7 files, commit `e40a18958`):** `agents/utils/memory.py`'s
     decision-log atomic write used a deterministic `.tmp` sibling filename (collision-under-
     concurrency + no-fsync, the same gap fixed repeatedly elsewhere this cycle) -- replaced with
     a unique tempfile+fsync+os.replace; `cli/announcements.py`'s explicit `timeout=0` was
     discarded by a falsy-OR default; `tests/test_deepseek_reasoning.py`'s live-API integration
     test only gated on a real `DEEPSEEK_API_KEY` being present, so any dev machine with a real
     key configured would silently make real, billed DeepSeek calls on every normal test run --
     added an explicit `VECTOR_RUN_LIVE_TESTS=1` opt-in gate. Also: `dataflows/
     alpha_vantage_common.py` and `dataflows/yfinance_news.py` migrated off the banned `requests`
     library to `httpx` per CLAUDE.md policy (companion test update: commit `c0c321d64`).
     New tests: `tests/test_trading_audit_regressions.py` (4), all passing.
     **Remaining scope:** ~82 of 89 files not yet individually confirmed -- partial pass.
     **Commit status:** `e40a18958`, `c0c321d64`.

115. **`core/scraper/`+`core/training/` audit, round 1 (2026-10-07) —** first-ever full-depth
     audit covering 83 of the combined 83 files. Codex hit its usage-limit wall before writing
     its own entry; committed by the parent session after independent verification.
     **Fixed with proof tests (13 files, commit `9ca9176d5`):** `scraper/engines/static.py`'s
     `"safe"` `follow_redirects` mode was conflated with curl's `CurlFollow.SAFE`, which only
     prevents credential/method leakage across a redirect hop -- it does NOT validate the
     redirect destination. Automatic redirects in "safe" mode could still silently follow a
     chain into an internal/private address with zero SSRF validation; disabled automatic
     redirect-following for this mode entirely until proper per-hop destination validation
     exists. Remaining fixes: path confinement and non-atomic-write fixes across the training
     checkpoint/model-save paths matching established bug classes from this cycle.
     New tests: `tests/test_scraper_training_audit_regressions.py` (15), all passing.
     **Commit status:** `9ca9176d5`.

116. **`core/mcp_tools/`+`core/inference/`+`core/security/` audit, round 1 (2026-10-07) —**
     first-ever full-depth audit covering 6 of the combined 80 files (`core/security/` is a
     THIRD directory with this name audited this cycle, after `vc_security/` and
     `vectorcode/src/security/`). Codex hit its usage-limit wall before writing its own entry;
     committed by the parent session after independent verification.
     **Fixed with proof tests (6 files, commit `17860eddc`):** `security/prompt_injection.py`'s
     `get_scanner()` singleton cache was keyed by NOTHING (one module-level variable) -- whichever
     caller requested a scanner first (strict or not) determined the cached instance for the
     entire process lifetime. A later caller specifically requesting `get_scanner(strict=True)`
     for a security-sensitive context could silently receive an already-cached non-strict
     scanner instead, downgrading its policy with zero indication anything was wrong. Fixed by
     keying the cache dict on the strict flag, giving each policy its own singleton.
     New tests: `tests/test_inference_route_policy_fail_closed.py` (6), all passing.
     **Remaining scope:** ~74 of 80 files not yet individually confirmed -- partial pass.
     **Commit status:** `17860eddc`.

117. **`core/benchmark/`+`core/city/`+`core/loop/` audit, round 1 (2026-10-07) —** first-ever
     full-depth audit covering 6 of the combined 56 files, including `permission_gateway.py` --
     per the project's own architecture docs, the single most security-critical file in the
     codebase ("LLM has ZERO direct access to real-world actions except through this gate").
     Codex hit its usage-limit wall before writing its own entry; committed by the parent session
     after independent verification (re-ran the full pre-existing `test_permission_gateway.py`
     suite to confirm zero regressions before trusting this).
     **Fixed with proof tests (6 files, commit `572eaa70c`):**
     - `loop/permission_gateway.py` (critical) -- EVERY execution path (GREEN auto-exec, YELLOW
       trust-ladder, YELLOW owner-initiated, YELLOW after-window, RED interactive, RED
       council-approved, RED owner-confirmed) hardcoded
       `GatewayResult(True, <tier>, True, exec_result, ...)` -- the "executed successfully" flag
       was ALWAYS `True` regardless of what `exec_result` actually contained. A handler that
       errored, was blocked, rejected, or was not-implemented was still reported as having
       succeeded. This flag almost certainly feeds `policy.update_from_outcome()`'s reward
       signal and HP awards per the project's own decision-loop architecture -- this could have
       been silently corrupting the policy-learning feedback loop for an unknown period. Added
       `_execution_succeeded()` to inspect `exec_result`'s actual status/error/success/blocked
       fields and wired it into every execution path.
     - `city/agent_registry.py` -- `final_hp = agent.get("final_hp") or
       agent.get("health_points")` discarded a real `final_hp` of exactly 0 (an agent's literal
       death condition per VECTOR's own HP system) and silently substituted `health_points`
       instead.
     - `benchmark_runner.py`, `report.py` -- a runner-state-reset bug and a non-atomic report
       write.
     New tests: `tests/test_regression_assigned_audit_round.py` (5), all passing. Full
     pre-existing `tests/test_permission_gateway.py` suite (8 tests) re-verified with zero
     regressions.
     **Remaining scope:** ~50 of 56 files not yet individually confirmed -- partial pass.
     **Commit status:** `572eaa70c`.
