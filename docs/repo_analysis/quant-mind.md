# quant-mind-master - VECTOR Absorption Review

**Verdict:** IMPLEMENT a narrow research-ingestion upgrade, not the whole framework.

**Priority:** MEDIUM

**Effort:** 1 focused session

**License:** MIT

**Repo size inspected:** ~109 files / ~8 MB

## What It Is

QuantMind is a Python framework for extracting finance/research knowledge from papers, news, blogs, reports, and SEC-style material into typed knowledge objects. The useful pieces are typed input routing for papers, fetch/format separation, frozen Pydantic knowledge contracts with provenance/citations, `TreeKnowledge` for whole papers, and a natural-language resolver that maps a user request into structured flow input/config.

Its own `GraphKnowledge` is a placeholder, not a working graph engine.

## VECTOR Already Has

- `districts/research/paper_reader.py`: arXiv search/daily brief, Obsidian write, episodic memory
- `districts/research/web_scout.py`, `news_aggregator.py`, `research_hub.py`, `deep_researcher.py`
- `core/research_engine/`: hypothesis, experiment, sandbox, analyzer, report assembler
- `core/research_engine/research_library/`: document/library persistence services
- `core/memory/knowledge_graph.py` and LightRAG/Obsidian sync
- investment research/reporting surfaces under `districts/investment/`

So QuantMind is not a new research district. It is a cleaner paper ingestion and provenance contract.

## Overlap

Approximate overlap: **65-70%**.

VECTOR already fetches papers, writes briefs, stores memory, and has broader research agents. QuantMind is better only at the typed ingestion contract: every extracted item has time validity, provenance, citations, and a canonical embedding string.

## Real Gaps Worth Absorbing

1. **Typed paper-source ingestion.** VECTOR's `PaperReader` fetches arXiv metadata and abstracts, but it does not expose a unified router for arXiv id, URL, local PDF/HTML/Markdown, raw text, and future DOI.

2. **Source provenance contract.** Research artifacts are not consistently stamped with `as_of`, `source.kind`, `source.uri`, `content_hash`, `extraction.model`, and citation anchors.

3. **Tree paper extraction.** VECTOR can summarize papers, but it does not have a first-class section-node schema that preserves hierarchy and per-node citations.

4. **Natural-language flow resolver.** A request like "summarize this arXiv paper and focus on limitations" should compile into structured input/config before execution.

## What Not To Absorb

- Do not import QuantMind as a dependency.
- Do not copy its OpenAI Agents SDK workflow wholesale.
- Do not build its placeholder graph layer; VECTOR already has LightRAG.
- Do not replace `PaperReader` or `research_hub`; extend them.
- Do not add DOI full-text resolution unless Unpaywall or another legal open-access resolver is explicitly scoped.

## Implementation Plan For Sonnet

1. Add `districts/research/paper_ingestion.py`.
   - Define Pydantic models: `ResearchSourceRef`, `ExtractionRef`, `CitationRef`, `PaperNode`, `PaperArtifact`, `PaperCard`.
   - Include `as_of`, `created_at`, `source`, `content_hash`, `citations`, `tags`, and `embedding_text()`.

2. Add `PaperInput` variants.
   - `arxiv`, `url`, `local`, `text`
   - `doi` as unsupported/deferred with clear error

3. Implement fetch/format helpers.
   - Reuse `httpx`.
   - Use existing safe XML parsing patterns from `PaperReader`.
   - For PDFs, use whichever dependency is already present in VECTOR; if missing, degrade with a clear `"unsupported_pdf_parser"` result.
   - For HTML, prefer existing scraper/research utilities if available.

4. Wire into `PaperReader.run`.
   - Preserve existing `query` and daily brief behavior.
   - Add task types like `ingest_paper`, `summarize_paper_tree`, and `paper_card`.
   - Store output in Obsidian and episodic memory with provenance.

5. Add tests.
   - Discriminated input parsing.
   - Content hash stability.
   - HTML/plain-text/local-path graceful behavior.
   - arXiv XML parse still works.
   - DOI returns a deferred/unsupported status, not a crash.

## Acceptance Criteria

- Existing `tests/test_research_district.py` still passes.
- A raw text paper can produce a `PaperArtifact` and `PaperCard`.
- Missing PDF parser or network failure returns a structured error.
- Every stored paper artifact includes `as_of`, `source`, and `content_hash`.

## Final Recommendation

Absorb only the **typed research ingestion contract**. This is a practical upgrade to VECTOR's research memory quality, especially for finance and AI papers. It should be implemented as a thin extension to `PaperReader` and the research library, not as a parallel QuantMind subsystem.
