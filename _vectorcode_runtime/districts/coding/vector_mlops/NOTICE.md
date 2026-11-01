# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
**Confirmed upstream (2026-10-12):** Hugging Face's `smolagents/ml-intern` project.
License: **Apache License 2.0** (per upstream's root `LICENSE`; restored locally at
`LICENSE` in this directory, 2026-10-13).
Local `agent/README.md` matches upstream's queue/event architecture, `agent_loop.py`,
session/context manager, tool router, and LiteLLM design; local prompts say "You are
Hugging Face Agent" and cover HF docs/datasets/repos/papers/cloud jobs/Trackio/sandboxing/
planning/GitHub examples — the same tool surface as upstream.
It also contains a separate FastAPI backend for authentication, sessions, and quotas.
VECTOR does not call that separate backend.
VECTOR uses selected agent utilities including dataset inspection, GitHub examples, Hugging Face jobs, and planning tools.
The integration isolates the vendored `agent` namespace while loading those utilities.
Vendored as-is; VECTOR's own code calls into: `districts/coding/mlops_agent.py`.

## Owner disposition (2026-10-12)

Option (4), full-depth review — already performed in practice (commit `63d7a6e44`,
2026-10-07 full-depth coding-district audit: fixed OAuth CSRF expiry, secret-storage
bypasses, path confinement, and session atomicity in this tree). This notice formalizes
that this component sits at the full-depth tier, not the standard wiring-check tier.
See `docs/design/investigation-2026-10-12-vector-mlops-origin.md` for the full
provenance investigation.
