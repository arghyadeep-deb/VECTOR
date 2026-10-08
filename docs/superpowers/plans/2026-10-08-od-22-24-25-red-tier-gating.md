# OD-22, OD-24, and OD-25 RED-tier gating plan

## Decision

Route the five destructive MCP tools and two destructive API operations through
`PermissionGateway.evaluate_external()` before their existing side effects.
Treat the gateway strictly as an approval gate: approved calls continue through
the existing implementation; denied calls return without executing it.

## Implementation

1. Register `memory_clear`, `file_delete`, `task_delete`, `config_reset`,
   `worker_reset`, `agent_hp_award`, and `memory_restore` in
   `PermissionConfig.red`.
2. Add a small shared async MCP helper that obtains the running
   `AutonomousLoop` singleton, falling back to a throwaway loop only to obtain
   its gateway when the loop is not running.
3. Convert the five targeted MCP handlers to async functions, preserving their
   validation and mutation logic after the approval check.
4. Gate the shared agent-award implementation (covering both route aliases) and
   the memory-restore route before their existing calls.
5. Add regression tests for RED classification plus denied/approved execution
   of memory clear, file delete, agent award, and memory restore.

## Security and compatibility checks

- Use fixed, non-owner gateway sources so external calls cannot claim an
  interactive owner bypass.
- Include only action parameters needed to identify the requested mutation.
- Preserve existing path confinement, confirmation tokens, response models,
  and mutation functions.
- Verify FastMCP awaits the converted handlers and the existing audit wrapper
  preserves coroutine functions.
- Run the requested focused suite and compile every touched Python file.
