# Task 09 — Venture pipeline first live run

- **Depends on:** Task 08 (or run manually any time)
- **Who:** OWNER trigger
- **Effort:** ~10 min (mostly network)

## Objective

The side-hustle discovery pipeline produces its first real report from 30 days
of Reddit + HN; afterwards the Monday 07:00 cron owns it.

## Implementation

```
python districts/news_trends/venture_pipeline.py --live
```

## Tests

`data/venture/` gains `clusters_*.json` + `venture_report_*.md`;
`GET /startups/ventures/latest` serves them.

## Demo

Ventures widget on the HUD shows ranked problem clusters.

## Acceptance

- [ ] Report generated with non-empty clusters
- [ ] HUD ventures widget renders it
- [ ] Weekly cron remains scheduled (no manual rerun needed)
