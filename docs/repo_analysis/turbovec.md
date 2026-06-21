# turbovec — Absorption Analysis

> Authored by Opus (parallel agent hit session limit before writing; recovered from recon).

**Verdict:** UPGRADE (optional, scale-gated) — absorb as an alternative ANN index behind a seam; not urgent for current corpus size.

**What it is:** A Rust vector index with Python bindings (`pip install turbovec`), built on Google Research's **TurboQuant** — a data-oblivious quantizer with no separate training phase. Claims 10M docs in ~4 GB (vs 31 GB float32), faster than FAISS IndexPQFastScan on ARM, SIMD kernels (NEON/AVX-512), online ingest (no rebuilds), and filter-at-search-time (id allowlist honored in-kernel). Fully local/air-gapped. License: check `LICENSE` (MIT/Apache per crates.io badges).

**VECTOR already has:** `lightrag` as the RAG system (`core/memory/knowledge_graph.py`), plus `chromadb` in the stack (libraries.md). lightrag handles entity/relation graph + vector retrieval; chromadb is the embedding store. turbovec is *only* the ANN index layer — it does not replace lightrag's graph/RAG logic.

**Overlap / comparison:** Different layers. turbovec ≈ a faster, far more memory-efficient ANN index that could sit *behind* embeddings; lightrag/chromadb provide the RAG orchestration + storage. turbovec's wins (4 GB for 10M, online ingest, in-kernel filtering) only matter once VECTOR's vector corpus is large (>~1M vectors). For a single-owner system today, chromadb is almost certainly sufficient.

**If UPGRADE — what to replace & migration risk:** Replace only chromadb's ANN index (not lightrag). Risk: lightrag may be coupled to chromadb's API; swapping needs an adapter implementing lightrag's vector-store interface over turbovec. Medium effort, real coupling risk. Data migration = re-embed/re-ingest (turbovec needs no train step, so ingest is cheap).

**Integration plan:** (1) `pip install turbovec` (guarded optional dep). (2) `core/memory/turbovec_index.py` — a thin vector-store adapter matching lightrag's expected interface. (3) Config flag `CONFIG["memory"]["vector_index"] = "chromadb" | "turbovec"`. (4) Benchmark on VECTOR's real corpus before switching default. Effort: ~1 session + benchmarking.

**Recommendation:** Worth absorbing as an **opt-in** index for when memory/scale bites, but **do not make it the default now** — chromadb works and lightrag coupling is the risk. Rank it LOW priority vs VoxCPM/train-llm. Pure-Python integration via the pip wheel (no Rust reimplementation needed).
