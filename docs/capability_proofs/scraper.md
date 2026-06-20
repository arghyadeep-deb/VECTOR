# Capability Proof — scraper

**Verdict: BROKEN**

Run at: 2026-06-20T12:33:31.127315+00:00 (corrected after manual follow-up — see below)

## Output (verbatim, from the automated probe)

```
{'status_code': 200, 'content_len': 0, 'url': 'https://example.com'}
```

The automated probe's classifier initially mis-scored this as LIVE — `status_code`
being non-empty/non-zero satisfied its "meaningful output" check even though the
actually-important field (`content_len`) was 0. Flagging this as a classifier gap
(noted below); the real finding came from manual follow-up.

## Root cause (isolated by hand)

`VectorScraper.fetch()` (`core/scraper/vector_scraper.py:152`) does:

```python
content = resp.text if hasattr(resp, 'text') else str(resp)
```

Direct reproduction against the real underlying fetcher
(`core.scraper.fetchers.AsyncFetcher` → `core.scraper.engines.toolbelt.custom.Response`)
shows the network layer works perfectly — it's the attribute access that's wrong:

```
status: 200
body len: 559          <- real HTML bytes, fetch genuinely succeeded
html_content len: 543  <- real parsed HTML
text len: 0            <- what vector_scraper.py actually reads — empty
```

`resp.text` returns an empty `TextHandler` for a real, successfully-fetched page.
`resp.html_content` (or equivalent extracted-text accessor) has the real content.
Every call to `VectorScraper.fetch()` / `quick_fetch()` / `fetch_to_markdown()`
returns status 200 with empty `content`/`html`/`markdown` — the HTTP layer works,
but nothing usable comes back to the caller. This affects any district relying on
`vector_scraper` (web_scout, research agents) — they'd see "success" with no data.

## Fix (scoped, not yet applied — Phase 0 is investigate-only)

In `core/scraper/vector_scraper.py:152` and the 3 other `ScrapeResult(...)`
construction sites (`fetch_stealth`, `fetch_dynamic` — lines ~215, ~269), replace
`resp.text` with `resp.html_content` (or `resp.get_all_text()` if plain-text
extraction is wanted instead of raw HTML). Needs its own fix sub-task before this
capability can be made autonomous, per Phase 0's triage gate.

## Unrelated but real finding surfaced during this probe

A separate `ImportError: cannot import name 'BeartypeConf' from 'beartype'` fires on
every run (from `fastmcp` → `key_value.aio` → `beartype`, triggered by `core/__init__.py`
eagerly importing optional sub-packages). It does not crash the process — something
catches it — but it fires unconditionally on every cold import of `core`. Worth a
separate look; out of scope for this capability's verdict.
