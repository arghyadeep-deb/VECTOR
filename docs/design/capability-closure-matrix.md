# VECTOR capability closure matrix

**Baseline:** 2026-10-10  
**Contract:** `docs/superpowers/specs/2026-10-10-vector-staged-closure-design.md`  
**Detailed inventory:** `docs/design/owner-decision-backlog.md`

This is the current evidence index, not a claim that every row is complete.
Every capability must end in one of the six statuses below:

`LIVE` · `NEEDS_CONFIG` · `FAIL_CLOSED` · `RETIRED` · `DEFERRED` · `FIX_QUEUE`

| ID | Capability | Status | Evidence / current truth | Exit criteria or revisit |
|---|---|---|---|---|
| BASE-001 | Agent manifest inventory | LIVE | `tests/test_manifest_inventory_contract.py`; readiness reports 274 agents, 41 districts, no empty/duplicate names | Keep counts generated from `config/agent_manifest.yaml` |
| BASE-002 | Launcher smoke spine | LIVE | `run_vector.py smoke` completed with 274 registered agents and a decision winner using a fresh per-run temp data root; `tests/test_run_vector_smoke_isolation.py` covers DB/data-root isolation and freshness | Re-run after launcher/runtime changes |
| TRUST-001 | Claims-store isolation | LIVE | `tests/test_claims_runtime_isolation.py`; default repository follows `VECTOR_TEST_DATA_DIR` | Re-run after persistence changes |
| TRUST-002 | Gateway outcome assessment | LIVE | `tests/test_gateway_handler_outcomes.py`, `test_outcome_assessment.py`, `test_command_failure_reporting.py` | Expand to every side-effect handler |
| TRUST-003 | Windows path-confinement symlink test | NEEDS_CONFIG | Production assertion remains; local Windows environment lacks symlink privilege and test skips with WinError 1314 | Re-run with Developer Mode or symlink privilege |
| RUN-001 | Autonomous loop multi-hour liveness | FIX_QUEUE | Source heartbeat/duplicate-loop controls exist; no fresh multi-hour soak evidence | Restart/recovery soak with heartbeat SLO |
| RUN-002 | Provider fallback/circuit health | FIX_QUEUE | Provider health and circuit-breaker tests exist; full external-provider acceptance remains incomplete | Exercise failure classes and fallback exhaustion |
| RUN-003 | Scheduler MCP tools | LIVE | `tests/test_scheduler_tool_injection.py`; `SystemBuilder` injects one runtime `TaskScheduler` into all five tools, and `tests/test_scheduler_runtime_path.py` proves the API uses the active data root | Re-run after scheduler lifecycle changes |
| RUN-004 | External MCP transport | NEEDS_CONFIG | Local stdio path is available; external SSE auth/deployment requires explicit configuration | Owner configures/authenticates external transport |
| CAP-001 | Growth content arm | LIVE | `tests/test_growth_config.py`, `tests/test_growth_content_arm.py`, `tests/test_growth_orchestrator.py`; current config enables the local content arm while `auto_publish=False` keeps external publication owner-gated | Owner-run daily media proof and explicit publication acceptance before any upload gate changes |
| CAP-001B | Growth software arm | DEFERRED | `_next_validated_issue()` intentionally returns `None`; build/review/fix/security stages remain fail-closed scaffolding | Define validated issue source, owner review, sandbox/Gateway path, rollback, release, and beta-PII gates; revisit 2026-11-10 |
| CAP-002 | AutoMemoryBridge | DEFERRED | Tested forward sync, no production constructor, reverse path incomplete | Define second-index provenance/dedup/reverse sync; revisit 2026-11-10 |
| CAP-003 | ExperimentRegistry | DEFERRED | Tested implementation, no production caller | Define subjects, metrics, exposure limits, rollback; revisit 2026-11-10 |
| CAP-004 | LoRA fine-tuning | DEFERRED | Manual training path is intentionally gated; top-level distillation still bypasses the tested approval/queue path | Make one canonical execution path and define artifact/resource/benchmark/rollback approval; revisit 2026-11-10 |
| CAP-005 | ChannelAgent governed bridge | LIVE | `tests/test_od43_channel_agent_wiring.py`; `GatewayRunner` constructs `ChannelAgent` with `GovernedAgentInvoker`, routing through A2A/Governor/Gateway | Add a real gateway authorization smoke run; keep deep-report escalation separately tracked |
| CAP-006 | Continuous sound sensing | FIX_QUEUE | Observe-loop wiring exists, but now requires `voice.ambient_enabled` plus consent; `tests/test_od58_sound_classifier_autonomous_wiring.py` proves no capture without consent. Emergency routing still lacks a production rule/subscription | Add consent/indicator/retention/duty-cycle evidence and connect alert events to the real emergency pipeline; revisit 2026-11-10 |
| CAP-007 | Godmode/jailbreak skill | FAIL_CLOSED | `tests/test_godmode_quarantine.py`; `execute_code` rejects Godmode markers and the loader excludes `godmode_race.py`/`auto_jailbreak.py` | Keep quarantined; any future red-team replacement needs a separate owner-approved contract |
| CAP-008 | Compatibility workflow shell action | FAIL_CLOSED | `vectorcode/src/agents/workflow_engine.py` routes `workflow_bash_execute` through `PermissionGateway`, with allowlisted executables/roots and focused compatibility tests | Keep unwired; redesign or retire before production discovery |
| CAP-009 | ChannelAgent deep-response escalation | FIX_QUEUE | Deep or >500-character responses return `vector://research/<session_id>`, but no producer, storage, or consumer for that URI exists | Persist/serve the report with an integration test, or remove the retrieval claim |
| CAP-010 | Sound emergency escalation | FIX_QUEUE | Sound classifier emits `environment:alert_sound`, but the live detector has no matching rule/subscription; direct probe returned no escalation | Add a real detector rule/subscriber and end-to-end classifier-to-emergency test |
| CAP-011 | Camera activation governance | FIX_QUEUE | `POST /camera/start` authenticates but directly flips camera state without a `PermissionGateway` decision | Route start/stop through the Gateway and add denial/approval tests |
| CAP-012 | PC-control capability grants | FAIL_CLOSED | Current PC actions are denied because the reconstructed capability policy has no `generic.run` grant; this is safe but not usable | Define legitimate caller grants without weakening default deny, then run owner hardware acceptance |
| EXT-001 | Production voice STT/TTS | NEEDS_CONFIG | `core/voice` is the production path; owner hardware/model proof is pending | Owner-run microphone/voice acceptance |
| EXT-002 | Legacy Mistral voice adapters | DEFERRED | Explicit removed-cloud stubs coexist with production voice adapters | Retire or document compatibility package; revisit 2026-11-10 |
| EXT-003 | ACP adapter | NEEDS_CONFIG | Import guard reports unavailable/incompatible package in current environment | Resolve package boundary and install/verify protocol |
| EXT-004 | Shadowbroker | NEEDS_CONFIG | Minimal probe received connection refused at `127.0.0.1:8765` | Start/configure sidecar and repeat probe |
| EXT-005 | ComfyUI | NEEDS_CONFIG | Doctor reports optional health endpoint unreachable | Start/configure sidecar and repeat probe |
| EXT-006 | HUD/browser flow | FIX_QUEUE | Static assets exist; full browser interaction evidence is pending | Run authenticated/local HUD flow and responsive checks |
| EXT-007 | Google Tasks OAuth | NEEDS_CONFIG | Connector has no expiry-driven token refresh and current credentials are not configured | Define refresh ownership/storage/retry semantics and run an authenticated probe |
| EXT-008 | VLLM/Pearl mining | FIX_QUEUE | `core/mining/vllm_pearl.py` imports missing `core.mining._docker`; implementation exists only under `vectorcode/src/mining/` | Resolve the package boundary and prove provider registration, Docker behavior, and fail-closed health |
| EXT-009 | Audio/image/PDF tools | FIX_QUEUE | Media executors lack a uniform allowed-root policy and direct provider paths are not uniformly Gateway-governed | Define media roots/provider policy and inject confinement/governance into every execution surface |

The remaining owner-decision entries are tracked individually in
`docs/design/owner-decision-backlog.md`; no row may be removed merely because
its module imports.
