# markitdown-main Audit

## 1. Repo Reality

MarkItDown is Microsoft's open-source Python library (MIT) for converting files of almost any format — PDF, DOCX, PPTX, XLSX, images, audio, HTML, CSV, JSON, ZIP, YouTube URLs, ePubs, Jupyter notebooks, Outlook .msg, RSS — into Markdown for LLM consumption. It prioritizes structure preservation (headings, tables, links) over pixel-perfect fidelity. It ships as `pip install markitdown[all]` and also as an MCP server (`markitdown-mcp` package).

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| MarkItDown integration in Obsidian sync | `core/memory/obsidian_sync.py` lines 317-364 | `markitdown used in: ./core/memory/obsidian_sync.py` — `from markitdown import MarkItDown` at line 326, used as pre-processor before ingesting non-markdown files into the vault | COVERED |
| MarkItDown in web scraping | `districts/research/web_scout.py` line 19 | Confirmed: `Uses DuckDuckGo ... + MarkItDown for conversion` | COVERED |
| MarkItDown in worktree research agents | `.claude/worktrees/agent-a52c840f31ef6b67b/agents/districts/research/markitdown/` | Present with full converter suite matching upstream | COVERED |
| PDF → Markdown for paper reader | `districts/research/paper_reader.py` | Uses ArXiv Atom API (XML/abstract), not binary PDF — no converter needed for this path | N/A |

**Verification output (exact):**
```
markitdown used in: ./.claude/worktrees/agent-a52c840f31ef6b67b/agents/districts/research/markitdown/converters/_doc_intel_converter.py
./core/memory/obsidian_sync.py
./districts/research/web_scout.py
```

VECTOR consumes markitdown as a **runtime dependency** (`from markitdown import MarkItDown`), not as a code-to-absorb repo. The integration is already live.

### Converter coverage in the upstream repo

The `packages/markitdown/src/markitdown/converters/` directory contains 22 converters: audio, Bing SERP, CSV, Azure Document Intelligence, DOCX, ePub, ExifTool, HTML, image, IPYNB, LLM caption, markdownify, Outlook MSG, PDF, plain text, PPTX, RSS, audio transcription, Wikipedia, XLSX, YouTube, ZIP. All are optional-dependency-gated.

VECTOR does not need to absorb any of this — it is a `pip install markitdown[all]` away.

### What markitdown-main has beyond what VECTOR uses

- **`markitdown-mcp` package** — standalone MCP server exposing markitdown as an MCP tool. VECTOR's `core/mcp_server.py` does not expose a document-conversion MCP tool
- **`markitdown-ocr` package** — OCR-specific converter integration. VECTOR has `pytesseract` for OCR but not via markitdown's pipeline
- **Azure Document Intelligence converter** — enterprise-grade document parsing via Azure API. VECTOR has no Azure DI integration
- **`markitdown-sample-plugin`** — plugin SDK for custom converters. VECTOR could use this to add custom converters (e.g., for Indian financial documents, KIIT portal HTML)

---

## 3. Frontend

N/A — MarkItDown is a backend utility library.

---

## 4. Verdict

**SAFE TO DELETE** (as a source repo to absorb)

VECTOR already uses markitdown as a pip package. The source repo is the upstream of that package — there is nothing to absorb. Keep it only as a local reference if development on custom converters is planned.

**One action item:** `pip install 'markitdown[all]'` to ensure all converters are active in `.venv`. Currently `obsidian_sync.py` imports it with a graceful fallback (`logger.debug("[VECTOR][obsidian] markitdown not installed — skipping non-md conversion")`), meaning DOCX/PDF/PPTX files dropped into the vault may silently fail to ingest if the package is absent.

---

## 5. Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| `pip install 'markitdown[all]'` | HIGH | Required for Obsidian vault to ingest non-markdown files (DOCX, PDF, PPTX, XLSX, audio) into LightRAG. Currently fails silently. |
| markitdown MCP tool | Low | `markitdown-mcp` could be wired into `core/mcp_server.py` as a `convert_document` tool, letting any VECTOR agent convert arbitrary files to Markdown on demand. |
| Custom KIIT portal converter | Low | KIIT's academic portal renders HTML with dynamic JS tables. A custom markitdown plugin (via `markitdown-sample-plugin` pattern) could give `kiit_scraper.py` cleaner Markdown output than raw HTML parsing. |
