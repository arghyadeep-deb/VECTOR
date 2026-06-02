# open-skills-main Audit

## 1. Repo Reality

**Source:** `BandarLabs/open-skills` (Apache 2.0 license)
**Purpose:** A local MCP server that runs Claude Code skills inside an isolated Apple Silicon container (`@apple/container`), enabling skills to execute Python/bash code on local files without uploading to cloud.
**Language:** Python (FastAPI + MCP + Playwright + Jupyter kernel), Docker, Bash shell scripts.
**Architecture:**
- `server.py` — FastMCP server exposing 5 tools: `execute_python_code`, `get_skill_file`, `get_skill_info`, `list_skills`, `navigate_and_get_all_visible_text`
- `install.sh` — Bootstraps the Apple container runtime, starts a Jupyter kernel inside it
- `docker-compose.yml` + `Dockerfile` — Container build for the Jupyter execution sandbox
- Skills in `skills/public/`: `image-crop-rotate`, `pdf-text-replace`

**Platform requirement (hard):** macOS with Apple Silicon (M1/M2/M3/M4/M5). The installer immediately exits on any non-darwin OS.

From `install.sh` line 8-10:
```bash
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "This script is intended for macOS systems only. Exiting."
    exit 1
fi
```

The sandboxing relies on `@apple/container` — Apple's VM-level container system that only runs on Apple Silicon. There is no Windows fallback path.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|-------------------|-----------------|--------|
| Sandboxed code execution | `core/sandbox/vector_sandbox.py` (VectorSandbox from openfang absorption) | Confirmed in `phase_status.md` — openfang absorbed | COVERED |
| MCP server exposing tools | `core/mcp_server.py` — 14 real tools + kanban(4) + claims(7) + guidance(3) + voice(2) + browser(3) | Confirmed in `phase_status.md` | COVERED |
| Skill execution infrastructure | VECTOR's own `~/.claude/skills/` with 60+ installed skills | Confirmed: skills are Claude Code native, not MCP-proxied | DIFFERENT APPROACH |
| Local file processing (PDF, images) | `core/knowledge/` (DomainExtractor, WikiParser), `districts/content/` | Absorbed from Understand-Anything, postiz | COVERED |
| Playwright web scraping | `districts/research/web_scout.py`, `districts/time_calendar/kiit_scraper.py` | Confirmed in `phase_status.md` | COVERED |
| Apple Container runtime | N/A — Windows 11 system | Cannot run | INCOMPATIBLE |
| Jupyter kernel pool | Not needed — VECTOR runs Python natively | N/A | NOT NEEDED |
| MCP path translation `/mnt/user-data` | N/A | N/A | macOS artifact |

---

## 3. Frontend

None. This repo has no frontend. The "skill runner" is a CLI/MCP layer.

---

## 4. Verdict

**DELETE-NOW**

Reasons:
1. **Hard platform incompatibility.** `install.sh` exits immediately on non-darwin systems. The core sandbox is `@apple/container` — Apple's Apple Silicon VM isolation. VECTOR runs on Windows 11 (Legion Pro 5, RTX 5070 Ti). This cannot run.
2. **All concepts already covered.** Sandboxed execution (`VectorSandbox`), MCP server (`core/mcp_server.py`), local file processing, Playwright scraping — all implemented natively in VECTOR's Python stack.
3. **Wrong execution model.** open-skills routes Claude skill execution through a Jupyter kernel inside an Apple container. VECTOR executes skills directly via the Claude Code agent runtime — no proxy server needed.
4. **Zero Python code to absorb.** The server.py is a macOS-specific MCP proxy for a Jupyter container. The two bundled skills (`image-crop-rotate`, `pdf-text-replace`) are trivially thin wrappers.

**Risk of deletion:** ZERO. Apache 2.0, re-downloadable. Nothing in this repo is absorbed or referenced by VECTOR.

---

## 5. Gaps

No gaps. The value proposition of this repo (run Claude skills locally in a sandbox) is fully met by VECTOR's existing stack:
- `core/sandbox/vector_sandbox.py` — process-isolated execution
- `core/mcp_server.py` — 25+ native MCP tools
- `core/browser/` — Playwright DOM pruner + PII scrubber + auth profiles

The only scenario where open-skills would be useful is running Claude Desktop on a Mac to process local files with official Anthropic skills (docx, pptx, xlsx). That is not VECTOR's use case.
