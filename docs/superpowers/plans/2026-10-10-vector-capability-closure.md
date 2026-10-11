# Plan: VECTOR capability closure

## Objective

Process incomplete and dormant capability families one at a time using the
approved disposition protocol.

## Capability work packages

### Growth, learning, and memory

- `districts/growth/growth_orchestrator.py`
- `districts/growth/software_arm.py`
- `vectorcode/src/memory/auto_bridge.py`
- `core/experiments/ab_testing.py`
- `vectorcode/src/learning/distillation/execute/loop.py`
- `vectorcode/src/learning/distillation/execute/appliers/lora_stub.py`

Keep autonomous product discovery, second-index memory, experiments, and LoRA
deferred unless their subjects, metrics, approvals, resource limits, artifact
verification, and rollback tests are explicitly defined. Retire only when the
owner selects retirement and the dedicated tests are accounted for.

### Channels and plugins

- `vectorcode/src/vc_agents/channel_agent.py`
- `vectorcode/src/plugins/loader.py`
- individually selected `vectorcode/src/plugins/*` entries
- `vectorcode/src/channels/*`
- `vectorcode/src/connectors/*`

Inventory discovery keys individually. Do not delete the live plugin cluster or
compatibility re-exports as a group.

### Sensing, tasks, mining, and media

- `core/sensing/sound_classifier.py`
- `vectorcode/src/connectors/google_tasks.py`
- `connectors/oauth.py`
- `core/mining/vllm_pearl.py`
- `vectorcode/src/mining/_docker.py`
- `vectorcode/src/vc_tools/audio_tool.py`
- `vectorcode/src/vc_tools/image_tool.py`
- `vectorcode/src/vc_tools/pdf_tool.py`

Add privacy/consent and root-confinement tests before wiring any continuous
device or file behavior. Missing services become `NEEDS_CONFIG`.

## Steps

1. For each family, write a caller/side-effect test or a retirement proof.
2. Run it red where a promised behavior is missing.
3. Choose only the approved disposition; record owner, reason, exit test, and
   revisit date in the capability matrix.
4. Implement or remove the smallest surface.
5. Run the family’s focused suite and one real minimal probe.

## Gate

No dormant capability becomes autonomous merely because it has tests or a
constructor. No destructive capability becomes reachable without the Gateway.
