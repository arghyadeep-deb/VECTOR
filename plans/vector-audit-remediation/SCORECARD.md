# VECTOR Audit — Baseline Scorecard (2026-06-12)

Baseline scores from the audit, captured to measure remediation progress. These
are the "before" numbers; re-run the assessment after fixes to show movement.

## Code Quality Score: 38 / 100

| Dimension | Score | Weight | Score drivers (issue refs) |
|-----------|-------|--------|-----------------------------|
| Architecture & Design | 65 | 20% | dup dirs (21/22/27), monolith (24), syspath (25), bare-except (23) |
| Code Correctness | 35 | 25% | 25+ broken imports (09), crash-at-import (12/13), NameErrors (11/14), TimeoutError shadow (15), SecurityBlockError isinstance (27e), stubs (26) |
| Security | 25 | 20% | eval/exec (03), shell-injection (04), bypassable sandboxes (05), hardcoded secrets (06), brain-server auth (07), tokens-in-argv (08) |
| Production Readiness | 20 | 20% | SQLite concurrency (17), thread-unsafe cache (16), _SPAWNED_AGENTS race (19), sync-httpx-in-async (20), unbounded mem (18 ✅), owner config pending |
| JARVIS Feature Parity | 60 | 15% | semantic stub (26b), planner stub (26a), counterfactual partial |

## JARVIS Closeness Score: 42 / 100

Breadth is strong (30+ channels, 80+ tools, 8 districts, council, HP/evolution);
depth gaps drag it down: "security is swiss cheese, memory is half-stubbed,
25+ runtime crash bugs, SQLite will corrupt under load."

## Capability → issue map (where the parity points are lost)

| JARVIS capability | VECTOR caveat (audit) | Issue |
|-------------------|------------------------|-------|
| Memory & Learning | semantic memory is a stub | 26b |
| Self-Improvement | planner is a stub | 26a |
| Security & Safety | bypassable sandboxes, hardcoded secrets | 05, 06 |
| Reliability / 24-7 | unbounded mem leaks, SQLite concurrency | 18 ✅, 17 |
| Contextual Awareness | thread-unsafe cache | 16 |
| Predictive | counterfactual is partial | (Year-2 gap; track separately) |

## How the remediation moves the needle
- **Security 25 → up:** issues 03,04,05,06,07,08,27e — biggest weighted lever.
- **Code Correctness 35 → up:** 09,11,12,13,14,15,27e + stubs 26b/26c.
- **Production Readiness 20 → up:** 16,17,19,20 (18 already done) + owner config
  (secrets/sidecars from the production-hardening plan).
- **Architecture 65 → up:** 21,22,23,24,25,27.

Target after remediation: re-score and record here as "after" column.
