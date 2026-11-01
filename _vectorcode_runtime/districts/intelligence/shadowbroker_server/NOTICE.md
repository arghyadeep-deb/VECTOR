# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
**Confirmed upstream (2026-10-12):** `BigBodyCobain/Shadowbroker`.
License: **AGPL-3.0** (per upstream's root `LICENSE` and `DATA-ATTRIBUTION.md`).
In-tree markers: `services/geocode.py` sets its user agent to
`ShadowBroker/1.0 (https://github.com/BigBodyCobain/Shadowbroker)`; `tests/test_gdelt_updater_hardening.py`
constructs codeload/release/API URLs for the same repo.
The upstream AGPL-3.0 license text is restored locally at `LICENSE` in this directory
(2026-10-13).
This notice does not represent the backend as native VECTOR code.
VECTOR starts its `main.py` process and provides a proxy route to that process.
Those are integration points, not a claim that all backend functionality is used.
Vendored as-is; VECTOR's own code calls into: `run_vector.py` and `core/api/routers/sb.py`.

## Owner disposition (2026-10-12)

Option (2), pinned external dependency — treat as an explicit upstream fork/pin: record
the exact upstream revision when recoverable, preserve the AGPL-3.0 license and data
attributions once the license text is restored, maintain a local-patch ledger, and monitor
upstream/security updates. VECTOR is a single-owner personal system, not distributed or
offered as a network service to other users (same basis as the `vector_social_sim` AGPL
acceptance) — revisit if VECTOR is ever exposed to other users over a network.
See `docs/design/investigation-2026-10-12-shadowbroker-server-origin.md` for the full
provenance investigation.
