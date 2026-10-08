# OD-37 LoRA Approval and Rollback Design

## Scope

Keep `LORA_FINETUNE` classified as `MANUAL`, but make that one edit operation
reachable through an explicit owner-approved Permission Gateway decision. Do
not change generic MANUAL edit behavior and do not add an autonomous caller.

## Approval boundary

`execute_edits()` recognizes a MANUAL `LORA_FINETUNE` edit before the generic
MANUAL skip. It submits compact, non-training-data metadata to
`PermissionGateway.evaluate_external()` using action type
`lora_finetune_execute` and source `distillation_execute_loop`. The action is
RED and owner-approval-only. A denial or gateway failure returns a blocked
`EditOutcome`; validation and application are not reached.

The executor remains synchronous. Its gateway bridge uses `asyncio.run()` only
when no event loop is active and fails closed with a blocked result otherwise.

## Rollback boundary

Immediately before real training, `LoraStubApplier` creates a confined rollback
record under `lora_rollbacks/<edit-id>/`. If an adapter already exists, its full
directory is copied to `pre_training_adapter/`; otherwise the manifest records
that there was no prior adapter. The snapshot is retained after successful
training until a later acceptance lifecycle exists. `rollback()` restores the
saved directory byte-for-byte, or removes the newly produced adapter when the
manifest says no adapter existed. A training exception triggers that rollback
immediately.

## Verification

Focused tests cover the exact gateway call, denial without validation/apply
side effects, approval reaching the applier, restoration of concrete prior
adapter bytes, path confinement, and RED/owner-only registration. The new tests
must be shown failing with only implementation files stashed when Git permits.

