# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
Its structure suggests the open-source local-deep-research project, but that exact origin is unconfirmed.
No root README, LICENSE, or `pyproject.toml` naming an upstream project was found in this vendored tree.
This notice therefore does not assert an exact upstream project name.
The tree includes research, citation, journal-quality, web-search, and database-migration components.
VECTOR uses selected research utilities rather than treating the full tree as native VECTOR code.
Confirmed utilities include `create_settings_snapshot`, `quick_summary`, `generate_report`, and `analyze_documents`.
Vendored as-is; VECTOR's own code calls into: `districts/research/research_api.py` and `core/loop/autonomous_loop.py`.
