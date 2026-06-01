# Repo Audit: playwright-mcp-main

**Audited:** 2026-06-02
**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\playwright-mcp-main`
**License:** Apache-2.0 (Microsoft)
**Package:** `@playwright/mcp` v0.0.75

---

## Step 1 — Repo Reality

### Language and architecture

This is a **thin Node.js shell** (3 JS files: `cli.js`, `index.js`, `index.d.ts`). It is not a standalone project. The actual source code lives inside the Playwright monorepo at `packages/playwright/src/mcp` and is bundled into `playwright-core/lib/coreBundle`. The `src/` folder in this repo contains only a README redirecting to the monorepo. The published package is effectively an NPM shim that exposes `tools.decorateMCPCommand()` and `tools.createConnection()` from `playwright-core`.

**Runtime:** Node.js 18+ required. Launched via `npx @playwright/mcp@latest [flags]`.

**Transport options:**
- **stdio** (default) — Claude Desktop, Claude Code, VS Code, Cursor, Cline, etc.
- **SSE/HTTP** — run with `--port 8931`, then clients connect to `http://localhost:8931/mcp`

**Browser support:** Chromium, Firefox, WebKit, Chrome, msedge. Persistent profile by default; `--isolated` for ephemeral sessions.

---

### Complete MCP tool inventory (62 tools total)

#### Core automation (always on — 22 tools)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_click` | no | Click element by accessibility ref or CSS selector |
| `browser_close` | no | Close the current page |
| `browser_console_messages` | yes | Return console messages at a given level |
| `browser_drag` | no | Drag and drop between two elements |
| `browser_drop` | no | Drop files or MIME-typed data onto an element |
| `browser_evaluate` | no | Evaluate JavaScript on page or element |
| `browser_file_upload` | no | Upload one or more files |
| `browser_fill_form` | no | Fill multiple form fields in one call |
| `browser_handle_dialog` | no | Accept or dismiss dialog boxes |
| `browser_hover` | no | Hover over element |
| `browser_navigate` | no | Navigate to a URL |
| `browser_navigate_back` | no | Go back in browser history |
| `browser_network_request` | yes | Show full headers + body of one network request |
| `browser_network_requests` | yes | List all network requests since page load |
| `browser_press_key` | no | Press a keyboard key |
| `browser_resize` | no | Resize the browser viewport |
| `browser_run_code_unsafe` | no | Execute arbitrary Playwright JS (RCE-equivalent) |
| `browser_select_option` | no | Select dropdown option |
| `browser_snapshot` | yes | Accessibility tree snapshot (better than screenshot for agents) |
| `browser_take_screenshot` | yes | PNG/JPEG screenshot of current page |
| `browser_type` | no | Type text into an element |
| `browser_wait_for` | no | Wait for text to appear/disappear or time to pass |

#### Tab management (1 tool)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_tabs` | no | List, create, close, or select a browser tab |

#### Config (opt-in `--caps=config`, 1 tool)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_get_config` | yes | Get resolved server configuration |

#### Network mocking (opt-in `--caps=network`, 4 tools)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_network_state_set` | no | Toggle online/offline mode |
| `browser_route` | no | Mock network requests matching a URL pattern |
| `browser_route_list` | yes | List all active routes |
| `browser_unroute` | no | Remove route(s) |

#### Storage management (opt-in `--caps=storage`, 14 tools)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_cookie_clear/delete/get/list/set` | mixed | Cookie CRUD |
| `browser_localstorage_clear/delete/get/list/set` | mixed | localStorage CRUD |
| `browser_sessionstorage_clear/delete/get/list/set` | mixed | sessionStorage CRUD |
| `browser_set_storage_state` | no | Restore cookies + localStorage from file |
| `browser_storage_state` | yes | Save cookies + localStorage to file |

#### DevTools (opt-in `--caps=devtools`, 8 tools)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_annotate` | yes | Open annotation mode, return annotated screenshot + ARIA + annotations |
| `browser_hide_highlight` | yes | Remove element highlight overlay |
| `browser_highlight` | yes | Add persistent highlight overlay to element |
| `browser_resume` | no | Resume paused script / step-by-step debug |
| `browser_start_tracing` | yes | Start Playwright trace recording |
| `browser_start_video` | yes | Start video recording |
| `browser_stop_tracing` | yes | Stop trace recording |
| `browser_stop_video` | yes | Stop video recording |
| `browser_video_chapter` | yes | Add chapter marker to video |

#### Coordinate-based / Vision (opt-in `--caps=vision`, 6 tools)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_mouse_click_xy` | no | Click at pixel coordinates |
| `browser_mouse_down` | no | Mouse button down |
| `browser_mouse_drag_xy` | no | Drag from (x1,y1) to (x2,y2) |
| `browser_mouse_move_xy` | no | Move mouse cursor |
| `browser_mouse_up` | no | Mouse button up |
| `browser_mouse_wheel` | no | Scroll mouse wheel |

#### PDF generation (opt-in `--caps=pdf`, 1 tool)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_pdf_save` | yes | Save current page as PDF |

#### Test assertions (opt-in `--caps=testing`, 4 tools)
| Tool | Read-only | Description |
|------|-----------|-------------|
| `browser_generate_locator` | yes | Generate a Playwright locator string for an element |
| `browser_verify_element_visible` | no | Assert element is visible by ARIA role + name |
| `browser_verify_list_visible` | no | Assert list items are visible |
| `browser_verify_text_visible` | no | Assert text is visible on page |
| `browser_verify_value` | no | Assert element value matches expected |

---

### How to run

**Headless with SSE transport (recommended for VECTOR):**
```bash
npx @playwright/mcp@latest --headless --port 8931
```

**MCP client config (SSE):**
```json
{
  "mcpServers": {
    "playwright": {
      "url": "http://localhost:8931/mcp"
    }
  }
}
```

**Claude Code add:**
```bash
claude mcp add playwright npx @playwright/mcp@latest
```

**Docker (headless chromium only):**
```bash
docker run -d -i --rm --init --pull=always \
  --name playwright \
  -p 8931:8931 \
  mcr.microsoft.com/playwright/mcp \
  /app/cli.js --headless --browser chromium --no-sandbox --port 8931 --host 0.0.0.0
```

---

## Step 2 — VECTOR Parity Check

**Command run:**
```
cd "C:\...\V.E.C.T.O.R. Codebase" && python -X utf8 -c "
import sys; sys.path.insert(0,'.')
from core.browser.dom_pruner import DOMPruner
from core.browser.auth_profiles import BrowserAuthStore
d = DOMPruner(); print('DOMPruner OK')
import subprocess
r = subprocess.run(['grep', '-c', 'browser', 'core/mcp_server.py'], capture_output=True, text=True)
print('browser MCP tools:', r.stdout.strip())
" 2>&1 | tail -4
```

**Output:**
```
DOMPruner OK
browser MCP tools: 114
```

**Interpretation:** VECTOR has 31 `browser_*` MCP tools (confirmed by `grep -c "def browser_"`) wired to `core/stealth_browser/client.py`, plus 3 tools from `core/browser/` (dom_pruner, auth profiles). The `114` count is raw line matches for the word "browser" across the 2700-line `mcp_server.py`.

### VECTOR's current browser stack (3 layers)

**Layer 1: `core/stealth_browser/`** — The primary browser engine. Anti-detection Node.js server (`@askjo/camofox-browser` / camoufox) running at `:9377`. Python client `StealthBrowserClient` wraps all REST endpoints. Used by: `districts/research/web_scout.py`, `districts/research/stealth_scout_agent.py`. 28 MCP tools wired.

**Layer 2: `core/browser/`** (absorbed from auto-browser-main, 2026-05-27)
- `dom_pruner.py` — Scores and prunes DOM observations from ~18K tokens to ~500 tokens
- `pii_scrub.py` — 17 regex patterns + Pillow pixel redaction of screenshots
- `auth_profiles.py` — Named Playwright storage-state profiles (save once, reuse forever)

**Layer 3: Direct `playwright` Python bindings**
- `districts/time_calendar/kiit_scraper.py` — `async_playwright()` for KIIT portal scraping
- `core/research_engine/research_library/downloaders/playwright_html.py` — JS-rendered HTML downloader
- `districts/marketing/ads/scripts/analyze_landing.py` and `capture_screenshot.py` — sync_playwright for ads analysis
- `districts/intelligence/shadowbroker_server/` — playwright + playwright-stealth for intelligence scraping

**Gap vs playwright-mcp:**

| Capability | VECTOR has | playwright-mcp has |
|------------|------------|--------------------|
| Navigate + click + type | Yes (stealth_browser) | Yes (browser_navigate/click/type) |
| Accessibility tree snapshot | Yes (stealth_browser /snapshot) | Yes (browser_snapshot) — **richer, ARIA-compliant** |
| Multi-tab management | Yes (stealth_browser tabs API) | Yes (browser_tabs) |
| Network request inspection | Partial (stealth_browser /network) | Yes (browser_network_requests + browser_network_request) — **complete headers + body** |
| Network mocking / routes | No | Yes (browser_route) — **VECTOR gap** |
| Cookie management | Partial (stealth_browser /cookies endpoint, async stub) | Yes (full CRUD: cookie_get/set/delete/list/clear) — **VECTOR gap** |
| localStorage / sessionStorage | Partial (async stub, requires stealth server endpoint) | Yes (full CRUD for both) — **VECTOR gap** |
| Storage state save/restore | Yes (auth_profiles.py — file-backed) | Yes (browser_storage_state + browser_set_storage_state) |
| File upload | No structured tool | Yes (browser_file_upload) |
| Form fill (bulk) | Yes (browser_form in MCP) | Yes (browser_fill_form) |
| JavaScript evaluation | Yes (browser_eval, async stub) | Yes (browser_evaluate) — **direct, no server stub** |
| Anti-detection / stealth | Yes (camoufox Firefox-based) | No (standard Chromium/WebKit) |
| Multi-browser (Chromium+Firefox+WebKit) | No (camoufox = Firefox only) | Yes — **Chromium, Firefox, WebKit, Chrome, Edge** |
| PDF export | Stub (requires stealth /pdf) | Yes (browser_pdf_save) — **works out of box** |
| Video recording | No | Yes (browser_start_video/stop_video) — **VECTOR gap** |
| Playwright traces | No | Yes (browser_start_tracing/stop_tracing) — **VECTOR gap** |
| DOM pruning (token reduction) | Yes (dom_pruner.py — absorbed) | No (raw accessibility tree) |
| PII scrubbing of screenshots | Yes (pii_scrub.py — absorbed) | No |
| Named auth profiles (Python) | Yes (auth_profiles.py) | Handled via --storage-state / --user-data-dir flags |
| Coordinate/pixel clicks | No in Python | Yes (browser_mouse_click_xy etc.) |
| ARIA-based test assertions | No | Yes (browser_verify_element_visible etc.) |
| DevTools + annotation mode | No | Yes (browser_annotate, browser_highlight) |

---

## Step 3 — Integration Plan

### How to run
```bash
npx @playwright/mcp@latest --headless --port 8931
```

This exposes all 22 core tools + optional capability groups via SSE at `http://localhost:8931/mcp`.

### Wiring VECTOR districts to playwright-mcp

The integration is as an **external MCP sidecar** called over HTTP/SSE by `provider_client.py` or a dedicated Python client. VECTOR never imports the Node.js package directly.

**Recommended Python bridge:**
```python
# core/browser/playwright_mcp_client.py
import httpx

MCP_URL = "http://127.0.0.1:8931/mcp"

async def call_tool(tool_name: str, params: dict) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            MCP_URL,
            json={"method": "tools/call", "params": {"name": tool_name, "arguments": params}},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()
```

**District call patterns:**

| District | Current code | With playwright-mcp |
|----------|-------------|---------------------|
| `time_calendar/kiit_scraper.py` | Direct `async_playwright()` + chromium.launch | Replace with `browser_navigate` + `browser_snapshot` + `browser_click` via MCP client |
| `research/web_scout.py` | `StealthBrowserClient` (camoufox) | Stays as-is for anti-detection scraping; playwright-mcp as fallback for standard sites |
| `marketing/ads/scripts/analyze_landing.py` | `sync_playwright()` | Replace with `browser_navigate` + `browser_snapshot` + `browser_take_screenshot` via MCP client |
| `marketing/ads/scripts/capture_screenshot.py` | `sync_playwright()` | Replace with `browser_navigate` + `browser_take_screenshot` via MCP client |
| `coding/qa/` district | None currently | Use `browser_verify_element_visible`, `browser_verify_text_visible` for automated UI assertions |
| `intelligence/shadowbroker_server/` | `sync_playwright` + `playwright-stealth` | Stays as-is (anti-detection requirement) |
| `core/research_engine/downloaders/playwright_html.py` | `sync_playwright` | Can replace with `browser_navigate` + `browser_evaluate` for JS-rendered HTML |

### What stays vs what becomes redundant

**KEEP (irreplaceable):**
- `core/stealth_browser/` — camoufox is Firefox-based with fingerprint spoofing. playwright-mcp cannot replicate this. Keep for scraping behind bot detection.
- `core/browser/dom_pruner.py` — Must be applied AFTER receiving playwright-mcp `browser_snapshot` output to reduce tokens. Not redundant; complementary.
- `core/browser/pii_scrub.py` — Must be applied to screenshots. Not redundant; complementary.
- `core/browser/auth_profiles.py` — Provides named profile management; playwright-mcp uses file paths for `--storage-state`. Python-side management is still needed.

**CAN BE REMOVED (replaced by playwright-mcp):**
- Direct `async_playwright()` / `sync_playwright()` calls in `kiit_scraper.py` (3 places), `playwright_html.py` (10+ places), `analyze_landing.py`, `capture_screenshot.py` — all can delegate to playwright-mcp MCP tools via the HTTP client.
- The 28 `browser_*` MCP stubs in `core/mcp_server.py` that say `"requires stealth browser server with /X endpoint"` can be backed by playwright-mcp instead of the camoufox server (for non-stealth use cases).

---

## Step 4 — Verdict: INTEGRATE DIRECTLY

**Integrate playwright-mcp as the default browser backend for non-stealth tasks.**

Rationale:
1. Node.js 24 is already installed (`node --version` = v24.15.0). No new runtime required.
2. `npx @playwright/mcp@latest` requires zero code changes to launch.
3. 22 always-on tools cover all of VECTOR's non-stealth browser needs (navigate, snapshot, click, type, screenshot, form fill, key press, wait).
4. The opt-in caps unlock 4 critical gaps: network mocking (`--caps=network`), full cookie/storage CRUD (`--caps=storage`), video recording, PDF export (`--caps=pdf`).
5. The accessibility-tree-first design (`browser_snapshot`) is better than raw HTML for LLM consumption, and VECTOR's `dom_pruner.py` can be applied on top to further reduce tokens.
6. Zero Python dependencies to add. No license issue (Apache-2.0).
7. VECTOR already has all architectural seams: `core/mcp_server.py` browser tool stubs, `core/browser/auth_profiles.py` for session state, `dom_pruner.py` for token reduction.

**Keep camoufox stealth server** for scraping targets that require anti-detection (Google, LinkedIn, KIIT portal). playwright-mcp is the standard-site path; camoufox is the anti-bot path.

---

## Step 5 — Gaps (numbered)

**Gap 1: No Python bridge module exists**
`core/browser/playwright_mcp_client.py` does not exist. VECTOR has no way to call the running playwright-mcp SSE server from Python. Need an async httpx client with JSON-RPC call wrapping, tool listing, error handling, and a `ensure_running()` helper that launches the Node.js process via `subprocess` if the port is not responding.

**Gap 2: Launch / lifecycle management missing**
`core/stealth_browser/server_manager.py` exists for camoufox, but there is no equivalent `PlaywrightMCPManager` that starts `npx @playwright/mcp@latest --headless --port 8931`, monitors it, and restarts on crash. Without this, the MCP server must be started manually.

**Gap 3: `kiit_scraper.py` still uses direct `async_playwright()`**
`districts/time_calendar/kiit_scraper.py` (lines 38–44, 205–210) launches its own Playwright Chromium instance. This duplicates browser overhead when playwright-mcp is running. Should be refactored to call `browser_navigate` + `browser_snapshot` + `browser_click` through the MCP client. The KIIT portal does not require stealth, so camoufox is overkill there.

**Gap 4: `playwright_html.py` uses direct `sync_playwright()`**
`core/research_engine/research_library/downloaders/playwright_html.py` (10+ usages) calls `sync_playwright()` directly. This creates a blocking synchronous context inside what is otherwise an async system. Replace with async calls through the playwright-mcp client. This also removes the need for `playwright` as a Python package in `requirements.txt` for the research path.

**Gap 5: 28 browser MCP stubs have `not_available` bodies**
In `core/mcp_server.py` lines 2484–2697, tools like `browser_eval`, `browser_cookie`, `browser_storage`, `browser_network`, `browser_pdf`, `browser_record`, `browser_replay`, `browser_assert`, `browser_select`, `browser_hover`, `browser_drag`, `browser_upload`, `browser_download`, `browser_resize` all return `"status": "not_available"` because the camoufox server doesn't expose those endpoints. These should be backed by playwright-mcp calls for standard-site automation, with the SSRF guard applied to the URL parameter before forwarding.

**Gap 6: No opt-in capabilities configured**
The recommended VECTOR launch command should include `--caps=storage,network,pdf` to unlock cookie CRUD, network mocking, and PDF export. None of these are enabled by default. A `core/config.py` entry for `playwright_mcp_caps` is needed so the launch command can be generated dynamically.

**Gap 7: No integration with `DOMPruner` on playwright-mcp responses**
`browser_snapshot` returns a full accessibility tree (potentially thousands of tokens). `dom_pruner.py` was built precisely to prune this. There is no middleware that automatically calls `DOMPruner.prune_observation()` on snapshot responses before passing them to the LLM. This should be wired in the Python bridge at the `call_tool` level.

**Gap 8: `core/mcp_server.py` browser tool list not updated**
When playwright-mcp is integrated, `core/mcp_server.py` should surface `browser_snapshot`, `browser_network_requests`, `browser_cookie_*`, `browser_storage_state`, `browser_pdf_save`, and `browser_tabs` as first-class VECTOR MCP tools that proxy to the playwright-mcp server — rather than keeping the existing hollow stubs. The governor and agents need to know these capabilities exist.

**Gap 9: No `--storage-state` wiring to `BrowserAuthStore`**
`core/browser/auth_profiles.py` saves Playwright storage-state JSON files. playwright-mcp accepts `--storage-state <path>` and `browser_set_storage_state` / `browser_storage_state` tools. There is no code that reads a named profile from `BrowserAuthStore` and passes its path to playwright-mcp when starting a session. The bridge needs a `load_auth_profile(profile_name)` → `browser_set_storage_state(filename)` flow.

**Gap 10: `ads/scripts/analyze_landing.py` and `capture_screenshot.py` use blocking `sync_playwright`**
These two scripts in `districts/marketing/ads/scripts/` call `sync_playwright()` synchronously inside FastAPI/async contexts. Replace with async calls to `browser_navigate` + `browser_take_screenshot` through the MCP client. This eliminates the only two remaining `sync_playwright` dependencies outside the research engine.

---

## Summary

| | Count |
|---|---|
| Total MCP tools exposed | 62 (22 core + 40 opt-in) |
| Always-on tools | 22 |
| Opt-in capability groups | 6 (config, network, storage, devtools, vision, pdf) |
| VECTOR current browser MCP stubs | 31 (28 hollow stubs + 3 active) |
| VECTOR direct playwright Python usages | 5 files (kiit_scraper, playwright_html, analyze_landing, capture_screenshot, shadowbroker) |
| Integration verdict | INTEGRATE DIRECTLY |
| Gaps identified | 10 |
| Action required before integration | Gaps 1 + 2 (bridge module + lifecycle manager) |
| Files to modify | `core/mcp_server.py`, `districts/time_calendar/kiit_scraper.py`, `core/research_engine/.../playwright_html.py`, `districts/marketing/ads/scripts/*.py`, `core/config.py` |
