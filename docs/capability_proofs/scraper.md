# Capability Proof — scraper

**Verdict: LIVE**

Run at: 2026-06-20T12:55:53.844912+00:00 (after Task 0.5a fix)

## Output (verbatim)

```
{'status_code': 200, 'content_len': 543, 'url': 'https://example.com'}
```

`content_len` went from 0 (Phase 0 finding) to 543 — matches the real
`html_content` length measured by hand during root-cause investigation.

## Fix applied (Task 0.5a)

`core/scraper/vector_scraper.py` — all 3 `ScrapeResult` construction sites
(`fetch`, `fetch_stealth`, `fetch_dynamic`) read `resp.text` (always empty
for scrapling's `Response` object) instead of `resp.html_content` (has the
real fetched markup). Fixed `content=` and `html=` assignments at all 3
sites to prefer `html_content`, falling back to `.text`/`str(resp)` for
fetcher types that don't expose it.

Regression test: `tests/integration/test_capability_live.py::test_scraper_fetch_returns_real_content`
(`@pytest.mark.live`) — asserts real content length and "Example Domain"
text are present in the fetched page. Passes.
