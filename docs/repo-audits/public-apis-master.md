# Repo Audit — `public-apis-master`

**Audited:** 2026-06-01
**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\public-apis-master`
**Upstream:** [public-apis/public-apis](https://github.com/public-apis/public-apis) — the famous "huge list of free public APIs" (~340k★)
**Verdict (1-liner):** Data-only reference repo. VECTOR already absorbed it (`districts/research/api_catalog.py` + 2 wired call sites). This particular checkout is a **broken partial** (catalog README missing) AND the absorbed scanner points to a **different, now-missing** checkout. **DELETE-NOW** the audited dir; separately fix the dangling path in VECTOR.

---

## Section 1 — Repo Reality

public-apis is, in its normal form, a single giant `README.md` catalog: **~50 categories** (Animals, Weather, Finance, Cryptocurrency, Machine Learning, News, Government, Geocoding, etc.) listing **~1,400+ free public APIs**, each as a markdown table row:

```
| API | Description | Auth | HTTPS | CORS | Call this API |
```

Plus a small Python tooling layer that validates the markdown (alphabetical order, 100-char description cap, valid Auth/HTTPS/CORS enum values, link liveness). **It is DATA, not an app** — a reference catalog with a CI linter bolted on.

### What's actually in THIS checkout (the audited dir)

| Item | Present? | Notes |
|------|----------|-------|
| `README.md` (the catalog itself) | ❌ **MISSING** | The entire reason the repo exists is absent here |
| `CONTRIBUTING.md` | ✅ | Formatting rules, Auth/CORS enums, PR guidelines |
| `LICENSE` | ✅ | MIT |
| `.gitignore`, `.gitattributes` | ✅ | — |
| `scripts/validate/format.py` | ✅ | Markdown table linter (~280 LOC): alphabetical order, column padding, desc ≤100 chars, Auth/HTTPS/CORS enum check |
| `scripts/validate/links.py` | ✅ | Link extractor + (in full version) liveness checker via `requests` |
| `scripts/tests/` | ✅ | pytest for the two validators |
| `scripts/github_pull_request.sh` | ✅ | CI helper |
| `.git/` | ❌ | Not a git repo — flat extracted copy |

**Net:** this is a **gutted checkout** — the catalog (the only valuable artifact) was never extracted. What remains is the linter that validates a file that isn't here. The scripts are useless without the README they lint. Total useful payload in this dir: **zero** (the linter only matters to upstream contributors maintaining the catalog).

---

## Section 2 — VECTOR Parity

### Finding 1 — `docs/public_apis.md` is NOT this catalog (different, much smaller thing) ⚠️→✅

`docs/public_apis.md` (120 lines) is a **hand-curated VECTOR-specific** list of ~50 zero-key APIs grouped **by VECTOR district** (Research, Investment, News, Comms, Content, Voice, Sensing, GitHub), with a "What VECTOR uses it for" column. Examples: DuckDuckGo IA, HN Firebase, ArXiv, CoinGecko, Yahoo Finance v8 (NSE `.NS`), OpenAQ, IP-API.

> **This is original VECTOR content, not derived from public-apis.** Different schema (district-oriented + usage notes vs. category-oriented Auth/HTTPS/CORS), different scope (~50 curated-for-VECTOR vs. ~1,400 generic). **Verdict: ✅ VECTOR has + uses it** — it's the operational shortlist VECTOR's districts actually call.

### Finding 2 — VECTOR ALREADY absorbed the full public-apis catalog ✅ (code) / ❌ (data path broken)

`districts/research/api_catalog.py` is a **purpose-built scanner** for the full public-apis README:

```python
# districts/research/api_catalog.py:4-15
"""Parses the public-apis README.md to build a searchable catalog of 1000+ free APIs.
ResearchHub uses this to auto-discover data sources for any research topic."""
_README = Path(__file__).parent.parent.parent.parent.parent / \
    "GitHub/public-apis_public-apis/repo/README.md"
```

It exposes `search_apis(query, category, free_only, limit)` and `get_stats()`. It is **wired into two live call sites**:

```python
# core/mcp_server.py:398-414  — MCP tool exposed to all VECTOR agents
@mcp.tool
def find_public_api(query, category="", free_only=True) -> str:
    """Search the public-apis catalog (1000+ free APIs) to find data sources..."""
    from districts.research.api_catalog import search_apis, get_stats
```

```python
# districts/research/research_hub.py:855-862  — ResearchHub "find_api" op
if t in ("find_api", "discover_api", "api_catalog"):
    from districts.research.api_catalog import search_apis
    results = search_apis(p.get("query", ""), p.get("category", ""), ...)
```

> **Verdict: ✅ VECTOR has + uses the catalog concept** — research district draws on it for data-source discovery, exposed as an MCP tool. The absorption already happened in a prior session.

### Finding 3 — BOTH public-apis checkouts referenced by VECTOR are missing ❌ (live bug)

- `api_catalog.py` reads `GitHub/public-apis_public-apis/repo/README.md` → **does not exist** (only dir present is `public-apis-master`, and that has no README either).
- Confirmed: `find ... GitHub/*public*` returns only `public-apis-master`; no README catalog exists anywhere under `GitHub/`.

Consequence: `_load_catalog()` hits its guard, logs `[PublicAPIs] README not found`, and returns `[]`. So `find_public_api` and ResearchHub `find_api` **silently return "0 APIs"** today. The wiring is real; the data is gone. Graceful (no crash) but the feature is **dead**.

| Item | Verdict |
|------|---------|
| District-level operational API shortlist (`docs/public_apis.md`) | ✅ Has + uses (VECTOR-original, not from this repo) |
| Full searchable catalog scanner (`api_catalog.py`) | ✅ Wired (MCP tool + ResearchHub op) |
| The catalog **data** the scanner needs | ❌ Missing — both expected README paths absent → scanner returns `[]` |
| The audited `public-apis-master` dir as a source for that data | ❌ Useless — it too lacks the README |

**Would the research/finance/news districts benefit from the full catalog?** Marginally. ResearchHub already hard-codes its actual sources (DuckDuckGo, HN, ArXiv, CoinGecko, Yahoo Finance — see `docs/public_apis.md`). The 1,400-API catalog is a nice "data-source discovery" lookup for novel topics, but it's a static reference; VECTOR doesn't depend on it for any core loop. The benefit is **a working `find_public_api` tool**, which requires the README — **not** this gutted checkout.

---

## Section 3 — Frontend

**None.** public-apis is a markdown catalog + a Python CLI linter. No web UI, no dashboard, no server, no frontend of any kind. (Upstream has a community-built browser at `api.publicapis.org`, but that is a separate project not present here.) Nothing to design-review.

---

## Section 4 — Verdict + Delete-Readiness

### The audited dir: `public-apis-master`

**SAFE TO DELETE → DELETE-NOW.**

Reasons:
1. It is a **broken partial checkout** — the catalog README (the only valuable artifact) is missing. What remains is a markdown linter that lints a file that isn't here.
2. VECTOR **already absorbed** the catalog concept in code (`api_catalog.py` + MCP tool + ResearchHub op). Nothing in this dir is referenced by VECTOR — `api_catalog.py` points at a *different* path (`public-apis_public-apis/repo/`), not `public-apis-master/`.
3. The validators (`format.py`, `links.py`) are upstream-contributor tooling for maintaining the catalog markdown — zero value to VECTOR, which doesn't author or host the catalog.
4. VECTOR's own `docs/public_apis.md` (the district shortlist) is original and unaffected.

Deleting this dir costs VECTOR **nothing** — it is not the source `api_catalog.py` reads, and even if it were, it has no README to read.

### Separate follow-up (NOT part of deleting this dir — flagged, not actioned per constraints)

VECTOR has a **dangling-path bug**: `api_catalog.py:14-15` and the `find_public_api` MCP tool point to `GitHub/public-apis_public-apis/repo/README.md`, which doesn't exist → `search_apis()` returns `[]` today. To restore the feature, re-clone the real public-apis catalog README to that path (or repoint the constant to a valid copy). This is independent of the audited dir and is a one-line fix + one data file; I did **not** modify any VECTOR code per the audit constraints.

### Tracker

| Target | Semantics | Action |
|--------|-----------|--------|
| `GitHub/public-apis-master/` (audited dir) | **DELETE-NOW** | Gutted partial, zero VECTOR references, not the path `api_catalog.py` reads |
| `api_catalog.py` dangling README path | **KEEP (code) + FIX (data)** | Wiring is good; restore the catalog README at the expected path to revive `find_public_api` |
| `docs/public_apis.md` | **KEEP** | VECTOR-original district shortlist, in active use |

---

### Honest bottom line

This checkout is **safe to delete right now** — it's the dead skin of an already-absorbed repo. The only real takeaway is a pre-existing VECTOR bug: the catalog scanner points at a README that's missing, so `find_public_api` returns nothing. Deleting `public-apis-master/` doesn't cause that bug (it predates it) and doesn't fix it (wrong path) — but it does remove a misleading duplicate that someone might mistake for the scanner's source.
