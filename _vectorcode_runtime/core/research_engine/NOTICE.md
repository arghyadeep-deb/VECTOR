# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
**Confirmed upstream (2026-10-12):** LearningCircuit's `local-deep-research` project.
License: MIT, Copyright (c) 2025 LearningCircuit — see `core/research_engine/LICENSE`.
`scripts/absorb_research_engine.py` (retired 2026-09-24) documents the absorption from
`GitHub/local-deep-research/src/local_deep_research`; `THIRD_PARTY_NOTICES.md` records the
same attribution centrally.
The tree includes research, citation, journal-quality, web-search, and database-migration components.
VECTOR uses selected research utilities rather than treating the full tree as native VECTOR code.
Confirmed utilities include `create_settings_snapshot`, `quick_summary`, `generate_report`, and `analyze_documents`.
Vendored as-is; VECTOR's own code calls into: `districts/research/research_api.py` and `core/loop/autonomous_loop.py`.

## Owner disposition (2026-10-12)

Option (3), reachability/privilege-boundary review — standing policy, confirmed.
See `docs/design/investigation-2026-10-12-research-engine-origin.md` for the full
provenance investigation.
