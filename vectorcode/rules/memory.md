<!-- VECTOR-INGESTED ASSET
  Source: .claude/rules/memory.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
paths:
  - "core/memory/**/*.py"
  - "districts/d7/**/*.py"
  - "**/memory*.py"
  - "**/episodic*.py"
  - "**/semantic*.py"
---

# Memory Rules

## Import — Self-Hosted ONLY
```python
from mem0 import Memory          # ✅ self-hosted OSS
# from mem0 import MemoryClient  # ❌ NEVER — sends data to cloud (Rule 11)
```

## The 5 Tables — Never Rename
```sql
episodic_memory    -- FTS5 virtual table (what happened)
semantic_memory    -- preferences, facts, patterns
policy_memory      -- RL reward history
reasoning_chains   -- thought chains + training data
agent_history      -- all agent generations + ghost memories
```
Adding columns is OK. Renaming or dropping is a CRITICAL violation.

## Session Hydration
Every LLM call must be preceded by:
```python
context = session_hydration_prompt()
messages = [{"role": "system", "content": context}, ...]
```
Without hydration, VECTOR has amnesia. Rule 1.

## Ghost Memory on Agent Death
When an agent's HP reaches 0:
```python
ghost = extract_learnings(agent_history)
semantic_memory.store(f"ghost:{agent_id}", ghost)
# Never delete agent_history rows — only mark is_dead=1
```

## LightRAG Integration
- District 8 (Research) uses LightRAG for external knowledge
- Internal memories use SQLite FTS5 — never mix the two stores
- LightRAG graph is append-only during session; compact weekly

## Memory Write Pattern
```python
# Always tag source + confidence
memory.add(
    content="...",
    user_id="arghyadeep",
    metadata={"source": "episodic", "confidence": 0.9, "district": "d7"}
)
```
