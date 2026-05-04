---
name: lightrag-integration
description: Use when writing any code that reads from or writes to VECTOR's memory system (District 7). Triggers on: "memory", "LightRAG", "remember", "recall", "knowledge graph", "RAG query", "insert knowledge"
---

# LightRAG Integration (District 7)

## Install
```bash
pip install "lightrag-hku[api]"
```

## Core API
```python
from lightrag import LightRAG, QueryParam
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.utils import EmbeddingFunc

# Initialise once per district
rag = LightRAG(
    working_dir="./memory/district_N",
    llm_model_func=ollama_model_complete,
    llm_model_name="vector-focus",        # gemma4:e4b — permanent in VRAM
    embedding_func=EmbeddingFunc(
        embedding_dim=768,
        max_token_size=8192,
        func=lambda texts: ollama_embed(texts, embed_model="nomic-embed-text"),
    ),
)
```

## Writing to Memory
```python
# Single document
rag.insert("Arghyadeep stayed up past 2AM → commit quality dropped next day")

# Batch insert
rag.insert(["fact 1", "fact 2", "fact 3"])
```

## Reading from Memory (4 modes)
```python
# Local — entity-level retrieval (fast, specific)
result = rag.query("what caused the last build failure?",
                   param=QueryParam(mode="local"))

# Global — community-level (slow, broad patterns)
result = rag.query("what are Arghyadeep's productivity patterns?",
                   param=QueryParam(mode="global"))

# Hybrid — local + global (recommended default)
result = rag.query("what should VECTOR prioritise today?",
                   param=QueryParam(mode="hybrid"))

# Naive — vector search only (fastest, no graph)
result = rag.query("last git commit message",
                   param=QueryParam(mode="naive"))
```

## 4-DB Sync Architecture (District 7)
```
LightRAG graph  ←→  Neo4j (relationships)
                ←→  PostgreSQL (structured facts)
                ←→  SQLite FTS5 (episodic log)
                ←→  ChromaDB (vector embeddings)
```

## Session Hydration Pattern (use in EVERY district)
```python
def get_session_context(district_name: str) -> str:
    return rag.query(
        f"Recent decisions, active tasks, and warnings for {district_name}",
        param=QueryParam(mode="hybrid", top_k=5)
    )
```

## Critical Rules
- NEVER use cloud Neo4j AuraDB — local instance only (data sovereignty)
- Insert AFTER verification, not before — don't pollute memory with bad data
- Use `mode="hybrid"` as default — falls back gracefully if graph is sparse
- District 7 is the SINGLE write point for long-term memory — other districts call it via API
