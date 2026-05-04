---
name: rag-engineer
description: Expert in RAG systems — embeddings, vector search, chunking, LightRAG. Use when building VECTOR's memory_curator district, wiring LightRAG, or improving episodic memory retrieval quality.
risk: safe
source: sickn33/antigravity-awesome-skills (Apache 2.0)
---

# RAG Engineer

Expert in building Retrieval-Augmented Generation systems. Masters embedding models, vector databases, chunking strategies, and retrieval optimization.

## Use this skill when

- Building `agents/districts/memory_curator/` (T6)
- Wiring LightRAG into VECTOR's episodic memory
- Improving `inject_past_reasoning()` retrieval quality
- Setting up `nomic-embed-text` for semantic search over memories
- Optimizing chunking for Obsidian vault ingestion

## VECTOR RAG Stack

```
nomic-embed-text (Ollama)   — vector embeddings, local only
chromadb                    — vector store (phase 1)
lightrag                    — upgraded RAG, replaces chromadb-only (T6)
FTS5 (SQLite)               — keyword search in episodic_memory table
hybrid = FTS5 + chromadb    — best retrieval for VECTOR memories
```

## Key Patterns

### Hybrid Search (VECTOR standard)
```python
# FTS5 for keyword matching (already in episodic.py)
results_kw = conn.execute(
    "SELECT * FROM episodic_memory WHERE episodic_memory MATCH ?",
    (query,)
).fetchall()

# Vector similarity for semantic matching
results_sem = chroma_collection.query(query_embeddings=[embed(query)], n_results=10)

# Reciprocal Rank Fusion to merge
def rrf(kw_results, sem_results, k=60):
    scores = {}
    for rank, r in enumerate(kw_results):
        scores[r['id']] = scores.get(r['id'], 0) + 1/(k + rank + 1)
    for rank, r in enumerate(sem_results):
        scores[r['id']] = scores.get(r['id'], 0) + 1/(k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])
```

### Semantic Chunking for Obsidian
- Split on `## ` headers (Obsidian structure)
- Preserve frontmatter as metadata
- Include 1 sentence overlap between chunks
- Index file path + creation date as metadata for filtering

### LightRAG Integration (T6)
```python
from lightrag import LightRAG, QueryParam
rag = LightRAG(working_dir="./vector_lightrag")
rag.insert(text)
result = rag.query("query", param=QueryParam(mode="hybrid"))
```

## Sharp Edges

- **Fixed-size chunking** breaks sentences → use semantic boundaries
- **No metadata filtering** → returns wrong-era memories → always filter by tags/date
- **Same embedding for all content** → code needs code-specific embeddings (nomic is general)
- **No retrieval evaluation** → can't diagnose poor memory quality → benchmark recall@K

## When to Use
- Building memory_curator district (T6)
- Wiring LightRAG to episodic memory
- Improving `inject_past_reasoning()` in reasoning_memory.py
- Obsidian vault sync and ingestion (T7)
