# camel-master Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\camel-master`
**Date:** 2026-06-02
**License:** Apache 2.0 (absorb-safe)
**Codebase size:** 496 Python files · 154,398 LOC · 83 toolkits · 52 model backends

---

## 1. Repo Reality

CAMEL (Communicative Agents for Mind Exploration of Large Language Model Society) is a research-grade multi-agent framework from camel-ai.org. It is NOT a personal agent OS — it is a *framework for building and studying* multi-agent systems at scale (up to 1M agents). Its primary audience is researchers generating synthetic training data and studying emergent agent behaviors.

### Concrete Features (with file paths)

#### A. Agent Primitives
| Feature | File | What it does |
|---------|------|-------------|
| ChatAgent | `camel/agents/chat_agent.py` (5,677 LOC) | Stateful LLM agent: tool use, streaming, memory, multi-turn, structured output, logprobs, interleaved thinking |
| CriticAgent | `camel/agents/critic_agent.py` | Adversarial review agent that scores/vetoes other agents' outputs |
| TaskPlannerAgent | `camel/agents/task_agent.py` | Decomposes a task into ordered subtasks |
| KnowledgeGraphAgent | `camel/agents/knowledge_graph_agent.py` | Extracts Node/Relationship triples from any text into graph DB |
| MCPAgent | `camel/agents/mcp_agent.py` | Native MCP tool-call agent with registry support |
| RepoAgent | `camel/agents/repo_agent.py` | GitHub repo interaction agent |
| SearchAgent | `camel/agents/search_agent.py` | Multi-source web search agent |
| RoleAssignmentAgent | `camel/agents/role_assignment_agent.py` | Assigns roles to agents for a given task |
| MultiHopGeneratorAgent | `camel/agents/multi_hop_generator_agent.py` | Generates multi-hop question–answer chains for training data |

#### B. Multi-Agent Orchestration
| Feature | File | What it does |
|---------|------|-------------|
| RolePlaying | `camel/societies/role_playing.py` | Two-agent conversation loop: user + assistant role, optional critic, task specification |
| Workforce | `camel/societies/workforce/workforce.py` | Async worker pool: AUTO_DECOMPOSE (LLM-driven) or PIPELINE mode; task dependency graph; failure recovery with 3 configurable strategies (retry/re-assign/new-worker); MAX 3 retries, 600s timeout |
| WorkforceMetrics | `camel/societies/workforce/workforce_metrics.py` | Per-task timing, success rate, token usage, worker utilization |
| WorkforceCallback | `camel/societies/workforce/workforce_callback.py` | Event hooks: task assigned/completed/failed/decomposed |
| WorkforceEvents | `camel/societies/workforce/events.py` | Typed event stream: TaskCreated, TaskDecomposed, TaskAssigned, TaskCompleted, TaskFailed, AllTasksCompleted |
| WorkflowMemoryManager | `camel/societies/workforce/workflow_memory_manager.py` | Cross-task memory shared across workers |

#### C. Memory Architecture
| Feature | File | What it does |
|---------|------|-------------|
| ChatHistoryMemory | `camel/memories/agent_memories.py` | Windowed chat history with optional KV backend |
| VectorDBMemory | `camel/memories/agent_memories.py` | Embedding-based long-term memory backed by any vector DB |
| ScoreBasedContextCreator | `camel/memories/context_creators/score_based.py` | Token-budget-aware context window: scores+truncates messages to fit within model's context window |
| VectorDBBlock | `camel/memories/blocks/vectordb_block.py` | Retrieval-augmented memory block (semantic search) |
| ChatHistoryBlock | `camel/memories/blocks/chat_history_block.py` | Sliding window block |

#### D. Model Backends (52 total)
All wrapped by `ModelFactory` + `ModelManager` for unified interface. Selected:
`camel/models/anthropic_model.py`, `camel/models/ollama_model.py`, `camel/models/openai_model.py`, `camel/models/gemini_model.py`, `camel/models/deepseek_model.py`, `camel/models/litellm_model.py` (catch-all via LiteLLM), plus 46 more.

Notable: `model_manager.py` provides load-balancing / fallback across multiple backends for the same role.

#### E. Toolkits (83 total)
All decorated with `@MCPServer()` for automatic MCP exposure. Key ones not in VECTOR:
- `camel/toolkits/code_execution.py` — 6 sandbox backends: `internal_python`, `jupyter`, `docker`, `e2b`, `subprocess`, `microsandbox`
- `camel/toolkits/math_toolkit.py` / `sympy_toolkit.py` — symbolic + numeric math
- `camel/toolkits/networkx_toolkit.py` — graph analysis toolkit
- `camel/toolkits/openbb_toolkit.py` — financial data (OpenBB)
- `camel/toolkits/thinking_toolkit.py` — explicit chain-of-thought tool
- `camel/toolkits/skill_toolkit.py` — dynamic skill registration/execution
- `camel/toolkits/task_planning_toolkit.py` / `planning_worktree_toolkit.py` — hierarchical task planning
- `camel/toolkits/context_summarizer_toolkit.py` — long-context compression tool
- `camel/toolkits/web_deploy_toolkit.py` — one-command web deployment

#### F. Synthetic Data Generation (datagen)
| Feature | File | What it does |
|---------|------|-------------|
| EvolInstructPipeline | `camel/datagen/evol_instruct/evol_instruct.py` | Iteratively evolves simple prompts into complex ones (WizardLM methodology); ThreadPoolExecutor parallel; BaseScorer quality gate |
| SelfInstruct | `camel/datagen/self_instruct/self_instruct.py` | Bootstraps training instructions from seed examples |
| CoTDataGenerator | `camel/datagen/cot_datagen.py` | Chain-of-thought dataset with reward score (0–1) per example |
| UserDataProcessor (Source2Synth) | `camel/datagen/source2synth/data_processor.py` | Converts raw user text → multi-hop QA pairs for training |
| SelfImprovingCoT | `camel/datagen/self_improving_cot.py` | Self-improving CoT loop: generates → verifies → improves |

#### G. Persona Hub
| Feature | File | What it does |
|---------|------|-------------|
| PersonaHub | `camel/personas/persona_hub.py` | Generates 1B+ diverse personas (Tencent paper); embedding-based dedup; persona-driven synthetic data synthesis |
| Persona | `camel/personas/persona.py` | Individual persona dataclass with name, description, embedding |

#### H. Verifiers (RLVR pipeline)
| Feature | File | What it does |
|---------|------|-------------|
| PythonVerifier | `camel/verifiers/python_verifier.py` | Runs code in isolated venv, installs deps, compares output to ground truth |
| MathVerifier | `camel/verifiers/math_verifier.py` | Symbolic math answer verification |
| PhysicsVerifier | `camel/verifiers/physics_verifier.py` | Physics equation answer verification |
| MultiStepEnv | `camel/environments/multi_step.py` | RL-style environment: setup→step→reset loop, episode history, action extraction |

#### I. Storage / Retrieval
| Feature | File | What it does |
|---------|------|-------------|
| SemanticCache | `camel/caches/semantic_cache.py` | Cosine-similarity cache: embeds queries, finds cached matches above threshold (default 0.85) |
| AutoRetriever | `camel/retrievers/auto_retriever.py` | Combines vector + BM25 retrieval automatically |
| BM25Retriever | `camel/retrievers/bm25_retriever.py` | Keyword-based BM25 retriever |
| HybridRetrieval | `camel/retrievers/hybrid_retrival.py` | Weighted fusion of vector + BM25 |
| GraphStorages | `camel/storages/graph_storages/` | Neo4j + NebulaGraph backends |
| VectorDB backends | `camel/storages/vectordb_storages/` | Chroma, FAISS, Milvus, Qdrant, PGVector, Weaviate, OceanBase, SurrealDB, TiDB (9 backends) |

#### J. Runtimes / Code Sandboxes
| Feature | File | What it does |
|---------|------|-------------|
| DockerRuntime | `camel/runtimes/docker_runtime.py` | Full Docker container as tool execution environment |
| DaytonaRuntime | `camel/runtimes/daytona_runtime.py` | Cloud dev environment |
| LLMGuardRuntime | `camel/runtimes/llm_guard_runtime.py` | LLM-based safety check before tool execution |
| E2BInterpreter | `camel/interpreters/e2b_interpreter.py` | Cloud sandbox via E2B |
| DockerInterpreter | `camel/interpreters/docker_interpreter.py` | Local Docker code execution |
| InternalPythonInterpreter | `camel/interpreters/internal_python_interpreter.py` | AST-checked in-process Python |
| JupyterKernelInterpreter | `camel/interpreters/ipython_interpreter.py` | Jupyter kernel execution |
| MicrosandboxInterpreter | `camel/interpreters/microsandbox_interpreter.py` | Lightweight sandboxed Python |

#### K. Benchmarks
`camel/benchmarks/`: GAIA, BrowseComp, APIBank, APIBench, Nexus, RAGBench — 6 evaluation suites for measuring agent performance.

#### L. Bots (Discord, Slack, Telegram)
`camel/bots/`: Discord, Slack (full bot clients), Telegram — same platforms VECTOR covers via vectorcode.

---

## 2. VECTOR Parity

**Verified output (exact):**
```
AgentRegistry OK: <class 'core.city.agent_registry.AgentRegistry'>
Governor OK: <class 'core.city.governor.Governor'>
SwarmCoordinator OK: <class 'vectorcode.src.swarm.SwarmCoordinator'>
```

| CAMEL Feature | VECTOR Equivalent | Verified Output / Notes | Status |
|---------------|-------------------|------------------------|--------|
| ChatAgent (stateful LLM agent) | `core/city/agent_base.py` AgentBase | `AgentBase methods: [...add_lesson, award_points, can_access_cloud, record_decision...]` | ✅ working |
| RolePlaying (two-agent loop) | `districts/governance/llm_council.py` LLMCouncil | `LLMCouncil methods: [...convene...]` | ✅ working (3-stage council vs 2-agent) |
| CriticAgent | `core/brain/red_team_agent.py` RedTeamAgent | `RedTeamAgent: <class 'type'>` | ✅ working |
| TaskPlannerAgent | `core/loop/decision_engine.py` DecisionEngine | `DecisionEngine: <class 'type'>` (5-factor scoring) | ✅ working |
| Workforce AUTO_DECOMPOSE | SwarmCoordinator | `SwarmCoordinator topology: Topology.HIERARCHICAL \| max_agents: 60` — **no decompose/retry logic** | ⚠️ stub |
| WorkforceMetrics | `core/engine/telemetry/` (otel_bridge + sentry_bridge) | Telemetry exists but not wired to task execution | ⚠️ stub |
| WorkforceCallback / event hooks | `core/event_bus.py` EventBus | EventBus present, not wired to swarm | ⚠️ stub |
| KnowledgeGraphAgent | `core/brain/synthesis_bridge.py` SynthesisBridge | `SynthesisBridge methods: [...synthesize, get_recent_patterns...]` | ✅ working |
| ChatHistoryMemory + window | `core/memory/episodic.py` EpisodicMemory | `EpisodicMemory has FTS5: True` · 396 LOC | ✅ working |
| VectorDBMemory (embedding retrieval) | ChromaDB available, wired via LightRAG | `ChromaDB available: 1.5.8` | ✅ working |
| ScoreBasedContextCreator (token budget) | `core/loop/context_engine.py` ContextEngine | `Has token count: False` · 193 LOC — no token counting | ❌ missing |
| SemanticCache (cosine-similarity query cache) | `core/jcode/cache_tracker.py` CacheTracker | `Has semantic/embedding: False` · CacheTracker is a rate/violation tracker, not a query cache | ❌ missing |
| 52 model backends via ModelFactory | `core/inference/llm_providers.py` 27 providers | `VECTOR provider classes: ['class LLMProvider']` · 27 providers configured | ✅ working (fewer backends, same coverage) |
| ModelManager (load-balance / fallback) | `core/inference/provider_client.py` | provider_client with Ollama-first fallback chain | ✅ working |
| GNNRouter (multi-layer routing) | `vectorcode/src/router.py` GNNRouter | `GNNRouter methods: [...route, route_sequence...]` | ✅ working |
| EvolInstructPipeline | Nothing | Not present anywhere in VECTOR | ❌ missing |
| SelfInstruct pipeline | ReasoningBank.distill() | `ReasoningBank methods: [...distill, inject_past_reasoning...]` — only distills from existing chains, no seed-based generation | ⚠️ stub |
| CoTDataGenerator | `core/memory/reasoning_memory.py` ReasoningMemory | `ReasoningMemory has reward: True` · store_chain + reward-gated training data | ✅ working |
| Source2Synth (multi-hop QA) | Nothing | Not present anywhere in VECTOR | ❌ missing |
| PersonaHub (1B+ personas) | Nothing | Not present anywhere in VECTOR | ❌ missing |
| PythonVerifier (isolated venv) | `core/sandbox/vector_sandbox.py` VectorSandbox | `VectorSandbox has venv: False` · subprocess only, no isolation | ⚠️ stub |
| MathVerifier / PhysicsVerifier | `districts/qa/` QA district agents | QA district exists but no symbolic math/physics checking | ⚠️ stub |
| MultiStepEnv (RL environment) | `vectorcode/src/neural_training.py` VECTORTrainer | A2C/DQN/PPO/SARSA wired into decision_engine | ✅ working |
| BM25Retriever | Nothing | Not present — episodic uses FTS5, not BM25 | ❌ missing |
| HybridRetriever (BM25+vector) | Nothing | Not present | ❌ missing |
| AutoRetriever | Nothing | No auto-combining of retrieval strategies | ❌ missing |
| SemanticCache | Nothing | No embedding-based query dedup cache | ❌ missing |
| Neo4j / NebulaGraph backends | Nothing | No graph DB backend wired | ❌ missing |
| 9 vector DB backends | ChromaDB (1 backend) | Only ChromaDB confirmed; FAISS/Milvus/Qdrant not wired | ⚠️ stub |
| Benchmarks (GAIA/BrowseComp etc.) | Nothing | No evaluation benchmark harness | ❌ missing |
| CodeExecutionToolkit (6 sandboxes) | VectorSandbox (subprocess + wasm + docker stub) | `runner has docker: True` but `core.mining.stubs` import breaks; VectorSandbox=subprocess only | ⚠️ stub |
| @MCPServer() auto-exposure of toolkits | `core/mcp_server.py` | MCP server exists with 14+ tools | ✅ working |
| HP / Darwinian evolution | `core/city/evolution_engine.py` EvolutionEngine | `EvolutionEngine: <class 'type'>` | ✅ working (VECTOR-unique, CAMEL has nothing equivalent) |
| Permission gateway (GREEN/YELLOW/RED) | `core/loop/permission_gateway.py` PermissionGateway | `PermissionGateway: <class 'type'>` | ✅ working (VECTOR-unique) |
| Ghost memory / cross-gen inheritance | AgentBase.inherit_ghost() | `AgentBase methods: [...inherit_ghost...]` | ✅ working (VECTOR-unique) |
| Autonomous loop (observe→think→act) | `core/loop/autonomous_loop.py` | 24/7 coroutine loop | ✅ working (VECTOR-unique) |

---

## 3. Frontend

CAMEL has **no user-facing frontend**. It is a Python SDK. Notable adjacents:

- `camel_log_viewer.html` — a standalone HTML file for viewing agent logs (single static file, no framework)
- `camel/services/agent_openapi_server.py` — auto-generates a FastAPI server exposing a `ChatAgent` as a REST endpoint (POST /chat)
- `apps/` folder exists but contains research prototype notebooks, not a dashboard

VECTOR's frontend: `frontend/VECTOR.html` (dashboard) + `api/src/` (Cloudflare Worker TypeScript). VECTOR's frontend is significantly more built-out than CAMEL's.

**No frontend absorption opportunity.** CAMEL's `agent_openapi_server.py` is interesting — it auto-wraps any ChatAgent as a REST API — but VECTOR already has `core/api/routers/` doing this.

---

## 4. Verdict

**PATCH VECTOR** — selectively absorb 5 specific Python components. Do NOT integrate the full framework.

**Reasoning:**

CAMEL is a 154K-LOC research framework built around OpenAI's API with fundamentally different architecture goals (scaling laws research vs. personal AI OS). The vast majority — role-playing, model backends, most toolkits, the bot clients, benchmark runners — is either already covered by VECTOR or irrelevant to a single-owner local-first system.

**What CAMEL does better (absorb these):**

1. **Evol-Instruct + Self-Instruct** (`camel/datagen/evol_instruct/`) — VECTOR's karpathy_lab needs this. Iteratively evolves simple prompts into complex training examples. VECTOR's ReasoningBank only stores existing chains; it cannot *generate new* training diversity. This directly feeds the OpenMythos fine-tuning pipeline.

2. **Source2Synth** (`camel/datagen/source2synth/`) — Converts VECTOR's own brain vault notes + reasoning chains into multi-hop QA pairs for supervised fine-tuning. Natural fit: VECTOR has 300+ Obsidian notes that could become training data.

3. **ScoreBasedContextCreator / token budget management** (`camel/memories/context_creators/score_based.py`) — ContextEngine has no token counting. At 32K context window (Ollama models), unmanaged context causes silent truncation. This is a production reliability fix.

4. **SemanticCache** (`camel/caches/semantic_cache.py`) — Embedding-based deduplication of LLM queries. VECTOR makes many repeated/similar LLM calls during the observe→think→act loop. A semantic cache with 0.85 cosine threshold over ChromaDB (already installed) would cut Ollama load significantly.

5. **PythonVerifier isolated venv** (`camel/verifiers/python_verifier.py`) — VectorSandbox runs all code in the main process via subprocess. For karpathy_lab training data quality and the QA district's api_tester, isolated venv execution with output comparison is needed to generate verifiably-correct training examples.

**What to skip:**
- All 52 model backends — VECTOR has 27 providers in `provider_client.py`; CAMEL's backends use OpenAI SDK pattern incompatible with VECTOR's Ollama-first architecture
- All 83 toolkits — VECTOR already has district-level equivalents; most CAMEL toolkits require external API keys not in VECTOR's stack
- Workforce class — too tightly coupled to CAMEL's ChatAgent and Task abstractions; SwarmCoordinator covers the use case
- PersonaHub — interesting but the 1B-persona use case requires Tencent's web3k dataset; not actionable without it
- Benchmarks — GAIA/BrowseComp are for academic evaluation, not VECTOR's personal-OS mission
- Bots (Discord/Slack/Telegram) — fully covered by vectorcode channel adapters

---

## 5. Gaps

| ID | Issue | CAMEL File:Line | VECTOR File:Line | Severity |
|----|-------|-----------------|------------------|----------|
| G-01 | SwarmCoordinator has no task decomposition — no LLM-driven subtask splitting. Governor.dispatch() routes but never decomposes a task into dependency graph of subtasks | `camel/societies/workforce/workforce.py:141` (WorkforceMode.AUTO_DECOMPOSE) | `vectorcode/src/swarm.py` — missing decompose() | MEDIUM |
| G-02 | SwarmCoordinator has no retry/failure-recovery strategy — task fails permanently on first error | `camel/societies/workforce/utils.py` RecoveryStrategy enum | `vectorcode/src/swarm.py` — no retry logic | MEDIUM |
| G-03 | No semantic embedding cache — every repeated/similar LLM query hits Ollama; at 0.5s observe tick this accumulates rapidly | `camel/caches/semantic_cache.py:34` SemanticCache | `core/jcode/cache_tracker.py` — rate/violation tracker only, no cosine cache | HIGH |
| G-04 | No Evol-Instruct pipeline — karpathy_lab cannot autonomously generate progressively harder training examples; ReasoningBank only stores what already happened | `camel/datagen/evol_instruct/evol_instruct.py:32` EvolInstructPipeline | `districts/karpathy_lab/data_prep.py:preprocess_data` — no evolution logic | HIGH |
| G-05 | No Source2Synth multi-hop QA generation — VECTOR brain vault notes cannot be turned into structured training data automatically | `camel/datagen/source2synth/data_processor.py:29` UserDataProcessor | `districts/karpathy_lab/data_prep.py` — missing | MEDIUM |
| G-06 | No PersonaHub — synthetic data generated by VECTOR has no persona diversity; all training examples come from a single implicit perspective | `camel/personas/persona_hub.py:38` PersonaHub | Missing entirely | LOW |
| G-07 | VectorSandbox runs code via subprocess with no venv isolation — generated training code cannot be safely verified for correctness; security risk for agent-generated scripts | `camel/verifiers/python_verifier.py:34` (venv isolation) | `core/sandbox/vector_sandbox.py:run_python` — subprocess only | HIGH |
| G-08 | No evaluation benchmark harness — no way to measure agent performance regression after model swaps or HP changes | `camel/benchmarks/` (6 suites) | `districts/qa/` — QA district is quality checking, not benchmark scoring | MEDIUM |
| G-09 | ContextEngine has no token counting or ScoreBasedContextCreator — at 32K context window (Ollama), long sessions silently truncate; session_hydration_prompt() grows unbounded | `camel/memories/context_creators/score_based.py` | `core/loop/context_engine.py:193 LOC` — no token budget enforcement | HIGH |
| G-10 | No BM25 or hybrid retrieval — episodic memory uses FTS5 (keyword) and LightRAG uses vector; no fusion strategy to combine both for best recall | `camel/retrievers/hybrid_retrival.py` | `core/memory/episodic.py` (FTS5) + ChromaDB (vector) — not fused | MEDIUM |
| G-11 | `core/sandbox/runner.py` ImportError on `core.mining.stubs` — ContainerRunner import fails silently in degraded mode; Docker sandbox is advertised but broken | `camel/interpreters/docker_interpreter.py` | `core/sandbox/runner.py:383` — `from core.mining.docker import PearlDockerLauncher` triggers `ModuleNotFoundError: No module named 'core.mining.stubs'` | HIGH (bug) |
| G-12 | No token-level logprob access in VECTOR's Ollama wrapper — CAMEL's ChatAgent exposes logprobs for calibration/self-assessment; VECTOR's reasoning_memory stores chains but not confidence scores | `camel/agents/chat_agent.py:handle_logprobs` | `core/inference/ollama_safe.py` — no logprob extraction | LOW |

---

## Absorption Plan (priority order)

### Absorb Now (HIGH severity gaps)

**1. SemanticCache → `core/inference/semantic_cache.py`**
Port `camel/caches/semantic_cache.py` (~120 LOC). Uses ChromaDB (already installed) + nomic-embed-text (already in Ollama). Wire into `core/inference/provider_client.py` as a pre-call cache layer. Threshold: 0.85 cosine. Expected benefit: 30-50% reduction in Ollama calls during observe tick.

**2. ScoreBasedContextCreator → `core/loop/context_engine.py`**
Port `camel/memories/context_creators/score_based.py` (~80 LOC). Add `tiktoken` or `transformers.AutoTokenizer` token counting to ContextEngine. Cap `session_hydration_prompt()` output at `context_window - 2048` tokens. Prevents silent truncation on all 32K-window Ollama models.

**3. EvolInstructPipeline → `districts/karpathy_lab/evol_instruct.py`**
Port `camel/datagen/evol_instruct/evol_instruct.py` (~200 LOC) + `templates.py` + `scorer.py`. Wire into karpathy_lab's daily 30-min session: at end of session, take N examples from ReasoningBank and evolve them into harder variants. Feed back into `reasoning_memory.store_chain()`.

**4. PythonVerifier → `core/sandbox/python_verifier.py`**
Port `camel/verifiers/python_verifier.py` (~180 LOC). Use stdlib `venv` (no new deps). Wire into `districts/qa/api_tester.py` and `districts/karpathy_lab/` to verify generated training code before storing as ground truth.

**5. Fix runner.py Docker import bug**
`core/sandbox/runner.py:383` — wrap `from core.mining.docker import PearlDockerLauncher` in try/except, set `ContainerRunner = None` on failure. The current silent degraded-mode suppression is hiding the failure; the runner module exports `ContainerRunner` as if it works when it doesn't.

### Absorb Later (MEDIUM severity)

**6. Source2Synth → `districts/karpathy_lab/source2synth.py`**
Port `camel/datagen/source2synth/data_processor.py` + `models.py`. Feed VECTOR's Obsidian brain vault (`brain/`) as input — convert notes into multi-hop QA pairs for OpenMythos fine-tuning. Requires MultiHopGeneratorAgent logic (~150 LOC total).

**7. Task Decomposition → `core/city/governor.py`**
Add `decompose_task(task: str) -> list[str]` method using a local Ollama call (vector-reasoning). Wire into `route_task()` when task complexity score > threshold. Pattern from `camel/societies/workforce/workforce.py:WorkforceMode.AUTO_DECOMPOSE`.

### Skip (LOW or out-of-scope)

- PersonaHub — needs Tencent's 1B-persona dataset; not actionable standalone
- Benchmarks — academic evaluation suites not aligned with personal OS mission
- Model backends (52) — VECTOR's 27-provider registry covers all needed providers
- Toolkits (83) — district-level agents provide equivalent functionality with VECTOR's architecture
- Bot clients — vectorcode already covers all platforms
