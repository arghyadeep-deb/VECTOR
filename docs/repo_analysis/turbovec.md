# turbovec — Absorption Analysis

> Authored by Opus (parallel agent hit session limit before writing; recovered from recon).

**Verdict:** UPGRADE (optional, scale-gated) — absorb as an alternative ANN index behind a seam; not urgent for current corpus size.

**What it is:** A Rust vector index with Python bindings (`pip install turbovec`), built on Google Research's **TurboQuant** — a data-oblivious quantizer with no separate training phase. Claims 10M docs in ~4 GB (vs 31 GB float32), faster than FAISS IndexPQFastScan on ARM, SIMD kernels (NEON/AVX-512), online ingest (no rebuilds), and filter-at-search-time (id allowlist honored in-kernel). Fully local/air-gapped. License: check `LICENSE` (MIT/Apache per crates.io badges).

**VECTOR already has:** `lightrag` as the RAG system (`core/memory/knowledge_graph.py`), plus `chromadb` in the stack (libraries.md). lightrag handles entity/relation graph + vector retrieval; chromadb is the embedding store. turbovec is *only* the ANN index layer — it does not replace lightrag's graph/RAG logic.

**Overlap / comparison:** Different layers. turbovec ≈ a faster, far more memory-efficient ANN index that could sit *behind* embeddings; lightrag/chromadb provide the RAG orchestration + storage. turbovec's wins (4 GB for 10M, online ingest, in-kernel filtering) only matter once VECTOR's vector corpus is large (>~1M vectors). For a single-owner system today, chromadb is almost certainly sufficient.

**If UPGRADE — what to replace & migration risk:** Replace only chromadb's ANN index (not lightrag). Risk: lightrag may be coupled to chromadb's API; swapping needs an adapter implementing lightrag's vector-store interface over turbovec. Medium effort, real coupling risk. Data migration = re-embed/re-ingest (turbovec needs no train step, so ingest is cheap).

**Integration plan:** (1) `pip install turbovec` (guarded optional dep). (2) `core/memory/turbovec_index.py` — a thin vector-store adapter matching lightrag's expected interface. (3) Config flag `CONFIG["memory"]["vector_index"] = "chromadb" | "turbovec"`. (4) Benchmark on VECTOR's real corpus before switching default. Effort: ~1 session + benchmarking.

**Recommendation:** Worth absorbing as an **opt-in** index for when memory/scale bites, but **do not make it the default now** — chromadb works and lightrag coupling is the risk. Rank it LOW priority vs VoxCPM/train-llm. Pure-Python integration via the pip wheel (no Rust reimplementation needed).

---

## Correction (2026-06-22, before implementing — verified against the running code, not the doc's assumption)

This doc's premise that **chromadb is the active vector backend is wrong** — confirmed by grepping the entire codebase: **zero files import chromadb anywhere** (`core/`, `districts/`). `chromadb` is listed in `libraries.md`'s aspirational stack table but was never actually wired in.

What's actually running: `core/memory/obsidian_sync.py:225` constructs `LightRAG(working_dir="./data/lightrag_vault", ...)` with **no `vector_storage` kwarg**, so LightRAG falls through to its own bundled default backend — confirmed by the on-disk artifacts (`data/lightrag_vault/vdb_chunks.json`, `vdb_entities.json`, `vdb_relationships.json` — NanoVectorDB's exact file-naming convention, a JSON-file-backed ANN index LightRAG ships internally).

This changes the integration target: turbovec would need to implement **LightRAG's `BaseVectorStorage` interface** as a custom backend class (LightRAG supports pluggable backends via that interface), not a chromadb-shaped adapter as originally planned — a different, not-yet-scoped piece of work.

**Current corpus scale, measured directly** (2026-06-22): largest vault file is `vdb_entities.json` at 358 KB; `episodic_memory` (the separate SQLCipher store) has ~68K rows. Both are **orders of magnitude below the >1M-vector threshold** where turbovec's 4GB-for-10M / online-ingest advantages would matter. NanoVectorDB's brute-force search is fine at this scale.

**Decision: defer, no code written.** Per the project's own anti-premature-abstraction rule (don't build for a scale that doesn't exist yet) and this repo's own "not urgent for current corpus size" verdict, building a `BaseVectorStorage` adapter now would be speculative scaffolding with nothing to benchmark against. Re-open this when `data/lightrag_vault/vdb_*.json` actually approaches a size where NanoVectorDB's brute-force scan becomes a measured bottleneck — at that point, write the LightRAG `BaseVectorStorage` adapter (not a chromadb one) and benchmark before flipping any default.
