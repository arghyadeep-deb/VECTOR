# VECTOR staged repository closure design

**Date:** 2026-10-10  
**Status:** Approved for implementation  
**Scope:** Entire PC-only VECTOR repository; robotics remains out of scope.

## Goal

Turn the existing local multi-agent platform into an honest, evidence-backed PC
assistant. Every capability must end in exactly one of these states:

- **LIVE** — the real path was exercised and the expected effect was verified.
- **NEEDS_CONFIG** — code is sound but a credential, service, model, device, or
  permission is missing; the result is explicit and fail-closed.
- **FAIL_CLOSED** — the capability is intentionally unavailable by policy or
  safety design and refusal is tested.
- **RETIRED** — the capability is not part of the supported product and its
  callers/tests/replacement were checked before removal.
- **DEFERRED** — the owner has accepted the capability gap with an owner,
  reason, exact exit criteria, and revisit date.
- **FIX_QUEUE** — a concrete defect remains and has a bounded implementation
  plan.

Importability, class existence, a friendly message, or a raw `ok` field is not
evidence of LIVE behavior.

## Approved architecture

```text
launcher/API -> AutonomousLoop -> Context/Goals/Decision
             -> core/runtime/executor.py
             -> PermissionGateway -> Governor -> district/agent
             -> verified outcome -> memory/audit/policy/metrics
```

The existing `PermissionGateway` remains the only real-world action boundary;
`Governor.dispatch()` remains the only district dispatch boundary. The existing
`core/runtime/executor.py` outcome helpers are extended and reused. No parallel
executor, permission system, or readiness platform is introduced.

### Rules

1. LLM proposals never bypass the Gateway.
2. RED/YELLOW behavior and the free-tier-only policy do not change without an
   explicit owner decision.
3. Missing integrations produce explicit unavailable/configuration results.
4. Approved execution is not completion until the expected result is observed.
5. Self-patching, Godmode, autonomous growth, and LoRA remain deferred or
   quarantined unless their specific contracts are approved.
6. Tests and smoke runs must isolate both `VECTOR_DB_PATH` and
   `VECTOR_TEST_DATA_DIR`.
7. The shadow self-audit is read-only and cannot modify, stage, commit, merge,
   or push source.

## Outcome contract

Raw handler payloads may retain existing `ok`/`success` strings for compatibility.
Completion boundaries use the following interpretation:

| Situation | Reported outcome | Side effect claim |
|---|---|---|
| Gateway denied or approval missing | `blocked` | none |
| Dependency/credential/device absent | `unavailable` or `needs_config` | none unless explicitly local-only |
| Handler declined or was not implemented | `rejected` or `not_implemented` | none |
| Handler ran but result is partial/local substitute | `incomplete` | only the observed local effect |
| Handler raised/timed out/returned an explicit failure | `failed` | unknown; never claim completion |
| Approved handler ran and independent evidence exists | `executed` | report only verified effect |

`core/runtime/executor.py` owns shared failure interpretation. API, WebSocket,
autonomous-loop reward/event code, and plan verification must use the same
interpretation rather than maintaining divergent status lists.

## Phases and budget

| Phase | Outcome | Modify | Create | Retire |
|---|---|---:|---:|---:|
| 0 | baseline contract and canonical inventory | 6–10 | 3–6 | 0–2 |
| 1 | persistence and outcome trust | 12–20 | 6–10 | 1–4 |
| 2 | runtime reliability | 15–25 | 6–12 | 2–6 |
| 3 | capability closure | 25–45 | 8–18 | 8–20 |
| 4 | external PC integrations | 15–30 | 5–12 | 3–10 |
| 5 | security/provenance and acceptance | 18–35 | 12–23 | 2–9 |

The ranges overlap because the same shared files may be touched by multiple
phases. Expected unique total: 100–180 files.

## Approved default dispositions

- **Deferred:** growth/software arm, AutoMemoryBridge, ExperimentRegistry,
  ChannelAgent, continuous SoundClassifier capture, and LoRA execution.
- **Quarantined:** `godmode_race.py` and the compatibility workflow engine's
  shell action. Neither may become an autonomous capability through discovery.
- **Fix/configure:** scheduler injection, Google Tasks refresh, ACP package
  collision, VLLM/Pearl boundary, media roots, and individually verified
  external adapters.
- **Retire only after caller/replacement proof:** stale scripts, duplicate
  wrappers, dead CLI modules, and compatibility shims.
- **Accepted policy:** free-tier-only reasoning and process-global isolation
  constraints remain accepted unless the owner explicitly changes them.

Deferred entries use owner `Arghyadeep`, proposed revisit date `2026-11-10`,
and must include a concrete exit test in the capability matrix.

## First implementation slice

1. Resolve the claims DB at construction time under `get_data_root()` instead of
   the import-time `%USERPROFILE%\\.vector\\claims.db` default.
2. Ensure `run_vector.py smoke` isolates main memory and claims state.
3. Correct Gateway false-success paths, beginning with
   `overwrite_note_personal`, and align API/autonomous completion accounting
   with the existing executor helpers.
4. Skip the symlink confinement test only when Windows refuses symlink creation;
   retain the production confinement assertion when symlinks are available.

## Verification gates

Every behavior change follows red-green-refactor:

1. Add a focused regression test.
2. Run it and observe the expected failure.
3. Implement the smallest change.
4. Run the focused test, then the affected-area suite.
5. Record the evidence in the capability matrix and gap register.

Required final evidence includes isolated smoke, API/lifespan checks, Gateway
approval/denial checks, provider degradation, restart/recovery, HUD/browser
flows, owner voice/camera checks, and one real day of use. No phase is complete
because imports or static scans pass alone.

## External prerequisites

Live proof may require owner-provided credentials, sidecars, Docker, optional
FAISS/ColBERT packages, Shadowbroker/ComfyUI, microphone/camera permissions,
browser permissions, and mail/calendar tokens. These prerequisites are recorded
as `NEEDS_CONFIG`; they are never simulated as successful execution.
