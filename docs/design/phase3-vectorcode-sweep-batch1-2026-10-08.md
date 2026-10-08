# Phase 3 Vectorcode Sweep — Batch 1 — 2026-10-08

**STATUS: all 18 findings fixed 2026-10-09** (overnight, owner asleep).
Commits: `a9dcee09f` (SEC-1/2/3, SANDBOX-1), `f89cd7aa3` (VCSEC-1/3/4,
VCMCP-1 — the critical fail-open-security-init and ungated-MCP-executor
findings), `9e449d150` (VCMCP-2/3/4/5, VCSEC-2/5/6/7 — SSRF+DNS-pinning,
stdio hang, streaming scan-before-release, and the rest). Every fix was
independently re-verified via direct diff review, real test runs, and a
genuine git-stash pre-fix/post-fix check before committing — not just
Codex's own report. See each commit message for full detail.

## Scope and method

This was a read-only, full-depth review of the cache-free Python source in:

- `vectorcode/src/vc_security/` (18 files)
- `vectorcode/src/vc_mcp/` (5 files)
- `vectorcode/src/security/` (7 files)
- `vectorcode/src/sandbox/` (3 compatibility shims)

The review read the implementations, searched all production callers, checked
the tool executor and system builder at the enforcement boundaries, and used
tests only as corroborating evidence. No production code was changed. Severity
reflects current reachability; explicitly dormant code is labelled as such.

## Finding summary

| Severity | Count |
|---|---:|
| Critical | 3 |
| High | 6 |
| Medium | 5 |
| Low | 4 |
| **Total** | **18** |

## `vectorcode/src/vc_security/`

### VCSEC-1 — Security setup silently fails open

- **Severity:** Critical
- **Evidence:** `vectorcode/src/vc_security/__init__.py:55-75`, `:76-87`, `:88-97`
- **Finding:** Scanner, capability-policy, and audit initialization each catch
  broad exceptions and continue. A typo in security mode, a broken policy, or
  an unavailable encrypted audit store can therefore return a usable engine
  with the corresponding control silently absent. This path is live through
  `vector_cli/ask.py`, `vector_cli/serve.py`, `sdk.py`, and
  `vc_system/builder.py`.
- **Fix recommendation:** Fail closed when security is enabled; distinguish
  optional telemetry from mandatory controls and raise a startup error for any
  configured guardrail/policy failure.

### VCSEC-2 — Streaming emits sensitive content before scanning it

- **Severity:** Critical
- **Evidence:** `vectorcode/src/vc_security/guardrails.py:222-264`, `:266-309`
- **Finding:** Both streaming methods yield every token/chunk immediately and
  scan only the accumulated output after the stream ends. `REDACT` and `BLOCK`
  modes therefore cannot redact or block streamed secrets/PII; at most they
  publish a post-hoc event after disclosure.
- **Fix recommendation:** Buffer and scan before release (or implement a safe
  rolling scanner with overlap); never advertise REDACT/BLOCK for a path that
  has already emitted the content.

### VCSEC-3 — Capability policy is allow-by-default, including parse failure

- **Severity:** High
- **Evidence:** `vectorcode/src/vc_security/capabilities.py:48-66`, `:121-143`,
  `:154-171`; `vectorcode/src/vc_security/__init__.py:78-86`
- **Finding:** `CapabilityPolicy` defaults `default_deny=False`; unknown agents,
  missing policy files, malformed policy files, and capabilities with no grant
  all resolve to allowed. `setup_security()` never supplies a deny-by-default
  option. The policy is live in the agent tool executor.
- **Fix recommendation:** Make production capability enforcement deny by
  default and treat missing/malformed configured policy as a startup failure.

### VCSEC-4 — Security audit data falls back to plaintext

- **Severity:** High
- **Evidence:** `vectorcode/src/vc_security/audit.py:32-45`, `:148-167`,
  `:216-253`
- **Finding:** Without SQLCipher, the live `AuditLogger` deliberately opens raw
  SQLite while persisting `matched_text` and `content_preview`—the very secrets
  and PII the scanners detected. A warning does not satisfy the repository's
  encrypted-sensitive-store rule.
- **Fix recommendation:** Refuse persistent audit logging without SQLCipher (or
  store only non-sensitive hashes/metadata); route connection management
  through the repository's approved encrypted database abstraction.

### VCSEC-5 — Audit and rate limiting violate the no-`threading` rule

- **Severity:** Medium
- **Evidence:** `vectorcode/src/vc_security/audit.py:15-16`, `:148-165`;
  `vectorcode/src/vc_security/rate_limiter.py:11`
- **Finding:** Production security modules directly import both raw `sqlite3`
  and `threading`, contrary to binding repository rules. The audit logger is
  live; the limiter is reusable security infrastructure.
- **Fix recommendation:** Use the approved encrypted store and an asyncio-safe
  lifecycle/concurrency design rather than process-global thread locks.

### VCSEC-6 — Declassification discards its mandatory justification

- **Severity:** Medium
- **Evidence:** `vectorcode/src/vc_security/taint.py:91-97`
- **Finding:** `declassify()` requires a `reason` but ignores it and returns no
  audit evidence, despite its docstring saying the reason should be logged.
  Any caller can strip PII/secret taint without an attributable record.
- **Fix recommendation:** Require an audit sink/context and atomically record
  actor, label, reason, source, and destination before returning declassified data.

### VCSEC-7 — SSRF defense is available but not mandatory at HTTP boundaries

- **Severity:** Medium
- **Evidence:** `vectorcode/src/vc_security/ssrf.py:1-147`; production-call
  search found no use from `vc_mcp/transport.py`
- **Finding:** The library has a dedicated SSRF checker, but consumers can issue
  arbitrary HTTP requests without it; Batch 1's MCP transport does exactly so.
- **Fix recommendation:** Centralize outbound client construction so SSRF
  validation and redirect/DNS policy cannot be omitted by individual callers.

### VCSEC-8 — Modules lack required executable self-tests

- **Severity:** Low
- **Evidence:** all 18 files in `vectorcode/src/vc_security/`
- **Finding:** None ends with the repository-required real `__main__` smoke
  block. This is systematic rather than an isolated style miss.
- **Fix recommendation:** Add meaningful, non-mocked smoke checks where the
  rule remains applicable, or formally scope/modernize the rule for packages.

## `vectorcode/src/vc_mcp/`

### VCMCP-1 — MCP tool calls bypass both capability policy and Permission Gateway

- **Severity:** Critical
- **Evidence:** `vectorcode/src/vc_mcp/server.py:72-76`, `:210-217`,
  `:259-286`; `vectorcode/src/vc_tools/_abc.py:100-119`, `:154-179`
- **Finding:** `MCPServer` constructs `ToolExecutor(tools)` with no capability
  policy, agent identity, boundary guard, interactive confirmation, or gateway
  callback. `tools/call` then executes directly. Auto-discovered tools include
  code interpreter, REPL, memory writes, and external `channel_send`; MCP
  annotations are descriptive only. The server is live in `vc_system/builder.py`
  and `mcp/protocol_manager.py`.
- **Fix recommendation:** Inject a deny-by-default identity/capability context
  and route every consequential tool through the real Permission Gateway; do
  not expose action tools when that context is absent.

### VCMCP-2 — Remote MCP transport permits SSRF and supplies no authentication

- **Severity:** High
- **Evidence:** `vectorcode/src/vc_mcp/transport.py:113-131`, `:140-180`;
  callers at `vectorcode/src/vc_system/builder.py:568-597` and
  `vectorcode/src/server/agent_manager_routes.py:499`
- **Finding:** A configured URL is passed directly to `httpx.Client.post()`.
  There is no scheme/host validation, private-address denial, DNS rebinding
  defense, redirect policy, or way to attach credentials. A malicious or
  compromised configuration can probe local/cloud metadata services; a real
  authenticated MCP endpoint cannot be safely configured.
- **Fix recommendation:** Validate each destination with the central SSRF guard
  (including redirects and resolved addresses) and add secret-manager-backed,
  redacted authentication configuration.

### VCMCP-3 — Stdio transport can hang indefinitely or deadlock

- **Severity:** High
- **Evidence:** `vectorcode/src/vc_mcp/transport.py:63-76`, `:78-91`
- **Finding:** The child `stderr` is piped but never drained, so a noisy child
  can block when the pipe fills. `stdout.readline()` has no deadline, so a
  silent or partial-line child blocks the caller forever.
- **Fix recommendation:** Use an asyncio subprocess with concurrent stderr
  draining, bounded message size, and per-request timeout/cancellation.

### VCMCP-4 — Missing JSON-RPC ids are converted into id `0`

- **Severity:** Medium
- **Evidence:** `vectorcode/src/vc_mcp/protocol.py:21-61`, `:81-90`
- **Finding:** `MCPRequest.from_json()` uses `parsed.get("id", 0)`, so a
  notification with no id becomes an ordinary request with id zero. Responses
  can then be generated for notifications, violating JSON-RPC semantics.
- **Fix recommendation:** Preserve absence as `None`, validate `jsonrpc`, method,
  params and id types, and suppress responses for notifications.

### VCMCP-5 — Tool exceptions are returned to clients verbatim

- **Severity:** Low
- **Evidence:** `vectorcode/src/vc_mcp/server.py:296-300`
- **Finding:** Arbitrary exception text is embedded in the JSON-RPC error,
  potentially exposing paths, commands, provider details, or secrets.
- **Fix recommendation:** Log the detailed exception after redaction and return
  a stable opaque error plus correlation id.

### VCMCP-6 — Package lacks required executable self-tests

- **Severity:** Low
- **Evidence:** all 5 files in `vectorcode/src/vc_mcp/`
- **Finding:** No module contains the required real `__main__` smoke block.
- **Fix recommendation:** Add focused protocol/transport smoke checks or
  formally exempt library modules from the repository-wide rule.

## `vectorcode/src/security/`

### SEC-1 — `SafeExecutor` is an execution allowlist, not a safety boundary

- **Severity:** High (dormant in production today)
- **Evidence:** `vectorcode/src/security/safe_executor.py:6-19`, `:21-57`,
  `:59-98`; production caller search found only its own smoke block and legacy tests
- **Finding:** Allowed binaries (`python`, `node`, `git`, `docker`, `kubectl`,
  package managers, etc.) are themselves arbitrary-code/system-action
  capabilities. The substring denylist is trivially bypassed, and execution has
  no working-directory confinement, environment sanitization, sandbox, or real
  Permission Gateway. Dormancy lowers current exposure but does not make it
  safe to wire.
- **Fix recommendation:** Keep it unwired; delete it or replace execution with
  the canonical sandbox plus mandatory Permission Gateway authorization and
  explicit per-action policy.

### SEC-2 — Validation logs complete tool arguments

- **Severity:** Medium
- **Evidence:** `vectorcode/src/security/validator.py:127-143`
- **Finding:** Successful validation logs the entire parameter dictionary.
  `write_file.content`, commands, and future secret-bearing parameters can be
  copied into logs.
- **Fix recommendation:** Log only tool name, validated field names, lengths,
  and a correlation id; redact values centrally.

### SEC-3 — Compatibility modules duplicate the security namespace

- **Severity:** Low
- **Evidence:** `vectorcode/src/security/{credential_stripper,file_utils,injection_scanner}.py:1-5`
- **Finding:** Three thin wildcard re-exports plus independent `validator.py`
  and `safe_executor.py` create two similarly named security APIs. This is not
  a vulnerability by itself, but it increases the risk that callers select the
  weaker compatibility control while believing they imported `vc_security`.
- **Fix recommendation:** Document one canonical namespace and make shims
  explicit named re-exports with deprecation/ownership tests.

## `vectorcode/src/sandbox/`

### SANDBOX-1 — This directory contains no sandbox enforcement

- **Severity:** High (misuse/assurance risk; canonical implementation is elsewhere)
- **Evidence:** `vectorcode/src/sandbox/runner.py:1-4`,
  `mount_security.py:1-4`, `wasm_runner.py:1-4`
- **Finding:** All three files wildcard re-export `core.sandbox`; this directory
  provides no independent confinement. The prior backlog already records
  resource-limit limitations in canonical `core/sandbox/wasm_runner.py` and
  `runner.py` (OD-8/OD-9). A reviewer or caller treating this package as a
  separate hardened boundary would receive inherited limitations unchanged.
- **Fix recommendation:** Mark the package unambiguously as compatibility-only,
  expose explicit symbols, and ensure security documentation/tests point to and
  assert the canonical sandbox guarantees.

## Batch conclusion

The most urgent correction is architectural: `vc_security` controls are
fail-open and post-hoc on streams, while `vc_mcp` creates a separate ungated
tool-execution path. Fixing individual regexes would not close that gap. The
next audit batch should give `vectorcode/src/gateway/` its own full-depth pass,
then follow with `src/server`, `src/mcp`, and the tool implementations reached
from MCP.
