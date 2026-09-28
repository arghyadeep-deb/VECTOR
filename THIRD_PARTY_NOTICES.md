# Third-Party Notices

VECTOR contains code from other open-source projects. This file records what
is known about each, and where its license text lives. Compiled 2026-09-24
(external-review Phase 7). Upstream licenses/copyright lines below were
checked against the upstream repositories' `LICENSE` pages on that date;
anything not checked says so. **Do not strip or rewrite upstream attribution
from these trees** — `scripts/deabsorb.py`, `scripts/absorb_research_engine.py`
and `scripts/absorb_coding_assistant.py` did exactly that and are now retired
(they exit immediately).

## Vendored trees

| Path | Upstream | License | Copyright | License file |
|---|---|---|---|---|
| `core/research_engine/` | local-deep-research (LearningCircuit) — named in `scripts/absorb_research_engine.py` | MIT | 2025 LearningCircuit | `core/research_engine/LICENSE` |
| `core/coding_assistant/` | mistral-vibe (Mistral AI) — named in `scripts/absorb_coding_assistant.py` | Apache-2.0 | 2025 Mistral AI | `core/coding_assistant/LICENSE` |
| `vectorcode/` (agent core) | Nous Research `hermes-agent` (`default_soul.py`, `nous_*` modules, `vectorcode/docs/absorption/`) | MIT | 2025 Nous Research | `vectorcode/LICENSES/MIT-NousResearch-hermes-agent.txt` |
| `vectorcode/` (orchestration/neural parts) | ruvnet `ruflo` (per `docs/phase_status.md`) | MIT | 2024-2026 ruvnet | `vectorcode/LICENSES/MIT-ruvnet-ruflo.txt` |
| `vectorcode/` (SDK/eval parts) | OpenJarvis (per `docs/phase_status.md`) | Apache-2.0 | 2025 The OpenJarvis Authors | `vectorcode/LICENSES/Apache-2.0-OpenJarvis.txt` |
| `core/training/openmythos/vendor/` | OpenMythos (Kye Gomez) — its own README states the license | MIT | 2026 Kye Gomez (per its README) | `core/training/openmythos/vendor/LICENSE` |
| `districts/investment/alpha_zoo/` | factor library; 154 file headers say "Apache-2.0, Copyright (c) Microsoft Corporation" (looks Qlib-derived — upstream repo not confirmed) | Apache-2.0 | Microsoft Corporation (per file headers) | `districts/investment/alpha_zoo/LICENSE` |
| `districts/investment/vector_finagent/` | Fincept Terminal | **Mixed — see copyleft below** | Fincept Corporation | `districts/investment/vector_finagent/LICENSE-AGPL-3.0.txt` |
| `districts/intelligence/vector_social_sim/` | MiroFish (`mirofish-backend`) | **AGPL-3.0** | (see copyleft below) | not present locally; standard AGPL-3.0 text, restore from upstream |

Per-tree `NOTICE.md` files (written by an earlier audit, deliberately not
asserting upstream names they could not confirm) also exist in:
`core/research_engine/`, `core/coding_assistant/`, `districts/coding/vector_mlops/`,
`districts/intelligence/shadowbroker_server/`, `districts/investment/{alpha_zoo,vector_backtest,vector_finagent}/`,
`districts/intelligence/vector_social_sim/`.

## Copyleft flags (need owner awareness)

1. **`vector_finagent` — AGPL-3.0-or-later (Fincept Corporation).** The tree's
   own installer license (`qt/packaging/.../license.txt`) is the AGPL-3.0, and
   the C++/Qt application under `qt/` appears to be AGPL-licensed too (inferred from that file). The Python scripts library's
   README declares MIT (per the existing `NOTICE.md`). **419 Python files carry a
   header claiming `Licensed under the MIT License. Copyright (c) 2024-2026 VECTOR`.**
   That header was an inaccurate attribution for code derived from Fincept's project
   (MIT also requires keeping the original copyright notice). **Fixed 2026-09-24:** all 418
   files now read "Derived from Fincept Terminal (Fincept Corporation) -- see
   THIRD_PARTY_NOTICES.md / Adapted for VECTOR (owner's personal-use build)"
   (`scripts/normalize_finagent_headers.py`, comment-only, bytecode verified unchanged).
   Owner direction: personal-use build, keep the tree.
2. **`vector_social_sim` — AGPL-3.0 (MiroFish).** Owner decision 2026-09-24
   (recorded in its `NOTICE.md`): keep using as-is; single-owner, no network
   exposure to other users. Revisit if VECTOR is ever exposed to other users.
3. **Not checked:** `core/mining/` (Pearl miner modules), `districts/intelligence/shadowbroker_server/`,
   `districts/investment/vector_backtest/`, `districts/investment/vector_hedgebot/`,
   `districts/coding/vector_mlops/` — no upstream project or license is declared inside these
   trees (see their `NOTICE.md`). Their licenses are unknown, so treat them as
   all-rights-reserved until identified.

## Reimplementations (no code copied, per project docs)

`docs/phase_status.md` records these as clean-room Python reimplementations of
ideas from other projects: nango (Elastic License 2.0), postiz-app (AGPL-3.0),
OpenWA, auto-browser, voicebox, pocketbase, Understand-Anything,
jcode, openhuman, openfang (upstream licenses other than nango/postiz as recorded in that file were not checked). **Not verified in this review** — if any of them
actually contain copied code, the corresponding license terms apply; the
ELv2 and AGPL ones in particular would matter.

## Other

- `.claude/skills/*` and `vectorcode/skills/*` carry their own `LICENSE` files; leave them in place.
- `vectorcode/src/vector_cli/default_soul.py` still says "created by Nous Research"
  in its system prompt. That is accurate attribution of the origin but odd as
  runtime identity text — owner decision whether to reword it (keep the credit here).
- `mattpocock/skills` (MIT) was copied into `~/.claude/skills/` by `scripts/absorb_skills.py`
  — outside this repository; keep its license files.
