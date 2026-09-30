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
