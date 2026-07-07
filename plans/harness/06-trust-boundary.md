# Harness Analysis 06 — Trust Boundary
> 2026-07-07, Fable 5. Autonomous vs approval-gated; over-granted vs fear-withheld.

## The trust machinery (ground truth — I built the trust ladder)
- **Permission gateway** (`core/loop/permission_gateway.py`): GREEN (auto),
  YELLOW (owner-confirm, 10s window), RED (owner-approval-always via Pushover),
  FORBIDDEN (blocked). LLM has ZERO direct action access.
- **Trust ladder** (`core/loop/trust_ladder.py`): a YELLOW action auto-promotes
  to GREEN after 20 consecutive explicit approvals with zero failures; any
  rejection/failure demotes it instantly. RED/FORBIDDEN NEVER promote.
- Tier assignment: `core/config.py` CONFIG["permission"] green/yellow/red lists.

## Where authority is MIS-calibrated (findings)

### Over-granted (agent has authority it shouldn't, or gate is too loose)
1. **`run_shell_command` / pc_controller shell is YELLOW with a 10ms pytest
   auto-confirm and `VECTOR_YELLOW_AUTO_CONFIRM` env.** Arbitrary shell at YELLOW
   is high-blast-radius; consider RED for shell that isn't an allowlisted command.
2. **Trust ladder can promote broad YELLOW actions to GREEN.** Good for
   `set_reminder`; risky if a coarse action type (e.g. `run_shell_command`)
   promotes. FIX: exclude high-blast-radius action types from ladder promotion
   (a denylist), even though they're YELLOW.
3. **GREEN includes UI/widget + some "read" actions that touch external services**
   (search_web hits DuckDuckGo). Fine, but confirm no GREEN action mutates
   external state.

### Fear-withheld (owner pays for withholding authority)
1. **VECTOR isn't running at all** — the ultimate withheld authority. Every
   capability is gated behind "not turned on." The single highest-value trust
   move is to LET IT RUN (install service) and let the trust ladder earn
   autonomy over weeks. The whole ladder is designed for exactly this and can't
   function until VECTOR runs.
2. **Feature flags were off** (now 13 enabled 2026-07-04) — LLM-backed reviews/
   research were withheld out of caution; enabling them costs nothing (free
   tiers) and adds value.
3. **RED-tier breadth:** send_email, all financial, deploy are RED (correct).
   But some analysis-only actions may be over-gated — audit that read/analyze
   actions aren't needlessly YELLOW/RED (slows autonomy without reducing risk).

## Redesign: calibrate by risk × leverage, not habit
| Action class | Risk | Leverage | Recommended tier |
|---|---|---|---|
| Read/analyze/search (no mutation) | low | high | GREEN |
| Reversible local writes (notes, reminders, commits) | low | high | GREEN via trust ladder |
| Arbitrary shell / PC control | HIGH | high | RED unless allowlisted command; exclude from ladder |
| External mutation (email, post, deploy) | HIGH | high | RED always (keep) |
| Financial | HIGH | high | RED + paper-default (keep) |

## Concrete edits
1. Add a `TRUST_LADDER_DENYLIST` (high-blast-radius action types never
   auto-promote) in trust_ladder + config.
2. Re-tier `run_shell_command`: RED unless the command matches an allowlist.
3. Audit GREEN list for any external-mutating action; demote if found.
4. **Owner action (the real unlock): install the service so the ladder can start
   earning autonomy.** Withholding this is the biggest miscalibration.

## Provenance
2026-07-07. Sources: `core/loop/permission_gateway.py`,
`core/loop/trust_ladder.py`, `core/config.py` CONFIG["permission"].
