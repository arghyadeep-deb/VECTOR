# VECTOR Repo Status

Last refreshed: 2026-06-17.

## Current Runtime

- `python run_vector.py smoke` passes with 75 registered agents.
- `python run_vector.py production-check` is the current readiness gate.
- `core/mcp_server.py` is now a facade; MCP tools live under `core/mcp_tools/`.
- Shared episodic/semantic/policy memory uses SQLCipher when available and serializes writes on the shared SQLite connection.
- `CONTEXT.md` remains the canonical domain glossary.

## Production Warnings

- Set real deployment secrets before production:
  - `MCP_KERNEL_SECRET`
  - `VECTOR_API_KEY`
  - `VECTOR_JWT_SECRET`
  - optional `HUMANLAYER_API_KEY`
- The production check still warns about intentional `eval`/`exec` surfaces in investment/backtesting strategy code. Treat those as disabled or sandbox-only for internet-facing deployment.
- Long-running soak/load evidence is still needed before calling the system production-grade for multi-user or internet-facing use.

## Cleanup Policy

- Runtime state, caches, test output, local DB files, build trees, and generated dependency folders should not be committed.
- Historical audit reports and one-time remediation scripts were removed after their resolved information was consolidated here.
- Domain/reference markdown under `docs/adr/`, `docs/agents/`, district skill folders, vectorcode docs, and marketing/investment knowledge bases are source/reference material and should be kept unless their owning district is removed.

## Useful Commands

```powershell
python run_vector.py smoke
python run_vector.py production-check
python -m pytest -q tests\test_collections.py::test_mcp_collection_tools tests\test_browser_absorption.py::test_mcp_browser_tools_exist tests\test_voice_cloning.py::test_mcp_voice_tools_exist tests\integration\test_spec15_hardening.py::TestMCPSecureCallWrapper
```

