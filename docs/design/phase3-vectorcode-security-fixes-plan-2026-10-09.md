# Phase 3 Vectorcode security fixes plan — 2026-10-09

## Scope

Fix only the findings in `vc_security` and `vc_mcp` from the Batch 1 sweep.
Production edits remain under those two packages; regression tests live under
`tests/`. The sibling `security` and `sandbox` packages are out of scope.

## Execution order

1. Make enabled security initialization fail closed, then make capability
   policy loading deny by default and reject missing or malformed policy files.
2. Require MCP servers to receive real authorization context and refuse tool
   execution when it is absent.
3. Move security audit persistence to SQLCipher with the established plaintext
   backup migration pattern.
4. Add mandatory SSRF checks and credential indirection to remote MCP HTTP.
5. Replace blocking stdio transport with bounded asynchronous subprocess I/O.
6. Remove prohibited synchronization primitives, audit declassification, fix
   notification semantics, and make client errors opaque.
7. Implement buffered streaming guardrails if it can be done without changing
   the public streaming contract; otherwise document the required follow-up.

## Verification per finding

- Add a focused regression test for the reported failure mode.
- Run `py_compile` on every file changed for that finding.
- Run the directly affected existing tests and the new regression test.
- Keep the new test present while temporarily stashing only that finding's
  implementation files, and confirm the regression fails against pre-fix code.
- Leave all changes unstaged and do not commit.

