# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
Its own project metadata names it `mirofish-backend`.
The metadata describes it as: "MiroFish - 简洁通用的群体智能引擎，预测万物".
Its declared license is AGPL-3.0.
That license is stated here as an attribution and visibility notice only; no licensing decision is made by this file.
This tree is not represented as native VECTOR code.
VECTOR uses the `VectorSocialSimEngine` utility from this tree for the simulation route.
Vendored as-is; VECTOR's own code calls into: `core/api/routers/simulation.py`.

## Owner licensing decision (2026-09-24)

Owner reviewed AGPL-3.0's network-use (Affero) clause and decided: continue using this
tree as-is. VECTOR runs as a single-owner personal system, not distributed or offered as
a network service to other users, so the clause's disclosure trigger does not currently
apply. Revisit this decision if VECTOR (or any product built on it) is ever exposed to
users other than the owner over a network.
