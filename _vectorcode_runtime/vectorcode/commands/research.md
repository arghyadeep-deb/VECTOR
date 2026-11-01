<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/research.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

# Research Run

Trigger District 8 autoresearch on a topic.

Ask: **"What's the research topic?"**

Then dispatch the `vector-researcher` sub-agent with:
- Topic from user
- Mode: `deep` (multi-source) or `quick` (single pass)
- Output: save findings to LightRAG via District 7

The researcher uses `karpathy/autoresearch` loop pattern:
- Fixed 5-minute budget per query
- Self-evaluates: does this answer the question? If not, refine and retry
- Saves verified findings to memory, discards noise
- Delivers a cited summary at the end
