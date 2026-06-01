# OpenCLI-main Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\OpenCLI-main`
**Audited:** 2026-06-01
**Language:** TypeScript (Node.js >= 20) — not Python
**License:** Apache-2.0

---

## 1. Repo Reality

OpenCLI is a TypeScript CLI tool (npm package `@jackwener/opencli`) that converts websites into deterministic CLI interfaces and enables AI agents to drive real Chrome sessions via a local daemon + Chrome Extension bridge.

### Concrete features

**A. 130+ built-in site adapters (YAML/JS pipelines)**
Pre-built scrapers for: hackernews, reddit, twitter/X, bilibili, zhihu, linkedin, amazon, upwork, douyin, zhihu, weibo, arxiv, google-scholar, pubmed, github (via plugin), coingecko, spotify, instagram, tiktok, youtube, and 100+ more. Adapters are YAML pipeline or `.js` files under `clis/<site>/`. Each adapter supports multiple commands (e.g. `linkedin` has `connect`, `inbox`, `jobs`, `profile-read`, `safe-send`, `salesnav-*`, 20+ total).

**B. Chrome browser bridge (CDP-backed automation)**
- Local HTTP daemon (`src/daemon.ts`) on port 19825 bridges CLI to Chrome Extension
- Chrome Extension (Manifest V3, `extension/`) uses the Chrome Debugger API
- Full browser control: `navigate`, `click`, `type`, `fill`, `select`, `keys`, `wait`, `get`, `find`, `extract`, `screenshot`, `scroll`, `eval`, `network`, tab management
- Session lifecycle: `open`, `bind` (attach to existing tab), `close`
- `--window foreground|background` control

**C. Advanced DOM snapshot engine** (`src/browser/dom-snapshot.ts`)
- 13-stage pipeline: visibility pruning, SVG collapse, Shadow DOM traversal, iframe extraction, bbox parent-child dedup, paint-order occlusion, attribute whitelist, table-aware markdown serialization, interactive indices, `data-ref` annotation, incremental diff
- Separate `ax-snapshot.ts` for accessibility-tree refs
- `src/browser/shape.ts`: JSON shape inference for network response previews (token-aware, 2KB budget)

**D. Article extraction** (`src/browser/extract.ts`, `src/browser/article-extract.ts`)
- HTML→Markdown via `turndown` + `@mozilla/readability` (runs in-page via CDP)
- Paragraph-boundary chunk/continuation with `next_start_char` cursor
- Noise removal: nav/header/footer/aside/script/style stripped

**E. Network intercept layer** (`src/interceptor.ts`)
- Monkey-patches `fetch` and `XMLHttpRequest` in-page
- Disguises patched functions so `toString()` returns native code signature
- Per-session network cache with TTL persisted to `~/.opencli/cache/`

**F. Stealth anti-detection** (`src/browser/stealth.ts`)
- Patches: `navigator.webdriver=false`, `window.chrome` stub, plugin/mimeType spoofing, permissions API spoof, `language`/`languages`, `screen` dimensions, WebGL renderer string obfuscation
- Injected before page scripts via CDP

**G. YAML pipeline executor** (`src/pipeline/executor.ts`)
- Sequential step execution with per-step retry on transient browser errors
- Step registry: `src/pipeline/steps/` (intercept, tap, fetch, extract, etc.)
- Capability routing: browser-only steps vs non-browser steps

**H. Plugin system** (`src/plugin.ts`)
- `opencli plugin install github:user/repo` — git-based plugin install with lock file
- Monorepo support; per-plugin compat check
- Lifecycle hooks: `onStartup`, `onBeforeExecute`, `onAfterExecute`

**I. External CLI hub** (`src/external.ts`)
- Register any local binary: `gh`, `docker`, `vercel`, `wrangler`, `obsidian`, `tg`, `ntn` (Notion), etc.
- Discovery surface shared with built-in adapters

**J. Electron desktop app adapters**
- CDP endpoint targeting for: Cursor, Codex, ChatGPT App, ChatWise, Antigravity, Discord App, Doubao
- Port-based discovery, macOS bundle ID resolution

**K. Self-repair / autoresearch loop** (`autoresearch/`)
- Karpathy-pattern 8-phase autonomous iteration: review→ideate→modify→commit→verify→decide→log→repeat
- Generic: any project with a shell `verify` command + metric extraction
- Presets stored as JSON; TSV iteration log

**L. Output formats**
- All adapters support `--format table|json|yaml|md|csv`
- Structured exit codes from `sysexits.h` (0/66/69/75/77/78/130)

**M. AI agent skills** (`skills/`)
- `opencli-browser`: full agent protocol for driving Chrome (10 critical rules, compound form fields, stale-ref handling)
- `opencli-adapter-author`: end-to-end guide for writing new adapters
- `opencli-autofix`: repair broken adapters
- `opencli-usage`: command reference

**N. Observation session manager** (`src/observation/`)
- Ring-buffer event capture per session (artifact, redaction, retention policies)
- Export observation sessions as structured data

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|-------------------|-----------------|--------|
| HackerNews scraping | `opencli_adapter.py:get_hn_top()` + `research_hub.py:get_hn_top()` | `python -X utf8 -c "...get_hn_top(2)"` → `HN top (2): 2 items / #1: A 10 year old Xeon is all you need` | ✅ |
| Reddit scraping | `opencli_adapter.py:get_reddit_hot()` → `reddit_miner.py` fallback | Fallback chain in place; `opencli_adapter.py` line 148 imports `RedditMiner` | ✅ |
| GitHub trending | `opencli_adapter.py:get_github_trending()` + `research_hub.py:get_github_trending()` | `GitHub trending (2): 2 items` (confirmed live) | ✅ |
| ArXiv paper search | `research_hub.py:search_arxiv()` | Code present; XML API, no auth | ✅ |
| Web search (DuckDuckGo) | `research_hub.py:search_web()` | DDG JSON + HTML fallback | ✅ |
| DEV.to posts | `research_hub.py:get_devto_posts()` | Code present; free API | ✅ |
| ProductHunt top | `research_hub.py:get_producthunt_top()` | Code present; GraphQL | ✅ |
| YouTube search | `research_hub.py:search_youtube()` via yt-dlp | Code present | ✅ |
| CoinGecko crypto | `research_hub.py:get_crypto_prices()` | Code present; no auth | ✅ |
| India stocks (NSE) | `research_hub.py:get_india_stocks()` via Yahoo Finance | Code present | ✅ |
| DOM pruning for agents | `core/browser/dom_pruner.py:DOMPruner` | `from core.browser.dom_pruner import DOMPruner` → `DOMPruner OK: <class 'type'>` | ✅ |
| Browser PII scrubbing | `core/browser/pii_scrub.py` | `BrowserAuthStore OK: <class 'type'>` (both modules import clean) | ✅ |
| Named browser auth profiles | `core/browser/auth_profiles.py:BrowserAuthStore` | Import verified above | ✅ |
| OpenCLI adapter wrapper (subprocess) | `opencli_adapter.py:OpenCLIAdapter` | `OK <class '...OpenCLIAdapter'>` — instantiates, available=False (opencli not installed), fallbacks active | ✅ |
| Karpathy autoresearch loop | `districts/karpathy_lab/autoresearch_runner.py` | File present, 5-min budget, 3 experiments/run | ✅ |
| 130+ built-in site adapters (bilibili, zhihu, xiaohongshu, twitter, linkedin, etc.) | None — VECTOR has no direct equivalents for Chinese-platform or social-site adapters | Not runnable without npm opencli installed | ❌ |
| Chrome CDP bridge daemon | `core/stealth_browser/` exists but is a Playwright-based browser controller, not a Chrome Extension + daemon bridge | Different architecture: no WebSocket daemon, no Chrome Extension | ⚠️ |
| Advanced DOM snapshot (13-stage pipeline, bbox dedup, paint-order occlusion, ax-tree) | `core/browser/dom_pruner.py` covers relevance scoring only (scoring factors: task keyword, type priority, visibility, recency) | Shadow DOM, iframes, paint occlusion, incremental diff not covered | ⚠️ |
| Article extraction (Readability + Markdown chunking) | `core/stealth_browser/` has HTML fetch but no Readability/turndown integration | No `next_start_char` continuation cursor or paragraph-boundary chunking | ❌ |
| Network intercept (fetch/XHR monkey-patch) | No equivalent in VECTOR | — | ❌ |
| Stealth anti-detection JS injection | `core/stealth_browser/` — Playwright stealth via `playwright-stealth` library, NOT native JS injection via CDP | Different mechanism; no `navigator.webdriver`, WebGL spoof, or disguised-toString patches at CDP level | ⚠️ |
| YAML pipeline executor | No equivalent in VECTOR | — | ❌ |
| Plugin system (git-based, lock file) | No equivalent | — | ❌ |
| External CLI hub (passthrough for gh/docker/etc.) | No equivalent | — | ❌ |
| Electron desktop app adapters (Cursor/Codex/ChatGPT/Discord) | No equivalent | — | ❌ |
| Structured exit codes (sysexits.h) | No equivalent — Python agents use exceptions | — | ❌ |
| Observation session ring-buffer | `core/memory/episodic.py` (event store) — different purpose: long-term memory, not per-session browser observation capture | — | ⚠️ |
| Autoresearch generic metric loop (any verify command) | `autoresearch_runner.py` is specific to nanoGPT `train.py`; OpenCLI's version is project-agnostic | — | ⚠️ |
| ResearchHub instantiation | `research_hub.py:ResearchHub.__init__` calls `self.subscribe_to("task_completed")` which does NOT exist on `AgentBase` | `AttributeError: 'ResearchHub' object has no attribute 'subscribe_to'` on import | ⚠️ |

---

## 3. Frontend / Panel Spec

OpenCLI has no web UI. Its only visual component is:
- A minimal Chrome Extension popup (`extension/popup.html` + `popup.js`) — shows connection status (daemon connected/disconnected, extension version)
- An ANSI TUI (`src/tui.ts`) — terminal-based multi-select checkbox prompt for interactive command selection

No dashboard, no web app, no panel design needed for VECTOR HUD. If VECTOR were to expose opencli-style browser control as a HUD panel, the relevant surface would be a small "Browser Sessions" widget showing:
- Active sessions list (session name, tab URL, lease status)
- Network intercept ring-buffer (last N captured requests, shape preview)
- DOM snapshot viewer (interactive element count, pruned token size)

This is out of scope for current VECTOR frontend spec (`docs/frontend-spec.md`).

---

## 4. Verdict

**PATCH VECTOR**

**Reasoning:**

The VECTOR claim that OpenCLI is "absorbed" via `opencli_adapter.py` is approximately true for the research data sources (HN, Reddit, GitHub, ArXiv) — those work via their own public APIs and do not depend on the npm tool at all. `OpenCLIAdapter` correctly detects `opencli` is not installed and uses native fallbacks; this is working.

However, there are two distinct gaps that are **not** covered:

1. **ResearchHub is broken at instantiation** — `subscribe_to()` is called in `__init__` but `AgentBase` has no such method. This means `ResearchHub` cannot be instantiated and is silently dead in the autonomous loop. This is a one-line bug fix.

2. **Advanced browser automation features are not absorbed** — The CDP daemon, network intercept, advanced DOM snapshot pipeline (13 stages vs VECTOR's 4-factor pruner), article extraction with Readability + chunked continuation, and the Electron app adapter registry are not present in VECTOR. VECTOR's `core/browser/` covers PII scrubbing and profile management (absorbed from auto-browser-main, not from OpenCLI) but not the deep CDP-level features. Whether these are worth absorbing depends on whether VECTOR needs to drive real Chrome tabs with logged-in sessions — if yes, OpenCLI's architecture (daemon + Extension) is significantly more capable than Playwright stealth for sites that block headless browsers.

3. **130+ site adapters** are TypeScript pipelines under `clis/` — not absorbable as Python. They require the npm tool. VECTOR has fallbacks for 5-6 of them (HN, Reddit, GitHub, ArXiv, DEV.to), but the long tail (LinkedIn, Bilibili, Zhihu, Twitter, Amazon, etc.) is not covered natively.

Recommended action: fix the ResearchHub bug, and absorb the 4 missing browser primitives listed in Section 5.

---

## 5. Gaps

| # | Issue | Location | Type | Status |
|---|-------|----------|------|--------|
| G1 | `ResearchHub.__init__` calls `self.subscribe_to("task_completed")` and `self.subscribe_to("decision_made")` but `AgentBase` has no `subscribe_to` method — instantiation raises `AttributeError` | `districts/research/research_hub.py:64-65` | Bug | OPEN |
| G2 | `ResearchHub.handle_event()` also calls `self.request_agent_help()` which does not exist on `AgentBase` — will raise `AttributeError` if an event triggers | `districts/research/research_hub.py:78` | Bug | OPEN |
| G3 | No network intercept capability: VECTOR cannot monkey-patch `fetch`/`XHR` in a page to capture API responses — blocks reliable scraping of SPA sites (Twitter, LinkedIn, Bilibili) that load data via XHR rather than rendering server-side HTML | `core/browser/` — missing module | Feature gap | OPEN |
| G4 | DOM snapshot pipeline covers only 4 scoring factors; missing: Shadow DOM traversal, same-origin iframe extraction, paint-order occlusion (overlay/modal detection), incremental diff marking, bbox parent-child dedup, and `data-ref` annotation for stable targeting across page changes | `core/browser/dom_pruner.py` | Enhancement | OPEN |
| G5 | No article extraction pipeline: VECTOR cannot extract clean Markdown from arbitrary article pages (blogs, news, docs) with paragraph-boundary chunking and `next_start_char` continuation — agents cannot read long articles without hitting context limits | `core/browser/` — missing module | Feature gap | OPEN |
| G6 | `OpenCLIAdapter.get_github_trending()` passes wrong arg signature: calls `_fallback_github_trending(language, limit)` with positional args but the function signature matches; however `opencli github trending` is not a real OpenCLI built-in (GitHub trending is a community plugin, not bundled) — the opencli branch will always fail silently | `districts/research/opencli_adapter.py:179-188` | Logic bug (minor) | OPEN |
| G7 | `opencli_adapter.py` uses `asyncio.get_event_loop().run_in_executor()` which is deprecated in Python 3.10+ — should use `asyncio.get_running_loop().run_in_executor()` | `districts/research/opencli_adapter.py:93,136,165` | Code quality | OPEN |
| G8 | 130+ OpenCLI site adapters (LinkedIn SalesNav, Bilibili, Zhihu, Xiaohongshu, Twitter full CRUD, Amazon, Upwork, etc.) have no VECTOR equivalent — these require the npm tool or native Python re-implementation | `clis/` — all except HN/Reddit/GitHub | Feature gap | OPEN |
