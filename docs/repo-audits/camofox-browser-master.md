# camofox-browser-master Audit

**Audited:** 2026-06-02
**Repo version:** 1.11.2 (`@askjo/camofox-browser`)
**VECTOR version:** 1.10.1 (`@askjo/camofox-browser`, vendored in `core/stealth_browser/server/`)
**Delta:** 2 minor versions behind (1.10.1 → 1.11.2)
**License:** MIT

---

## 1. Repo Reality

**What it is:** camofox-browser is a REST API server that wraps [Camoufox](https://camoufox.com) — a Firefox fork that applies anti-bot fingerprint spoofing at the C++ level (`navigator.hardwareConcurrency`, WebGL, AudioContext, WebRTC, screen geometry). It is purpose-built for AI agents that need to browse real websites without being blocked by Cloudflare, Google, or general bot detection.

**Core architecture:**
```
Plugin system (OpenClaw)
    ↓
Express REST API (server.js, 6128 lines)
    ↓
Browser session management (BrowserContext per user, isolated cookies/storage)
    ↓
Camoufox (Firefox + C++ fingerprint patches) via camoufox-js + playwright-core
```

**Session model:**
```
Browser Instance (Camoufox — single process)
└── User Session (BrowserContext) — isolated cookies/localStorage
    ├── Tab Group (sessionKey: "conv1")
    │   ├── Tab (google.com)
    │   └── Tab (github.com)
    └── Tab Group (sessionKey: "conv2")
        └── Tab (amazon.com)
```

Sessions auto-expire (30 min inactivity). Browser shuts down after 5 min with no sessions, relaunches on demand. Oldest tab auto-recycled when per-session limit reached.

**Full capability list:**

| Category | Capability |
|----------|-----------|
| Anti-detection | C++-level Firefox fingerprint spoofing (navigator, WebGL, AudioContext, WebRTC, screen) |
| Element refs | Stable `e1`/`e2`/`e3` references in accessibility snapshots for reliable interaction |
| Snapshot compression | Accessibility tree snapshots ~90% smaller than raw HTML; offset-based pagination for large pages |
| Screenshots | Base64 PNG alongside snapshot (`includeScreenshot=true`) |
| JS evaluation | `POST /tabs/:tabId/evaluate` — execute arbitrary JavaScript in page context |
| Structured extract | `POST /tabs/:tabId/extract` — JSON Schema-driven structured data extraction with `x-ref` mapping |
| Cookie import | Netscape-format cookie injection per session; gated by `CAMOFOX_API_KEY`; path-traversal-safe |
| Session persistence | `~/.camofox/profiles/<hashed-userId>/storage_state.json` — survive browser restarts |
| Session tracing | Playwright trace capture (screenshots + DOM + network + console) per session; list/fetch/delete API |
| Proxy + GeoIP | Simple or backconnect (Decodo/generic); automatic locale/timezone from exit IP |
| Proxy rotation | Round-robin port pool OR backconnect sticky sessions |
| YouTube transcripts | `POST /youtube/transcript` — yt-dlp fast path, browser fallback |
| Search macros | 14 macros: `@google_search`, `@youtube_search`, `@amazon_search`, `@reddit_search`, `@reddit_subreddit`, `@wikipedia_search`, `@twitter_search`, `@yelp_search`, `@spotify_search`, `@netflix_search`, `@linkedin_search`, `@instagram_search`, `@tiktok_search`, `@twitch_search` |
| Download capture | `GET /tabs/:tabId/downloads` — captured file downloads, optional base64 inline |
| DOM image extraction | `GET /tabs/:tabId/images` — `<img>` src/alt list, optional inline data URLs |
| Viewport control | `POST /tabs/:tabId/viewport` — resize page viewport |
| VNC plugin | Interactive login via noVNC; export storage state |
| Session isolation | Separate cookies/localStorage per user |
| Tab lifecycle | Create, list, close, group close, session close |
| Navigation | URL, macro, back/forward/refresh |
| Interaction | Click (ref or CSS), type, press key, scroll |
| Metrics | Prometheus (`/metrics`, `PROMETHEUS_ENABLED=1`) |
| Memory pressure | `/pressure/cleanup` — proactive idle tab GC; automatic browser restart on RSS/native-mem threshold breach |
| Sentry integration | Optional `@sentry/node` error tracking via `SENTRY_DSN` env var (new in 1.11.x) |
| Crash telemetry | Anonymized crash/hang reports to Cloudflare Worker; HMAC-hashed private domains; opt-out |
| Structured logging | JSON log lines with request IDs |
| Access control | `CAMOFOX_ACCESS_KEY` bearer token for all routes; `CAMOFOX_ADMIN_KEY` for `/stop` |
| OpenClaw plugin | 11 tools: `camofox_create_tab`, `camofox_snapshot`, `camofox_click`, `camofox_type`, `camofox_navigate`, `camofox_scroll`, `camofox_screenshot`, `camofox_close_tab`, `camofox_evaluate`, `camofox_list_tabs`, `camofox_import_cookies` |
| Deploy | Docker, Fly.io, Railway; Windows PowerShell builder (`build.ps1`) |
| OpenAPI | Auto-generated spec at `/openapi.json` + interactive docs at `/docs` |

---

## 2. VECTOR Parity

VECTOR's version is vendored at `core/stealth_browser/server/` (1.10.1). VECTOR also has:
- Python client wrapper: `core/stealth_browser/client.py`
- Server manager: `core/stealth_browser/server_manager.py`
- Transcript helper: `core/stealth_browser/transcripts.py`
- Macros helper: `core/stealth_browser/macros.py`

**Version delta confirmed by:**
```
VECTOR stealth version: 1.10.1 name: @askjo/camofox-browser
Repo version:           1.11.2 name: @askjo/camofox-browser
```

| Feature | VECTOR 1.10.1 | Repo 1.11.2 | Status |
|---------|---------------|-------------|--------|
| C++ anti-detection (Camoufox) | Yes | Yes | ✅ Same |
| Element refs / accessibility snapshot | Yes | Yes | ✅ Same |
| Snapshot pagination (offset) | Yes | Yes | ✅ Same |
| Screenshot with snapshot | Yes | Yes | ✅ Same |
| JS evaluation (`/tabs/:tabId/evaluate`) | Yes (line 4340) | Yes (line 4340) | ✅ Same |
| Structured extract (`/tabs/:tabId/extract`) | Yes | Yes | ✅ Same |
| Cookie import (Netscape format) | Yes | Yes | ✅ Same |
| Session persistence | Yes | Yes | ✅ Same |
| Session tracing (Playwright traces) | Yes | Yes | ✅ Same |
| Proxy + GeoIP | Yes | Yes | ✅ Same |
| Backconnect proxy (Decodo/generic) | Yes | Yes | ✅ Same |
| YouTube transcript | Yes | Yes | ✅ Same |
| 14 search macros | Yes | Yes | ✅ Same |
| Download capture | Yes | Yes | ✅ Same |
| DOM image extraction | Yes | Yes | ✅ Same |
| Viewport resize (`/tabs/:tabId/viewport`) | Yes (line 3695) | Yes (line 3730) | ✅ Same |
| VNC plugin | Yes (`server/plugins/vnc/`) | Yes (`plugins/vnc/`) | ✅ Same |
| Prometheus metrics | Yes | Yes | ✅ Same |
| `/pressure/cleanup` | Yes (line 2369) | Yes | ✅ Same |
| Native memory restart (NATIVE_MEM_RESTART) | Yes (line 5042-5068) | Yes | ✅ Same |
| Browser RSS restart (BROWSER_RSS_RESTART) | **No** — single-threshold only | Yes (line 5100-5110) | ❌ Missing |
| Sentry integration (`lib/sentry.js`) | **No** — file absent | Yes — `lib/sentry.js` + `initSentry()` wired in `server.js` | ❌ Missing |
| `sentryDsn` in config | **No** — absent from `lib/config.js` | Yes — line 151 | ❌ Missing |
| `SENTRY_DSN` env var | **No** | Yes | ❌ Missing |
| `bin/camofox-browser.js` CLI entrypoint | **No** — `bin/` not vendored | Yes | ⚠️ Not needed for VECTOR |
| `camofox_evaluate` in OpenClaw plugin | N/A (plugin.js not vendored) | Yes | ⚠️ VECTOR uses Python client, not OpenClaw |
| 11 OpenClaw tools including `camofox_evaluate` | N/A (no plugin.js) | 11 tools in `package.json` | ⚠️ Not applicable |
| Python client — `evaluate()` method | **No** | N/A (JS-only) | ⚠️ Server-side exists; Python client gap |
| Python client — `set_viewport()` method | **No** | N/A (JS-only) | ⚠️ Server-side exists; Python client gap |
| Python client — `extract()` method | **No** | N/A (JS-only) | ⚠️ Server-side exists; Python client gap |
| Python client — `get_downloads()` method | **No** | N/A (JS-only) | ⚠️ Server-side exists; Python client gap |
| Python client — `traces()` methods | **No** | N/A (JS-only) | ⚠️ Server-side exists; Python client gap |
| Anonymized crash telemetry | Yes (reporter.js) | Yes (reporter.js) | ✅ Same |
| `browserProcessTreeRssMb` export | Yes (resources.js line 7) | Yes (resources.js line 32) | ✅ Same |
| OpenAPI docs | Yes | Yes | ✅ Same |
| Access control (`CAMOFOX_ACCESS_KEY`) | Yes | Yes | ✅ Same |
| Structured logging | Yes | Yes | ✅ Same |

**Summary of real gaps (affecting runtime behavior):**

| Gap | Severity | Impact |
|-----|----------|--------|
| `lib/sentry.js` missing + `initSentry()` not wired | Medium | No Sentry error tracking; `SENTRY_DSN` env var silently ignored |
| `browserRssRestartThresholdMb` config missing | Medium | Browser's own RSS pressure not detected; Firefox memory bloat builds undetected when idle |
| `browserRssRestartThresholdMb` check absent in memory restart interval | Medium | Complements the config gap above — the detection code simply doesn't exist |
| Python client missing `evaluate()` | Low | Agents using `client.py` can't execute JS on page; must call REST directly |
| Python client missing `set_viewport()` | Low | Viewport resize not accessible from Python |
| Python client missing `extract()` | Low | Structured JSON Schema extraction not accessible from Python |
| Python client missing `get_downloads()` | Low | Download capture not accessible from Python |
| Python client missing trace management methods | Low | Trace list/fetch/delete not accessible from Python |

---

## 3. Frontend

No frontend in this repo. It is a pure REST API server with:
- `/docs` — Swagger UI (auto-generated from JSDoc `@openapi` annotations via `swagger-jsdoc`)
- `/openapi.json` — machine-readable OpenAPI 3.0 spec
- `plugins/vnc/` — noVNC web UI for interactive browser sessions (optional, `ENABLE_VNC=1`)

The noVNC plugin serves a minimal iframe HTML at the configured `NOVNC_PORT` (default 6080). VECTOR has this vendored at `core/stealth_browser/server/plugins/vnc/`. No gap here.

---

## 4. Verdict

**Decision: Patch delta — do NOT full replace.**

Rationale:
1. VECTOR's vendor copy is 1.10.1. The repo is 1.11.2. The delta is exactly 69 lines in `server.js` (6059 VECTOR vs 6128 repo) and one new file (`lib/sentry.js`).
2. **All core functionality is present.** Tab management, snapshots, element refs, JS eval, structured extract, cookies, proxies, traces, downloads, images, macros, YouTube transcripts — all identical between versions.
3. The 1.11.x delta adds: (a) optional Sentry integration (zero-impact if `SENTRY_DSN` unset), and (b) browser RSS memory restart threshold (Linux-only, production hardening for long-running deployments).
4. VECTOR runs on Windows (Legion Pro 5 + RTX 5070 Ti). The `browserRssRestartThresholdMb` logic reads `/proc/<pid>/status` which is Linux-only. `browserProcessTreeRssMb()` already returns `null` on non-Linux (`process.platform !== 'linux'`). The check becomes a no-op on Windows. **Not urgent for local dev.**
5. Sentry is optional and disabled by default. Not urgent.
6. The Python client gaps are real but low priority — all server endpoints already exist in VECTOR's server.js, just not wrapped in `client.py`.

**Upgrade path:** patch, not replace. Copy 3 diffs, add 5 Python methods. 2–3 hours total.

---

## 5. Gaps — Exact Files/Lines to Patch

### Gap 1: Add `lib/sentry.js` (new file)

**Action:** Copy the file verbatim from repo to VECTOR.

- Source: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\camofox-browser-master\lib\sentry.js`
- Destination: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\stealth_browser\server\lib\sentry.js`

The file is 73 lines. It does a guarded dynamic `import('@sentry/node')` — if the package isn't installed, it silently disables itself. Zero risk to add.

### Gap 2: Wire Sentry into `server.js`

**Action:** Apply two-line patch to `core/stealth_browser/server/server.js`.

In VECTOR's `server.js`, the import block (lines 36–38) currently reads:
```js
import { createReporter, createTabHealthTracker, collectResourceSnapshot, classifyProxyError } from './lib/reporter.js';
import { mountDocs } from './lib/openapi.js';
import { prepareExternalCamoufoxExecutable } from './lib/camoufox-executable.js';
```

Change to:
```js
import { createReporter, createTabHealthTracker, collectResourceSnapshot, classifyProxyError, browserProcessTreeRssMb } from './lib/reporter.js';
import { mountDocs } from './lib/openapi.js';
import { initSentry, captureException as sentryCaptureException, setupExpressErrorHandler as setupSentryErrorHandler, flush as sentryFlush } from './lib/sentry.js';
import { prepareExternalCamoufoxExecutable } from './lib/camoufox-executable.js';
```

Then after the reporter is created (line 45 in VECTOR: `const reporter = createReporter(...)`), add:
```js
// --- Sentry error tracking ---
initSentry({ ...CONFIG, version: _pkgVersion });
```

Reference: repo `server.js` lines 38 and 48.

### Gap 3: Add `sentryDsn` to `lib/config.js`

**Action:** One-line addition to `core/stealth_browser/server/lib/config.js`.

At the end of the `loadConfig()` return object (currently ends at `crashReporterConfig: readCrashReporterConfig(),`), add:
```js
sentryDsn: process.env.SENTRY_DSN || '',
```

Reference: repo `lib/config.js` line 151.

### Gap 4: Add browser RSS restart threshold to `lib/config.js`

**Action:** One-line addition inside `loadConfig()` return object.

After `nativeMemRestartThresholdMb: parseInt(process.env.NATIVE_MEM_RESTART_THRESHOLD_MB) || 300,` (VECTOR line 94), add:
```js
browserRssRestartThresholdMb: parseInt(process.env.BROWSER_RSS_RESTART_THRESHOLD_MB) || 1500,
```

Reference: repo `lib/config.js` line 95.

### Gap 5: Add browser RSS restart check to `server.js`

**Action:** Expand the existing memory pressure `setInterval` (VECTOR lines 5049–5070).

Current VECTOR code only checks native Node memory growth. Add a browser RSS check at the top of the interval (after `const nativeMemMb = ...` and before the baseline check), matching repo lines 5098–5110:

```js
const browserRssMb = browserProcessTreeRssMb(_browserPid());

if (browserRssMb !== null && browserRssMb >= CONFIG.browserRssRestartThresholdMb) {
  log('warn', 'browser rss pressure, restarting browser', {
    browserRssMb,
    thresholdMb: CONFIG.browserRssRestartThresholdMb,
  });
  browserRestartsTotal.labels('browser_rss_pressure').inc();
  closeBrowserFully('browser_rss_pressure').catch((err) => {
    log('error', 'browser rss pressure browser close failed', { error: err.message });
  });
  return;
}
```

Note: `browserProcessTreeRssMb` is already exported from `resources.js` and imported in VECTOR's `reporter.js`. Needs to be re-exported or directly imported in `server.js`. Repo's `server.js` imports it directly from `./lib/reporter.js` (which re-exports it from `resources.js`).

### Gap 6 (Optional): Add 5 missing methods to `client.py`

**File:** `core/stealth_browser/client.py`

Add after the `wait()` method (line 261) and before the YouTube section:

```python
async def evaluate(self, tab_id: str, expression: str) -> dict:
    """Execute JavaScript in a tab's page context."""
    c = await self._ensure_client()
    r = await c.post(
        f"{self._base}/tabs/{tab_id}/evaluate",
        json={"expression": expression},
        headers=self._headers(),
    )
    r.raise_for_status()
    return r.json()

async def set_viewport(self, tab_id: str, width: int, height: int) -> dict:
    """Resize the tab viewport."""
    c = await self._ensure_client()
    r = await c.post(
        f"{self._base}/tabs/{tab_id}/viewport",
        json={"width": width, "height": height},
        headers=self._headers(),
    )
    r.raise_for_status()
    return r.json()

async def extract(self, tab_id: str, schema: dict) -> dict:
    """Structured data extraction via JSON Schema with x-ref mapping."""
    c = await self._ensure_client()
    r = await c.post(
        f"{self._base}/tabs/{tab_id}/extract",
        json={"schema": schema},
        headers=self._headers(),
    )
    r.raise_for_status()
    return r.json()

async def get_downloads(self, tab_id: str, inline: bool = False) -> list[dict]:
    """List captured file downloads for a tab."""
    c = await self._ensure_client()
    r = await c.get(
        f"{self._base}/tabs/{tab_id}/downloads",
        params={"includeData": "true" if inline else "false"},
        headers=self._headers(),
    )
    r.raise_for_status()
    return r.json().get("downloads", [])

async def list_traces(self, user_id: str = "vector") -> list[dict]:
    """List Playwright trace files for a user session."""
    c = await self._ensure_client()
    r = await c.get(f"{self._base}/sessions/{user_id}/traces", headers=self._headers())
    r.raise_for_status()
    return r.json().get("traces", [])
```

### Priority Order

| Priority | Gap | Reason |
|----------|-----|--------|
| 1 | Gap 4 + Gap 5 (browser RSS restart) | Production reliability; Firefox memory bloat is real on long-running sessions; config + logic must be added together |
| 2 | Gap 1 + Gap 2 + Gap 3 (Sentry) | Optional but production-grade error tracking; zero install risk if `SENTRY_DSN` unset |
| 3 | Gap 6 (Python client methods) | Quality of life; agents calling REST directly still work |

### Files to Touch (summary)

| File | Change |
|------|--------|
| `core/stealth_browser/server/lib/sentry.js` | CREATE — copy verbatim from repo |
| `core/stealth_browser/server/lib/config.js` | ADD 2 lines: `sentryDsn` + `browserRssRestartThresholdMb` |
| `core/stealth_browser/server/server.js` | ADD sentry import + `initSentry()` call; ADD browser RSS check in memory interval |
| `core/stealth_browser/client.py` | ADD 5 async methods: `evaluate`, `set_viewport`, `extract`, `get_downloads`, `list_traces` |
