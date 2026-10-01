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
