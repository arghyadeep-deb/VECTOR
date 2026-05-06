# ObsidianSync — Design Spec
**Date:** 2026-05-07  
**Status:** Approved  
**Gate:** T6.1 / Day 6 — "Obsidian note" requirement

---

## 1. Problem

VECTOR needs a bidirectional bridge to the Obsidian vault at
`C:/Users/Arghyadeep/V.E.C.T.O.R Brain`. Two problems to solve:

1. **Write** — VECTOR must autonomously produce notes (reflections, HP logs,
   council decisions, research summaries) and write personal notes on demand.
2. **Read** — VECTOR must build a context-mature understanding of vault
   content so `session_hydration_prompt()` can include relevant knowledge —
   not fuzzy embedding matches but causally correct entity-relationship context.

Plain vector similarity (ChromaDB dot-product) is rejected: it connects
semantically adjacent but wrong concepts and returns verbose raw chunks.
LightRAG knowledge graph solves both problems.

---

## 2. Architecture

### 2.1 Two-Layer Memory (no overlap)

```
Layer 1 — LightRAG Knowledge Graph
    What:  vault .md notes, on-demand PDFs/images via RagAnything
    Where: ./data/lightrag_vault/   (persisted, append-only during session)
    LLM:   vector-reasoning (Ollama local) for entity/relation extraction
    Embed: nomic-embed-text (Ollama local, 768-dim)
    Query: mode="hybrid" (local entity + global community) → compact structured context
    Use:   ContextEngine.get_vault_context(query) before LLM calls needing vault knowledge

Layer 2 — SQLite FTS5 Episodic Memory  (already built, unchanged)
    What:  VECTOR's own actions, decisions, HP events, loop ticks
    These never enter LightRAG. Internal state ≠ external knowledge.
```

### 2.2 Module: `core/memory/obsidian_sync.py`

`ObsidianSync` is a plain class (not AgentBase). It is a core memory service,
not a city agent — it has no HP, no district, and no Darwinian lifecycle.
The agents that USE it (ConsolidationBot, PatternFinder) are AgentBase subclasses.

```
ObsidianSync
│
├── write_note(title, content, folder, tags, overwrite=False) → Path
│     - Resolves target path, checks write permission for folder
│     - GREEN folders: execute immediately
│     - YELLOW folders (personal, new note): execute + notify via gateway
│     - RED folders (personal, overwrite existing): await confirmation via gateway
│     - Protected folders / files: raise PermissionError, never write
│     - Atomic write: write to .tmp → os.replace() → final path
│     - Prepends YAML frontmatter: date, tags, source: vector, type
│
├── append_to_note(title, content, folder) → bool
│     - Appends a timestamped block to existing note
│     - Same permission rules as write_note
│     - Creates note if missing (uses write_note path)
│
├── start_watching() → async coroutine (never crashes)
│     - watchdog ObservedHandler on vault_path
│     - Events queued with 30s debounce per file
│     - On dequeue: read .md → rag.ainsert(content) + episodic_memory.store(event)
│     - Skips protected files and hidden/system files
│     - Runs until self._running = False
│
├── ingest_existing(folder=None) → int
│     - One-shot bulk ingest at startup
│     - Walks folder (or entire vault if None)
│     - Skips already-ingested files (hash-checked via semantic_memory)
│     - Returns count of newly ingested files
│
├── query(text, mode="hybrid") → str
│     - Wraps rag.aquery(text, param=QueryParam(mode=mode))
│     - Returns structured context string for LLM prepend
│
└── ingest_to_rag_anything(file_path) → bool  (on-demand, called by research district)
      - Handles PDFs, images, audio → same LightRAG graph
      - Uses RagAnything from rag_anything/ (already embedded)
```

### 2.3 CONFIG additions (`core/config.py`)

```python
"obsidian": {
    "vault_path": "C:/Users/Arghyadeep/V.E.C.T.O.R Brain",  # mirrors vault_path
    "lightrag_working_dir": "./data/lightrag_vault",
    "watch_debounce_sec": 30,
    "ingest_on_startup": True,
    "protected_paths": [
        "CLAUDE.md", "GOALS.md", "VECTOR/", "graphify-out/", ".obsidian/"
    ],
    "vector_write_folders": [
        "Daily", "Reflections", "Council", "Agent HP", "Research", "Interviews"
    ],
    "personal_write_folders": [
        "00 Notes", "01 Journals", "02 Projects", "03 Reviews", "04 Skills", "wiki"
    ],
}
```

`permission.yellow` gains: `"write_note_personal"`
`permission.red` gains: `"overwrite_note_personal"`

### 2.4 LightRAG Configuration

```python
LightRAG(
    working_dir="./data/lightrag_vault",
    llm_model_func=ollama_model_complete,
    llm_model_name=CONFIG["models"]["reasoning"],   # vector-reasoning
    embedding_func=EmbeddingFunc(
        embedding_dim=768,
        max_token_size=8192,
        func=lambda texts: ollama_embed(texts, embed_model="nomic-embed-text"),
    ),
)
```

### 2.5 Write Permission Matrix

| Target folder | Auto (VECTOR) | On demand (owner asks) | Level |
|---------------|:---:|:---:|-------|
| `Daily/` `Reflections/` `Council/` `Agent HP/` `Research/` `Interviews/` | ✅ | ✅ | GREEN |
| `00 Notes/` `01 Journals/` `02 Projects/` `03 Reviews/` `04 Skills/` `wiki/` | ❌ | ✅ new note | YELLOW |
| `00 Notes/` … (overwrite existing) | ❌ | ✅ with confirm | RED |
| `CLAUDE.md` `GOALS.md` `VECTOR/` `graphify-out/` | ❌ | ❌ | FORBIDDEN |

### 2.6 Note Format

```markdown
---
date: 2026-05-07T02:00:00+00:00
tags: [vector, reflection, daily]
source: vector
type: reflection
---

# Daily Reflection — 2026-05-07

[content]
```

### 2.7 Integration Points

**`core/loop/context_engine.py`**
- Add `_get_obsidian()` lazy loader
- Add `get_vault_context(query: str) -> str` method
- Called in `session_hydration_prompt()` when query is non-trivial
- Returns `""` gracefully if LightRAG not yet initialised

**`core/loop/autonomous_loop.py`**
- New `obsidian_loop()` coroutine added to `run_forever()`
- Calls `obsidian_sync.start_watching()` — runs for lifetime of loop
- Calls `obsidian_sync.ingest_existing()` once at startup (background, non-blocking)

**`core/loop/permission_gateway.py`**
- Add `write_note_personal` to YELLOW list
- Add `overwrite_note_personal` to RED list

---

## 3. Data Flow

```
Vault .md changes (watchdog)
    → 30s debounce queue
    → LightRAG.ainsert(content)          [entity/relation extraction, local model]
    → episodic_memory.store(event_type="vault_change", ...)

VECTOR writes note
    → ObsidianSync.write_note(...)
    → PermissionGateway.execute(Action)
    → atomic write to vault
    → LightRAG.ainsert(new content)      [self-ingests immediately]
    → episodic_memory.store(event_type="vault_write", ...)

LLM call (any module)
    → session_hydration_prompt()
    → context_engine.get_vault_context(recent_query)
    → LightRAG hybrid query → structured context string
    → prepended to LLM message
```

---

## 4. Error Handling

- LightRAG init failure → log warning, `query()` returns `""` gracefully, writes still work
- Watchdog crash → `start_watching()` catches all exceptions, sleeps 5s, restarts
- Write failure → raise, let caller handle (gateway logs it)
- Disk full → catch `OSError`, log critical, skip
- nomic-embed-text unavailable → LightRAG degrades to keyword-only graph (still works)

---

## 5. Testing

Each method has a `__main__` smoke test:
- `write_note()` → file exists, frontmatter parseable, `.tmp` file absent
- `append_to_note()` → file grew, new block present
- `start_watching()` → create test .md → assert ingested within 35s
- `ingest_existing()` → returns count > 0 on real vault
- `query()` → returns non-empty string for known vault content
- Gateway integration → personal folder write fires YELLOW notification

---

## 6. Files Changed

| File | Action |
|------|--------|
| `core/memory/obsidian_sync.py` | Implement (was stub) |
| `core/loop/context_engine.py` | Add `get_vault_context()` + `_get_obsidian()` |
| `core/loop/autonomous_loop.py` | Add `obsidian_loop()` coroutine |
| `core/loop/permission_gateway.py` | Add `write_note_personal`, `overwrite_note_personal` to permission lists |
