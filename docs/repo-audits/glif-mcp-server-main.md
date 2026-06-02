# glif-mcp-server-main Audit

**Repo:** glif-mcp-server — TypeScript MCP server for glif.app AI workflows (MIT)
**Audited:** 2026-06-02

---

## 1. Repo Reality

TypeScript MCP server (`@glifxyz/glif-mcp-server`) exposing glif.app visual AI workflow pipelines as MCP tools:
- `run_workflow` — run any glif workflow by ID (image gen → upscale → text → audio → video)
- `workflow_info` — get workflow metadata
- `list_featured_workflows`, `search_workflows`, `my_workflows` — discovery
- `list_agents`, `load_agent` — agent browsing

Bridge: `GLIF_API_TOKEN` → calls `https://simple-api.glif.app`. Returns base64 images, text, audio, video as MCP content blocks.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Status |
|---------|------------------|--------|
| Image generation | `comfyui_adapter.py` (local only) | ⚠️ Local only |
| External AI workflow pipelines | ❌ None | ❌ |
| Chained gen (image→upscale→text) | ❌ No pipeline chaining | ❌ |
| Community workflow library | ❌ No workflow discovery | ❌ |

---

## 3. Frontend: N/A (API-only, workflows run on glif.app)

---

## 4. Verdict

**INTEGRATE DIRECTLY** — Build and add to `.mcp.json`:
```bash
cd C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\glif-mcp-server-main
npm install && npm run build
```
Add `GLIF_API_TOKEN` to `.env`. Wire to `districts/content/` and `districts/marketing/` via MCP tool calls.

**Delete-readiness:** KEEP as npm package. Run locally as MCP sidecar.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | glif-mcp not built or wired to `.mcp.json` | `.mcp.json` | MED |
| G2 | `GLIF_API_TOKEN` not in `.env` or `core/config.py` | `core/config.py` | MED |
| G3 | No `districts/content/glif_workflow_agent.py` for autonomous content pipelines | `districts/content/` | LOW |
