# llm-council-master Audit

**Repo:** llm-council — Multi-LLM consensus voting framework (MIT)
**Audited:** 2026-06-02
**Verified:** `LLMCouncil OK` — VECTOR's council instantiates and is more advanced

---

## 1. Repo Reality

Python library for multi-LLM voting on decisions. Supports calling multiple LLM APIs, collecting responses, and synthesizing them via voting/aggregation. Configurable via YAML. Features: multi-provider, response aggregation, consensus scoring, CLI interface.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| Multi-LLM consensus voting | `districts/governance/llm_council.py` | LLMCouncil OK | ✅ |
| HP-gated council (700+ HP) | `can_vote_in_council()` in AgentBase | ✅ | ✅ |
| 3-stage deliberative process | `deliberate()`, `vote()`, `synthesize()` in LLMCouncil | ✅ | ✅ |
| Chairman role | `vector-chairman` (gemma4:31b) | ✅ | ✅ |
| ReasoningBank integration | `RULE 8` — all chains stored | ✅ | ✅ |
| CLI interface | VECTOR uses FastAPI + MCP instead | N/A | N/A |

---

## 3. Frontend: N/A

---

## 4. Verdict

**SAFE TO DELETE** — VECTOR's `LLMCouncil` is strictly more advanced: HP-gating, Darwinian member selection, 3-stage deliberation, ReasoningBank storage, per-decision cost tracking, and local Ollama inference. The reference repo has no features VECTOR lacks.

**Delete-readiness:** ✅ DELETE-NOW

---

## 5. Gaps: None
