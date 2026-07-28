# VECTOR Evaluation Roadmap — LangSmith Native Evaluators

**Purpose:** move VECTOR's evals off the ad-hoc custom scorer in
`scripts/langsmith_vector_eval.py` and onto LangSmith's built-in evaluators
(the "Evaluators" page: Safety / Quality / Conversation / Trajectory / Image),
so results are repeatable, comparable across runs, and visible in the LangSmith
dashboard.

**How to attach a native evaluator (per LangSmith UI):**
Datasets & Experiments → open the target dataset → Experiments → add evaluator →
pick from the prebuilt list. Or attach as an *auto-evaluator rule* on the
`VECTOR-eval` tracing project so every new trace is scored automatically.

**Existing datasets in the account** (created by the custom script — reuse these):
`VECTOR tier1`, `VECTOR tier2`, `VECTOR tier3`, `VECTOR tier4`, plus the
memory/concurrency reports. Trace project: `VECTOR-eval`.

**Context that shapes priority:**
- 22 of 38 districts tested at the *conversational* layer only. 16 districts
  never tested. The *tool-execution* layer (does the real action happen) is
  tested for 0 districts — this is the biggest, highest-risk gap.
- VECTOR has real device access (phone/PC control, posting, file ops), so
  safety-critical action subsystems matter more than output polish.
- VECTOR is Hindi + English (Devanagari) — Language evaluator is not optional.

---

## Priority tiers (execute top-down)

### P0 — Trajectory / execution layer  (HIGHEST RISK, LARGEST GAP)
The part never tested: does VECTOR route to the right agent and actually do the
task, not just talk about it. This is where the stub-answer bug and the
injection-scan bypass were found — the routing layer is fragile.

| VECTOR target | Native evaluator | What it catches |
|---|---|---|
| Governor district routing (all 38 districts) | **Tool Selection** | wrong-district dispatch (the `_llm_classify` non-determinism) |
| Multi-step tasks (tier2/tier3 combos) | **Trajectory Accuracy** | illogical / wasteful action paths |
| Every request | **Task Completion** | agent "completed" without doing the work (the stub bug class) |
| Planned multi-step flows | **Plan Adherence** | agent deviates from its stated plan |

Datasets: build a **trajectory dataset** — inputs = requests that require a
specific district + a specific action, reference = expected district/tool +
expected end-state. Run against `/ws/command` with tracing on so the tool/route
spans are captured for these evaluators to read.

### P1 — Safety content  (device access = real-world consequences)
| VECTOR target | Native evaluator |
|---|---|
| Safety-refusal domains (malware, keylogger, unauthorized trade, exfiltration) | **Toxicity** |
| Advice/opinion domains (health, investment, relationships, news) | **Bias & Fairness** |
| Image/media/avatar output | **Explicit Content**, **Sensitive Imagery** |

### P2 — Reconfirm this session's fixes via native evaluators
Prove the fixes hold on the dashboard, not just my custom script.
| Fix | Native evaluator |
|---|---|
| Memory write→read (was 0.00 → 1.00) | **Knowledge Retention** |
| Premature-compliance "On it right away" | **Tone** |
| Fabrication-when-uncertain | **Hallucination** + **Correctness** |

### P3 — Output quality across the 22 tested + 16 untested districts
| VECTOR target | Native evaluator |
|---|---|
| Factual answers (research, news, science) | **Correctness**, **Hallucination** |
| Coding district output | **Code Checker** |
| Any Q&A | **Answer Relevance**, **Assertions** |
| Briefings / chief-of-staff | **Conciseness** |

### P4 — Conversation experience
| VECTOR target | Native evaluator |
|---|---|
| Hindi + English handling | **Language** (must confirm Devanagari, not romanized) |
| Full sessions | **User Satisfaction**, **Perceived Error** |
| Support-style requests | **Support Intent** |

---

## Coverage math
- **69 evaluation targets total** (38 district capabilities + 31 core subsystems).
- Done so far (~24): 22 districts conversationally + governor + memory.
- This roadmap's P0–P4 covers the district + conversational + trajectory surface.
- **Still needs a separate track (not native-evaluator-shaped):** the
  safety-critical *core subsystems* — permission_gateway, control/action layer,
  sandbox isolation, audit/merkle integrity, metering/budget. These need
  functional/integration tests, not LLM-judge evaluators. Track separately.

## Execution notes for the Sonnet session
1. Reuse the running VECTOR instance (restart via `RESTART_VECTOR_TASK.bat` only
   if code changed). Confirm `/status` is up before any run.
2. Native evaluators are LLM-as-judge → they consume LangSmith free-tier quota.
   Batch modestly; the free tier is 5,000 traces/mo and hard-gates at the cap.
3. For P0 you must capture tool/route spans — verify `@traceable` covers the
   governor dispatch path (`core/city/governor.py` dispatch) and provider calls,
   or the Tool Selection / Trajectory evaluators will have nothing to read.
4. Keep prompts JARVIS-grounded (personal-assistant, real domains) — not generic
   benchmark questions.
