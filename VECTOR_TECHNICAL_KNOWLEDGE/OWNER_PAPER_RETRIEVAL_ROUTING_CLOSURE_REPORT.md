# VECTOR V1 — OWNER PAPER-RETRIEVAL ROUTING CLOSURE REPORT

Date: 2026-09-22 (IST) · Branch `production-hardening-complete` · Single bounded repair of the one blocker left by `PRE_RG_D2_FINAL_CLOSURE_REPORT.md` §15 #1.

**VERDICT: OWNER PAPER RETRIEVAL CLOSURE PASS — BRIDGE HANDOFF READY**

P1 PASS, P2 PASS, P3 PASS, real arXiv evidence on P1/P2, canonical `search_arxiv` identity preserved from Candidate through PermissionGateway to dispatch, no new security regression. This report does not claim V1 itself is complete.

---

## 1. Starting HEAD

Branch `production-hardening-complete`, HEAD `3e859a123f2b97abcb3535790fb3ee4354e28d85` (verified before any edit). VECTOR stopped, port 8000 clear, no python processes. Known unstaged artifacts preserved and never staged: the pending Section 31 edit to `OWNER_ROUTING_CLOSURE_REPORT.md`, `data/models/neural_policy.{pt,meta.json}`, `data/council_log.jsonl`.

## 2. Root cause

Recent-paper retrieval depended on the general LLM classifier. In `commands.py` the T1 retrieval route (`current_information_plan`) ran only **after** `classify_chat_intent()` and only when it returned exactly `answer_question`:

- **B1** ("Any recent papers on retrieval-augmented generation for code?"): the classifier hit its 45 s ceiling → `classification_failed` early return → retrieval never reached.
- **B2** ("What new papers have come out on state space models like Mamba?"): the classifier answered an action-shaped `research_papers_search` → canonicalized to `research_papers` (not permission-registered) → PermissionGateway `UNKNOWN … blocked` → retrieval never reached.

Two latent flaws in the deterministic seam were exposed while closing this (both fixed, both inside the same seam):

1. `_PAPER_RE` counted a bare **"published"** as an academic cue, so "the latest news on Tesla published this week" planned a `retrieve` (arXiv) — a wrong-routing bug in the existing post-classifier T1 route (required test 5).
2. `_research_topic` could return a **task verb** as the topic: "…current research on this general subject and summarize it for me" → topic `summarize`. It was invisible while the route sat behind the classifier; the new pre-route would have searched arXiv for "summarize". Caught by the POST-RGC2 fallback-fabrication suite (3 tests newly failed), which is why regression was run before any live probe.

## 3. Smallest repair

Uses the existing deterministic seam (`current_information_plan`); no second retrieval architecture, no bypass of Candidate / DecisionEngine / PermissionGateway, no tier changes.

- `paper_retrieval_topic(text, *, require_recency=True)` (anti_fabrication.py): the concrete topic when the request is a genuine academic-paper retrieval request, else `None` (fail closed). Requires recency + academic cue + concrete topic via `current_information_plan`; any action verb (send/email/post/schedule/save/deploy/…) disqualifies it; creative/owner-local text is excluded.
- Pre-classifier route (commands.py, "respond" branch): if `paper_retrieval_topic(text)` returns a topic, build the `search_arxiv` intent directly (identity `current_info_route`) and **do not call the classifier**; it then follows the unchanged Step 3–8 path (single Candidate → `DecisionEngine.evaluate` → `PermissionGateway.execute` → `Governor.dispatch` → evidence renderer). Anything else keeps the old classifier path.
- `_fold_paper_retrieval_alias`: after the classifier, a `research_papers` / `research_papers_search` verdict folds to `search_arxiv` (identity `alias_to_search_arxiv`) **only** when the text is genuinely a paper-retrieval request with a topic and no action verb; otherwise the alias stays `UNKNOWN`-blocked (fail closed).
- Seam corrections: `_PAPER_RE` no longer treats bare "published" as an academic cue; `_research_topic` cuts a trailing task clause ("…, and summarize it for me", "… and explain …", "please", "for me") before extracting the topic.

Passes used: one implementation pass; one directly-related correction pass (the topic-clause fix, found by regression).

## 4. Production files changed

| File | Change |
|---|---|
| `core/security/anti_fabrication.py` | +49/−2: `paper_retrieval_topic`, action-verb guard, `_PAPER_RE` narrowing, `_TOPIC_TASK_CLAUSE_RE`, `__all__` |
| `core/api/routers/commands.py` | +40/−1: pre-classifier route, `_fold_paper_retrieval_alias`, import |

Not modified: `research_hub.py`, `permission_gateway.py`, `decision_engine.py`, `governor.py`, `intent_matcher.py`, config permission tiers, the bridge. Diff audit: 89 insertions, 3 deletions across the two files; every hunk reviewed; no stray control characters (a first patch attempt wrote three backspace characters into a regex — caught by `cat -A`, repaired, and the final diff scanned clean).

## 5. Tests

New: `tests/test_owner_paper_retrieval_routing.py` — 36 tests, written RED first (both demonstrated failures reproduced through the real `/command` path before any production change), all GREEN after. Mocked boundaries are external only (LLMs, `Governor.dispatch` = arXiv); routing, `DecisionEngine`, `PermissionGateway`, `command_endpoint` run as production code.

| # | Required test | Coverage |
|---|---|---|
| 1 | recent papers + topic + classifier timeout → `search_arxiv` via normal path | classifier mock raises `TimeoutError`; asserts `search_arxiv` dispatched, classifier **never consulted** |
| 2 | classifier returns `research_papers_search` → canonical `search_arxiv` | endpoint-level, plus post-classifier fold test with no recency marker |
| 3 | `research_papers` alias → canonical identity | fold unit tests (both raw/canonical forms), fail-closed cases, only paper aliases fold |
| 4 | timeless academic question → no forced retrieval | 3 questions, dispatch 0, conversational LLM used |
| 5 | product/version/news/price request → not arXiv | 3 requests incl. the "published" case; honest verify-decline, no LLM facts |
| 6 | vague "what's new?" → no invented topic | vague research request asks for a topic; bare "What's new?" is small talk and never searches; anaphoric ("this general subject", "that, and explain it") and task-clause topics rejected |
| 7 | retrieval failure → honest inability | empty / missing / raised, under both classifier states; no LLM factual fallback |
| 8 | success → actual evidence | title, URL, authors, date rendered |
| 9 | identity chain | spies on `DecisionEngine.evaluate` candidates, `PermissionGateway._classify` and dispatched type: all `search_arxiv`, for classifier = timeout / research_papers_search / conversation |
| 10 | RED/YELLOW unchanged, actions not swallowed | tier assertions (`search_arxiv` GREEN, `send_email`/`deploy_production` RED, `commit_code` YELLOW, `research_papers` still UNKNOWN); action-verb request not taken by pre-route |

## 6. Regression results

Targeted set: 447 tests (new routing; PRE-RG-D2 A/B/C; V1 T1/T2/T3; F1/F2/F3; POST-RGC2 classifier / fallback-fabrication / situation-hash; PermissionGateway; RED interactive; command intent routing; RR-1; RR-3.7a/b/b1/c; ResearchHub/spec09) → 445 pass, 2 fail. Plus a second sweep of every other test importing the modified modules (content/email/interview/karpathy/learning/marketing/security run-wiring, RR-1.5 vocabulary, RR-3.6 boundary, ws/command parity, governor thread-hop): 173 tests, 0 failures, 1 skip.

| Failure | Class |
|---|---|
| `test_permission_gateway.py::test_red_action_times_out_without_confirmation` | PRE-EXISTING (identical on baseline, confirmed in the previous mission) |
| `test_rr3_7b1_ambiguous_endpoint_closure.py::test_rr3_7b1_ambiguity_closure_diff_scope` | PRE-EXISTING (identical on baseline) |

Mid-mission: 3 `test_postrgc2_fallback_fabrication_guard` tests failed NEW after the implementation pass; root cause was flaw (2) in §2, fixed by the correction pass — all three now pass. NEW at the end: 0. No authorization/security regression.

## 7. Frozen probe SHA

`paper_routing_probes.json` (frozen before VECTOR was started; re-verified with `sha256sum -c` before each send), SHA-256 `f8422345a70d815268286d6d3f529d047f4d0645f10d8e44eadc3ace620c71fb`:

- **P1** "Any recent papers on retrieval-augmented generation for code?"
- **P2** "What's the latest research on speculative decoding for large language models?"
- **P3** "Can you explain how the attention mechanism in transformers works?"

One attempt each, no retries, no repair after observing them. (A deterministic offline sanity check of the recognizer on these strings ran before freezing, without contacting VECTOR.) Fresh VECTOR started 2026-09-21T19:56:08.5Z, LISTENING 19:56:18.8Z. P1/P2 were sent immediately, **while the IntentMatcher was still prewarming** (0 of 499 embedded), to show independence from both the matcher and the classifier. P3 was sent later (20:06:10Z).

## 8. Complete P1 / P2 / P3 identity traces

| Stage | P1 | P2 | P3 |
|---|---|---|---|
| Owner text | recent papers, RAG for code | latest research, speculative decoding | timeless attention question |
| Stage-0 keyword | `respond` | `respond` | `respond` |
| Deterministic recognition | `paper_retrieval_topic` → "retrieval-augmented generation code" | → "speculative decoding large language models" | `None` |
| LLM classifier | **not consulted** | **not consulted** | consulted: `is_action=false`, conf 0.99 |
| Candidate / DecisionEngine | `Winner: search_arxiv (score=0.6694) over 0 alternatives` | `Winner: search_arxiv (score=0.6694)` | none (conversation fast path) |
| PermissionGateway | `search_arxiv classified as GREEN (proposed by api_command)` → `Executing search_arxiv` | same | not invoked |
| Dispatch | `dispatch task_1790020608 -> research (search_arxiv)` | `dispatch task_1790020617 -> research (search_arxiv)` | none |
| Retrieval | `[research_hub] ArXiv 'retrieval-augmented ': 5 papers` | `ArXiv 'speculative decoding': 5 papers` | no `search_arxiv` / `ArXiv` log line after P3 was sent |
| Response | `action_taken=search_arxiv`, `district=research`, `candidates_evaluated=1`, evidence-grounded | same | `action_taken=None`, ordinary explanation, no retrieval |
| Latency | 26.8 s | 8.9 s | 30.0 s |
| Verdict | **PASS** | **PASS** | **PASS** |

The identity is `search_arxiv` at Candidate, gateway evaluation, and dispatch, live (log lines above) and in unit test 9. Note for honesty: `create_content_from_research` and `proactive_*` lines appearing in the trace windows are autonomous-loop actions (proposed by the loop / anticipation engine), not caused by the probes; the probe responses themselves show `candidates_evaluated=1` / `action_taken=search_arxiv` (P1, P2) and `None` (P3).

## 9. Retrieval / evidence proof

Owner-facing responses (verbatim starts; full URLs retained):

- **P1:** "arXiv results retrieved just now (from the arXiv API, not from memory): 1) AutoRecLab: Describe the Experiment, Get the Code! — Moritz Baumgart, Philipp Meister, Justus Krell (2026-09-18) — http://arxiv.org/abs/2609.21863v1 | 2) Beyond Similarity through Zero-Token Geometric Graphs for Multi-Hop RAG — Zeliang Li, Xiaofen Xing, Kailing Guo (2026-09-17) — http://arxiv.org/abs/2609.19622v1 | 3) DriveMCP … (2609.17247v1) | 4) BioPhys-Bridge … (2609.19180v1) | 5) SpecLens: LLM-Based Verilog Generation … (2609.16729v1)"
- **P2:** "… 1) SpecQuant: Speculative Decoding with Multi-Parent Quantization for Adaptive LLM Inference — Harish KB, Jagadeeswaran M, Pradheep P (2026-09-18) — http://arxiv.org/abs/2609.21704v1 | 2) To Copy or Not to Copy: Controlling Speculative Decoding via Intrinsic Model Signals (2609.20186v1) | 3) A Calibrated Instrument for Measuring How Inference Optimizations Affect Output Quality (2609.18005v1) | 4) FlexEE: Self-Speculative and KV-Compatible Early Exiting … (2609.17008v1) | 5) GrowMTP: Can RL Grow Its Own Draft Head? (2609.16648v1)"

Every title, author, date and URL comes from the arXiv API response (log `ArXiv …: 5 papers` from the ResearchHub agent); nothing is LLM-generated (the conversational LLM was not called on P1/P2 — the renderer builds the text from the evidence). Relevance: P2 is clearly on-topic; P1 is on-topic for the first and last entries and looser for DriveMCP / BioPhys-Bridge (arXiv matches the AND'd terms anywhere in the abstract and results are date-sorted, §11 #2). Transport/HTTPS, query construction and renderer were proven in the previous mission and were not touched.

## 10. Final HEAD

Starting HEAD `3e859a123f2b97abcb3535790fb3ee4354e28d85`. The final HEAD is the single commit containing this report; a commit cannot embed its own hash, so it is printed in the Hard Stop summary (`git rev-parse HEAD`). Not pushed. VECTOR stopped; no listener on port 8000; no python processes.

## 11. Unresolved findings

1. **Matcher prewarm was degraded in this run (not addressed — explicitly out of scope).** After P1/P2 the prewarm logged 23+ `[IntentMatcher] Embedding failed: timed out` (10 s each) and had not completed after ~10 minutes; a failed embedding silently becomes a zero vector (existing design). A direct `ollama.Client.embeddings` call from a separate process at the same moment took 0.04 s, so the delay is inside the VECTOR process (cause unmeasured: candidates are executor/GIL contention with other startup work). It does not affect this closure — P1/P2/P3 do not depend on the matcher — but combined with the 261 s prewarm from the last mission it deserves its own bounded mission.
2. **arXiv ordering is newest-first, not relevance-ranked.** Results all match the AND'd terms but a few (P1 #3, #4) are only loosely related. Honestly labelled and evidence-grounded; not a correctness or security issue.
3. **Carried / not changed:** the deterministic recognizer is phrase-shaped (a paper request with no recency marker, no topic marker or an action verb still goes to the classifier path; a phrasing like "papers about X" without a recency word relies on the alias fold); the `/ws/command` surface only has the honest-decline floor for current-information requests and does not gain the new retrieval route (still fabrication-safe); JWT type confusion, 629 routable-but-permission-unregistered actions, `/command` reporting "Done" for `status: error` handlers.

## 12. RG-D2 readiness

The single bounded blocker from `PRE_RG_D2_FINAL_CLOSURE_REPORT.md` is closed: owner paper-retrieval reaches the real, permission-gated capability with real evidence and no dependence on the LLM classifier, and ordinary conversation / non-academic current-info requests are unaffected. RG-D2, JWT, the prewarm, goal progress, long-horizon autonomy and the bridge were not touched. Awaiting independent review; if accepted, the next action is **bridge connectivity verification**.
