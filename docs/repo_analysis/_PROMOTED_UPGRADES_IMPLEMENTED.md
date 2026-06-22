# Promoted Repo Upgrades - First Implementation Slice

**Date:** 2026-06-22

This implements the first safe VECTOR-native slice from the SOC crosscheck promotions:

- Auto Browser
- Crawl4AI
- Headroom
- Competitor X-Ray
- last30days

No external repo code was copied. The upgrade adds small contracts and safety layers that Sonnet can now build on.

## Implemented

### 1. Auto Browser Governance

Added:

- `core/browser/governance.py`

Capabilities:

- classifies browser actions as GREEN/YELLOW/RED/UNKNOWN
- blocks obvious high-risk browser actions by default
- creates browser action receipts
- hashes screenshots instead of storing raw image data
- redacts visible text using existing browser PII scrubber

Wired into:

- `core/vision_control/browser_controller.py`
- `core/mcp_tools/browser.py`

Next:

- connect high-risk browser actions to full PermissionGateway owner approval flow
- add persistent receipt storage for browser sessions
- add human-takeover state to browser task results

### 2. Crawl4AI-Style Extraction Contract

Added:

- `core/research_engine/content_fetcher/extraction.py`

Capabilities:

- clean HTML/Markdown normalization
- link extraction
- content hash
- fetch timestamp
- query-focused pruning
- `WebExtractionArtifact` contract

Wired into:

- `core/research_engine/content_fetcher/fetcher.py`

Also fixed:

- `core/research_engine/content_fetcher/__init__.py` now lazy-loads `ContentFetcher`, so lightweight extraction imports do not require optional PDF dependencies.

Next:

- add optional Crawl4AI provider adapter behind this artifact contract
- add SSRF/rate-limit tests for live web extraction path
- store extraction artifacts in research library

### 3. Headroom-Style Context Budget

Added:

- `districts/memory_curator/context_budget.py`

Capabilities:

- deterministic oversized message compaction
- retrieval handles
- SHA-256 content hashes
- in-memory original retrieval for first slice
- token/character savings stats

Next:

- persist handles to SQLite/episodic memory
- wire before provider calls
- add budget telemetry per provider/task

### 4. Competitor X-Ray Workflow Contract

Added:

- `districts/marketing/competitor_xray.py`

Capabilities:

- target normalization
- evidence-tiered claims: CONFIRMED / REPORTED / INFERRED / NOT_FOUND
- competitor brief schema
- threat scoring and ranking

Next:

- wire into `CompetitorIntelAgent`
- feed it with existing research/search results
- add Markdown/CSV/PDF export later

### 5. last30days Recency Contract

Added:

- `districts/research/last30days.py`

Capabilities:

- recent signal schema
- recency/engagement/confidence scoring
- degraded-source reporting
- ranked brief output

Next:

- add vetted connectors only after SkillSpector
- connect to Reddit/HN/GitHub/YouTube/search sources
- persist source timestamps and confidence

## Tests Added

Added:

- `tests/backend/test_promoted_repo_upgrades.py`

Validated:

- high-risk browser actions are blocked
- browser receipts hash screenshots and redact visible PII
- `BrowserController` checks governance before execution
- extraction artifacts clean HTML and track hashes
- context budget creates retrieval handles
- competitor x-ray normalizes/ranks
- last30days ranks recent signals first

## Verification

Passed:

```powershell
python -m pytest -q tests\backend\test_promoted_repo_upgrades.py
python -m pytest -q tests\test_browser_absorption.py
```

## Important Boundaries

- This is not a bulk absorption of Auto Browser, Crawl4AI, Headroom, Competitor X-Ray, or last30days.
- It is the VECTOR-native substrate for those capabilities.
- Live crawling, social connectors, and full browser sidecar integration still require explicit follow-up work and SkillSpector/quarantine where external skill text is involved.

