# Repo Audit — LightRAG-main (HKUDS)

> Audited: 2026-06-01 · Repo: `GitHub/LightRAG-main` · pip name: `lightrag-hku` v1.4.16 (MIT)
> Method: read repo + grep VECTOR + attempt live run. **Brutally honest.**

**TL;DR:** LightRAG is a real, mature graph-RAG library. VECTOR has a *real wrapper* (`core/memory/obsidian_sync.py`) that calls `ainsert`/`aquery` with Ollama backends — the plumbing exists and is wired into ~50 districts via `ObsidianSync`. BUT: (1) `lightrag-hku` is **NOT in `requirements.txt`** — it's only present because it happens to be pip-installed in *global* site-packages (not the venv); (2) the session-hydration hook the tests assume (`ContextEngine.get_vault_context`) **does not exist** — a test references a method that was never written; (3) I **could not prove the insert→query loop actually runs** because the host's sockets are exhausted (WinError 10055) — every event loop + tiktoken download fails machine-wide right now.

---

## Section 1 — Repo Reality

LightRAG = entity/relation extraction → knowledge graph + vector store → dual-level (local+global) hybrid retrieval. Concrete features (counted):

| # | Feature | Evidence |
|---|---------|----------|
| 1 | **Entity + relation extraction** from documents via LLM | `lightrag/operate.py`, `prompt.py` |
| 2 | **Knowledge graph construction** (NetworkX default, append-only) | `lightrag/kg/networkx_impl.py` |
| 3 | **6 query modes**: `naive`, `local`, `global`, `hybrid`, `mix`, `bypass` | `lightrag/base.py:86` (`QueryParam.mode` Literal) |
| 4 | **Dual-level retrieval** (local = context-specific, global = themes) | README Fig 2; `operate.py` |
| 5 | **Incremental insert** (`ainsert`, dedup by content hash) | `lightrag.py` (4090 LOC) |
| 6 | **9 graph/vector storage backends**: NetworkX, Neo4j, Memgraph, Postgres(AGE), Milvus, Qdrant, Faiss, MongoDB, OpenSearch, Redis, nano-vectordb | `lightrag/kg/*.py` (15 impl files) |
| 7 | **Reranker support** (default for `mix` mode) | `lightrag/rerank.py` |
| 8 | **LightRAG Server** — FastAPI + Ollama-compatible chat endpoint | `lightrag/api/` |
| 9 | **WebUI** — React + Sigma.js graph viz, doc manager, retrieval tester | `lightrag_webui/src/` |
| 10 | **Multimodal context** (RAGAnything: PDF/image/audio) | `lightrag/multimodal_context.py` |
| 11 | **Chunking + pipeline orchestration** | `lightrag/chunker/`, `pipeline.py` |
| 12 | **Storage migrations** + atomic file writes | `storage_migrations.py`, `file_atomic.py` |
| 13 | **LLM provider adapters** (OpenAI, Ollama, Gemini, Azure, …) | `lightrag/llm/` |
| 14 | **Eval harness** (vs NaiveRAG/GraphRAG/HyDE) | `lightrag/evaluation/`, `reproduce/` |
| 15 | **20 runnable examples** | `examples/` |

**~15 distinct features.** This is a serious library (4090-LOC core), not a toy.

---

## Section 2 — VECTOR Parity (verification attempted by running)

### Is `lightrag` installed / vendored?

```
$ python -c "import lightrag; print(lightrag.__version__, lightrag.__file__)"
1.4.16  C:\Users\...\Python313\Lib\site-packages\lightrag\__init__.py
```

- **pip-installed: YES** (v1.4.16) — but in **GLOBAL Python site-packages, not VECTOR's `.venv`**.
- **In `requirements.txt`: NO.** `grep -in "rag" requirements.txt` → only `chromadb==1.5.8` and a *commented-out* `# OPTIONAL: rag-anything`. **`lightrag-hku` is undeclared.** If the venv is rebuilt from `requirements.txt`, LightRAG vanishes and every wrapper silently degrades.
- **Vendored: NO.** Nothing under `core/` or `districts/` contains the lightrag package; `core/memory/obsidian_sync.py:18` sets `_LIGHTRAG_PATH = districts/memory_curator` and `sys.path.insert`s it, but that dir only holds a *demo script*, not the package. The import resolves via the global pip install, not that path.

### Where does VECTOR use LightRAG?

**Real integration: `core/memory/obsidian_sync.py`** (the one true wrapper):
- `_init_rag()` (line 207) — constructs `LightRAG(working_dir, llm_model_func=ollama_model_complete, embedding_func=ollama_embed)`. Ollama-backed, local-first ✅ (RULE 11 compliant — no cloud).
- `_insert_to_rag()` → `rag.ainsert()` (line 256).
- `query(text, mode="hybrid")` → `rag.aquery(param=QueryParam(mode=mode))` (line 266).
- `ingest_existing()`, `ingest_file()`, `ingest_to_rag_anything()` — bulk + multimodal ingest with markitdown/RAGAnything fallback.
- Every failure path `logger.warning`s and returns `""`/`None` — **graceful degradation throughout** ✅.

`ObsidianSync` is imported and instantiated in **~50 districts** (research, reflection, finance, governance/llm_council, memory_curator, etc.) + `autonomous_loop.py:1356` + `mcp_server.py` (5 sites, incl. `search_vault` MCP tool). So the *object* is everywhere.

### Does the RAG pipeline actually RUN?

**Could not confirm — blocked by host environment, not by code.** Three independent run attempts all died at the same OS-level fault:

```
OSError: [WinError 10055] An operation on a socket could not be performed
because the system lacked sufficient buffer space or because a queue was full
```

- `asyncio.set_event_loop_policy(...)` + `socket.socketpair()` → 10055 (can't even create an event loop on this host right now).
- Synchronous `LightRAG(...)` construction → 10055 while tiktoken tried to download `o200k_base.tiktoken` from `openaipublic.blob.core.windows.net` (LightRAG fetches the encoding at init if not cached — a **network dependency at construction time**).

This is a **machine-wide socket exhaustion**, not a VECTOR/LightRAG bug. What I *could* verify statically:
- `from lightrag import LightRAG, QueryParam` ✅ importable.
- `LightRAG` has `ainsert` + `aquery` ✅.
- All 6 modes (`naive/local/global/hybrid/mix/bypass`) accepted by `QueryParam` ✅.

### The wiring gap (verified, code-level — not environmental)

`tests/test_obsidian_sync.py:88-91` asserts:
```python
from core.loop.context_engine import ContextEngine
ce = ContextEngine()
result = asyncio.run(ce.get_vault_context("VECTOR goals"))
```
But:
```
$ python -c "...; print(hasattr(ContextEngine(), 'get_vault_context'))"
has get_vault_context: False
```
**`ContextEngine.get_vault_context` does not exist.** `grep get_vault_context core/loop/context_engine.py` → no matches. So:
- The test that supposedly proves LightRAG→hydration wiring **would error** (AttributeError), not pass.
- **LightRAG retrieval is NOT injected into `session_hydration_prompt()`** — the whole point per RULE 1 / memory.md. VECTOR's hydration does not pull graph-RAG context.
- ConsolidationBot (`districts/memory_curator/consolidation_bot.py`) compresses memory via **raw LLM calls**, not LightRAG — `grep query/rag/lightrag` there finds nothing.
- The only file that calls `aquery` with real query loops is `districts/memory_curator/lightrag_ollama_demo.py` — a **standalone demo**, not part of the loop.

### Per-feature verdict

| Feature | Verdict |
|---------|---------|
| LightRAG importable | ✅ pip v1.4.16 (global, not venv) |
| Ollama-backed wrapper (`obsidian_sync`) | ✅ written, local-first, graceful |
| `ainsert` / `aquery` called by VECTOR | ⚠️ called in wrapper + demo; **not proven to run** (host sockets dead) |
| Wired into ~50 districts | ✅ object instantiated everywhere |
| Injected into session hydration | ❌ `get_vault_context` missing; not in hydration prompt |
| ConsolidationBot uses LightRAG | ❌ uses raw LLM, not graph-RAG |
| Declared in requirements.txt | ❌ undeclared (only chromadb is) |
| tiktoken cache for offline init | ⚠️ downloads encoding at init unless pre-cached |
| Storage backends (Neo4j/Postgres/etc.) | ⚠️ default NetworkX only; others unconfigured |
| WebUI / graph viz in VECTOR | ❌ not built |

**Counts: ✅ 4 · ⚠️ 4 · ❌ 5.**

**Bottom line:** the difference between "lightrag is pip-installed" and "VECTOR wires it into a working memory pipeline" is exactly where this falls down. The wrapper is real and good, but (a) the dependency is undeclared, (b) the hydration hook the tests assume is missing, and (c) I could not get a single live insert→query to complete on this host. It is **wired but unproven, and the headline use case (RAG-augmented hydration) is not actually connected.**

---

## Section 3 — Frontend (WebUI as a HUD panel spec)

LightRAG's WebUI (`lightrag_webui/src/features/`):

| Panel | What it does | Tech |
|-------|--------------|------|
| `GraphViewer.tsx` | Interactive KG: pan/zoom, force/circular/circlepack layouts, node-border, minimap, graph-search | **Sigma.js + graphology** (`@react-sigma/*`, 19 sigma deps) |
| `DocumentManager.tsx` | Upload/list/track ingestion status of docs | React + TanStack Table |
| `RetrievalTesting.tsx` | Live query box with mode selector (naive/local/global/hybrid/mix) → answer + retrieved context | — |
| `ApiSite.tsx` | Embedded API docs | — |
| `LoginPage.tsx` | Auth | Radix UI |

**HUD "Knowledge RAG" panel spec (if built for VECTOR dashboard):**
- **Layout:** left = force-directed entity graph (Sigma.js, node size by degree, edge weight by relation confidence); right-top = query box + mode dropdown; right-bottom = retrieved-context list with source note links.
- **Colors:** map to existing VECTOR HUD tokens — entity nodes by type (person/concept/project), edges muted, active-query path highlighted.
- **Data source:** `obsidian_sync.query()` (text) + a new `export_graph()` exposing the NetworkX graph as nodes/edges JSON.

**Worth building now? NO — defer.**
- VECTOR already has a **Code Graph panel from Understand-Anything** (`core/knowledge/`). A LightRAG graph panel is **complementary not duplicative** (code-structure graph vs. semantic-knowledge graph), but it is **premature**: the underlying pipeline isn't proven to run and isn't in hydration. **Fix the backend wiring first; a viz panel over an unconnected pipeline is decoration.**
- Per the "valuable frontends → panel now" rule: the *value* is gated on the RAG pipeline actually working. Until `get_vault_context` exists and a live query returns content, there is nothing meaningful to visualize.

---

## Section 4 — Verdict + Delete-Readiness

### Verdict: **DELETE-NOW (the clone) + PATCH (the wiring)**

LightRAG is a **pip dependency**, not something to vendor. The 4090-LOC core + WebUI + Docker stack in the GitHub clone is **redundant** — VECTOR consumes the library through `import lightrag`, never the repo tree.

**Tracker semantics:**
1. **The GitHub clone `GitHub/LightRAG-main/` → SAFE TO DELETE NOW.** VECTOR does not read from it. `_LIGHTRAG_PATH` points at `districts/memory_curator` (a VECTOR-owned demo dir), not at this clone. Deleting the clone changes nothing at runtime.
2. **The pip package `lightrag-hku` → KEEP** — but it must be **declared**.

### Required PATCHes (the real gaps — VECTOR code, do NOT auto-apply here, flagged for a follow-up task):

| Priority | Gap | Fix |
|----------|-----|-----|
| P0 | `lightrag-hku` undeclared in `requirements.txt` | Add `lightrag-hku>=1.4.16` (currently survives only via *global* site-packages — a venv rebuild silently kills all RAG). |
| P0 | `ContextEngine.get_vault_context` missing | Implement it (call `ObsidianSync().query(...)`) so the test passes and RAG context enters `session_hydration_prompt()` per RULE 1. Right now the test references a phantom method. |
| P1 | Insert→query loop unproven | Re-run `obsidian_sync` insert+query once the host's sockets recover (current WinError 10055 is environmental); pre-cache tiktoken `o200k_base` for offline init. |
| P2 | ConsolidationBot bypasses LightRAG | Wire semantic consolidation through the graph instead of raw LLM, if graph-RAG is meant to be the memory substrate. |

### Reasoning
The memory-index claim that "District 6/7 uses LightRAG and it's the upgraded RAG system" is **half true**: the wrapper is written and instantiated widely, but (a) the dependency isn't pinned, (b) it isn't connected to hydration (the missing `get_vault_context`), and (c) no live run was demonstrable on this host. So it's **closer to "scaffolded" than "shipped."** Delete the clone (zero risk), keep the pip package, declare it, and finish the two P0 wiring gaps.

---

## 5-Line Summary
1. **Features:** ~15 concrete (entity/relation extraction, KG, 6 query modes, 15 storage backends, incremental insert, server + Sigma.js WebUI, multimodal).
2. **pip-dep or vendored:** pip-installed `lightrag-hku` v1.4.16 (in **global** site-packages, **not the venv**, **NOT in requirements.txt**); not vendored.
3. **Does VECTOR use it working:** wrapper `core/memory/obsidian_sync.py` calls `ainsert`/`aquery` and is wired into ~50 districts — but the hydration hook `ContextEngine.get_vault_context` **doesn't exist**, ConsolidationBot bypasses it, and a live insert→query **could not be confirmed** (host WinError 10055 killed every event loop + tiktoken fetch). Scaffolded, not proven.
4. **Counts:** ✅ 4 · ⚠️ 4 · ❌ 5.
5. **Verdict:** **DELETE-NOW the GitHub clone** (redundant, zero runtime use) + **KEEP the pip package** + **PATCH** two P0 gaps (declare in requirements.txt; implement `get_vault_context` so RAG reaches session hydration).
