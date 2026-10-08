# Phase 3 Vectorcode Sweep — Batch 2 — 2026-10-09

**STATUS: findings only — no fixes applied.** This is the review artifact for
the second Phase 3 dispatch. Remediation is intentionally deferred until the
findings have been reviewed.

## Scope and method

This was a read-only, full-depth review of all 63 Python files (approximately
60,000 lines) under `vectorcode/src/gateway/`. The review read the
implementations, searched their production callers, followed authentication,
permission, tool-execution, subprocess, storage, and outbound-network paths to
their enforcement boundaries, and checked the repository-specific rules in
`CLAUDE.md` and `.claude/rules/`. Tests and static checks were used only as
corroborating evidence. No production code was changed.

`vectorcode/src/gateway/run.py` was reviewed in its current form, including the
mining telemetry collector and governed `ChannelAgent` bridge added by
`4dbb2f254`. The new `/agent` path does use the A2A/Governor route, and the new
collector is owned by the gateway task lifecycle; neither addition produced a
separate finding below. Severity reflects current reachability; where a risk is
limited to loopback or requires an authenticated/configured integration, that
constraint is stated explicitly.

## Finding summary

| Severity | Count |
|---|---:|
| Critical | 2 |
| High | 4 |
| Medium | 5 |
| Low | 4 |
| **Total** | **15** |

## `vectorcode/src/gateway/`

### GW-1 — CLI HTTP gateway executes coding tools outside the Permission Gateway

- **Severity:** Critical
- **Evidence:** `vectorcode/src/gateway/server.py:448-471`;
  `vectorcode/src/engine/agent.py:23-81`;
  `vectorcode/src/engine/conversation.py:114-136`;
  `vectorcode/src/cli.py:685-696`
- **Finding:** The production `vector gateway start` command constructs this
  server. Its `/run` and `/stream` paths instantiate the coding `AIAgent` with
  no `permission_gateway`, project confinement, approval callback, or explicit
  tool allowlist, then execute the request. The engine advertises the coding
  toolset and dispatches model-selected tools directly through
  `model_tools.handle_function_call()`. Network-accessible binding requires a
  bearer key, but authentication is not authorization: any accepted request
  can reach terminal, file, code-execution, and web tools without the real
  Permission Gateway. Loopback mode is unauthenticated, so any local process
  can exercise the same path.
- **Fix recommendation:** Remove or disable this parallel executor until it
  can reuse the canonical governed gateway runner. At minimum, inject the real
  Permission Gateway, bind every request to an authenticated principal and a
  confined project root, derive an explicit tool allowlist, and fail closed if
  any of those controls cannot initialize.

### GW-2 — Gateway deliberately starts with command scanning fail-open

- **Severity:** Critical
- **Evidence:** `vectorcode/src/gateway/run.py:747-753`;
  `vectorcode/src/tools/tirith_security.py:71-86`, `:604`, `:616-673`
- **Finding:** Gateway construction starts the Tirith installer in the
  background and catches every setup failure, explicitly continuing
  “fail-open at scan time.” The scanner's default is also
  `tirith_fail_open=True`; missing binaries, spawn errors, timeouts, and unknown
  exit codes all return an `allow` verdict. Consequently, a security-control
  outage silently converts command execution from scanned to unscanned—the
  same fail-open class addressed in Batch 1.
- **Fix recommendation:** Make scanner availability a startup prerequisite
  whenever command-capable tools are enabled, default to fail-closed for every
  operational error, and expose a clear degraded/unhealthy state rather than
  allowing commands while background installation is incomplete.

### GW-3 — Responses API persists full tool history in raw SQLite

- **Severity:** High
- **Evidence:** `vectorcode/src/gateway/platforms/api_server.py:283-307`,
  `:310-345`
- **Finding:** `ResponseStore` documents that it stores the full internal
  conversation, including tool calls and tool results, then serializes that
  material directly into `response_store.db` with raw `sqlite3`. Tool output
  commonly contains source, filesystem content, credentials, or other private
  context. The store has no application encryption and therefore violates the
  repository rule forbidding raw SQLite for sensitive data; silently falling
  back to an in-memory raw database does not repair the persistent case.
- **Fix recommendation:** Move response state to the approved encrypted store,
  define retention and deletion semantics, minimize/redact persisted tool
  results, and fail closed (or explicitly disable continuation) if protected
  persistence cannot be initialized.

### GW-4 — Media downloads can follow redirects into private networks and exhaust memory

- **Severity:** High
- **Evidence:** `vectorcode/src/gateway/platforms/discord.py:1807-1830`,
  `:1886-1909`; `vectorcode/src/gateway/platforms/matrix.py:1050-1084`;
  `vectorcode/src/gateway/platforms/mattermost.py:405-428`;
  `vectorcode/src/gateway/platforms/telegram.py:1916-1945`;
  `vectorcode/src/gateway/platforms/base.py:1473-1498`
- **Finding:** Model-produced media URLs are checked once with `is_safe_url`,
  but these adapter-specific downloaders do not apply the repository's redirect
  revalidation hook. The clients follow redirects (aiohttp by default and
  Matrix/httpx explicitly), allowing a public URL to redirect to loopback,
  link-local metadata, or another private address. They also read the complete
  response into memory without a byte cap. An authorized prompt, compromised
  upstream model, or prompt injection can therefore turn final-response media
  handling into SSRF and memory exhaustion. The shared base downloader and
  Slack path already demonstrate the intended redirect guard, but these paths
  bypass it.
- **Fix recommendation:** Route every remote-media fetch through one shared
  downloader that validates scheme/host/IP at every redirect and connection,
  pins DNS decisions where supported, streams into a hard byte limit, validates
  media type, and rejects oversized or indeterminate content.

### GW-5 — Orphan-run cleanup drops ownership without stopping the agent

- **Severity:** High
- **Evidence:** `vectorcode/src/gateway/platforms/api_server.py:2309-2310`,
  `:2353-2363`, `:2451-2509`, `:2600-2615`
- **Finding:** `/v1/runs` limits concurrency by the number of entries in
  `_run_streams`, but the five-minute orphan sweep merely removes the stream,
  active-agent, and task references. It neither calls `agent.interrupt()` nor
  cancels/awaits the task. The executor thread can keep running tools after it
  becomes unobservable and unstoppable, while its removed stream slot permits
  another run. Repeating this creates unbounded background agent/tool work
  despite the advertised limit of ten.
- **Fix recommendation:** Treat the task/agent as the concurrency authority;
  interrupt and boundedly await stale work before releasing its slot, retain
  ownership until the executor really exits, cap event queues, and expose a
  terminal cancelled/expired state.

### GW-6 — WhatsApp startup kills any process that owns its configured port

- **Severity:** High
- **Evidence:** `vectorcode/src/gateway/platforms/whatsapp.py:32-64`,
  `:397-423`
- **Finding:** If the health probe does not identify a connected bridge,
  WhatsApp startup enumerates the listener on the configured port and forcibly
  terminates it with `taskkill /F` or `fuser -k`. It never verifies the PID was
  created by VECTOR, matches the bridge executable/session, or is covered by a
  stored ownership record. A port collision therefore destroys an unrelated
  user or system process, and the destructive action bypasses the Permission
  Gateway.
- **Fix recommendation:** Never kill by port alone. Persist and validate an
  owned PID plus process identity/start time, terminate only a verified child,
  otherwise report the collision and require an explicit governed approval.

### GW-7 — WhatsApp performs package installation and script execution during connect

- **Severity:** Medium
- **Evidence:** `vectorcode/src/gateway/platforms/whatsapp.py:357-392`,
  `:425-452`
- **Finding:** Merely connecting the adapter runs `npm install` when
  `node_modules` is absent and then executes the configured bridge script with
  a copy of the gateway's full environment. These external actions are not
  routed through the Permission Gateway, the dependency install is not
  lockfile-enforced here, and the child inherits unrelated credentials present
  in the daemon environment. Configuration access or a modified bridge tree can
  therefore turn platform startup into arbitrary code execution with excessive
  secrets.
- **Fix recommendation:** Install pinned dependencies as an explicit,
  separately approved setup step; validate the bridge path and lockfile; launch
  only the packaged bridge; and pass a minimal allowlisted environment. Route
  any repair/install action through the real Permission Gateway.

### GW-8 — Signed webhooks bypass governance for direct external actions

- **Severity:** Medium
- **Evidence:** `vectorcode/src/gateway/platforms/webhook.py:135-162`,
  `:474-529`, `:685-765`, `:788-831`
- **Finding:** HMAC authentication protects configured routes, but
  `deliver_only` renders request data and directly sends it to a platform or
  executes `gh pr comment`. Authentication proves possession of the webhook
  secret; it does not perform the repository-mandated Permission Gateway
  decision for messaging or subprocess execution. A leaked integration secret
  or over-broad route can therefore cause external side effects outside the
  canonical governance/audit path.
- **Fix recommendation:** Convert direct deliveries into typed actions and
  submit them to the real Permission Gateway with route, actor, destination,
  rendered-content, and command context; deny when governance is unavailable.

### GW-9 — API cron mutation and execution endpoints bypass the Permission Gateway

- **Severity:** Medium
- **Evidence:** `vectorcode/src/gateway/platforms/api_server.py:2010-2197`,
  `:2640-2647`; `vectorcode/src/gateway/platforms/api_server.py:675-695`,
  `:2661-2680`
- **Finding:** The API server exposes create, update, delete, pause, resume, and
  immediate-run operations and invokes the cron service directly after its
  bearer check. No real Permission Gateway decision is made for these durable
  or immediate external actions. The server permits all requests when bound to
  loopback without a configured key, so any local process can create and run
  jobs; remote binding improves authentication but still does not add action
  authorization.
- **Fix recommendation:** Require authentication even on loopback for
  action-capable endpoints, assign a principal/scope to each token, and route
  every cron mutation and manual execution through the canonical Permission
  Gateway and audit trail.

### GW-10 — HTTP gateway cancellation bookkeeping is unreachable

- **Severity:** Medium
- **Evidence:** `vectorcode/src/gateway/server.py:85-86`, `:218-229`,
  `:233-314`, `:558-571`
- **Finding:** `_running` is initialized and read by `/cancel` and `stop()`, but
  no run or stream handler ever inserts its task. Cancellation therefore
  returns success while only flipping a session flag; it cannot interrupt the
  executor or tool subprocesses. Shutdown likewise reports zero running tasks
  and can leave active work behind.
- **Fix recommendation:** Register every owned task before execution, remove it
  in `finally`, propagate cancellation into the agent/process registry, and
  await bounded cleanup before reporting cancellation or shutdown complete.

### GW-11 — Gateway production code broadly violates the no-`threading` rule

- **Severity:** Medium
- **Evidence:** `vectorcode/src/gateway/run.py:27`, `:720-722`, `:9340-9388`,
  `:10365-10367`, `:11405-11757`;
  `vectorcode/src/gateway/session.py:15`, `:652`;
  `vectorcode/src/gateway/pairing.py:27`, `:101`;
  `vectorcode/src/gateway/platforms/api_server.py:35`, `:297`;
  `vectorcode/src/gateway/platforms/discord.py:19`, `:147`;
  `vectorcode/src/gateway/platforms/feishu.py:60`, `:1340-1349`, `:2067`;
  `vectorcode/src/gateway/platforms/feishu_comment.py:1002-1008`;
  `vectorcode/src/gateway/platforms/yuanbao_proto.py:23`, `:109`
- **Finding:** Multiple live gateway paths import raw `threading`, create
  locks/events, and start unmanaged threads despite the binding repository rule
  banning it. The mix of asyncio lifecycle ownership with independent threads
  makes cancellation, shutdown ordering, context propagation, and shared-state
  reasoning unreliable; the cron ticker and review/reconnect helpers are
  particularly long-lived.
- **Fix recommendation:** Replace raw threads with gateway-owned asyncio tasks
  and locks, use bounded executor calls only for unavoidable blocking library
  operations, and make every background unit visible to the existing shutdown
  lifecycle.

### GW-12 — Raw internal exception text is returned to HTTP clients

- **Severity:** Low
- **Evidence:** `vectorcode/src/gateway/server.py:273-276`, `:348-351`,
  `:492-502`; `vectorcode/src/gateway/platforms/api_server.py:2020-2021`,
  `:2068-2069`, `:2087-2088`, `:2120-2121`, `:2139-2140`, `:2158-2159`,
  `:2177-2178`, `:2196-2197`, `:2482-2490`
- **Finding:** Both HTTP implementations serialize `str(exception)` into JSON,
  SSE events, or normal response text. Provider, subprocess, database, and
  filesystem exceptions can contain local paths, command fragments, upstream
  bodies, or identifiers, exposing internals to authenticated—and in loopback
  mode unauthenticated—clients.
- **Fix recommendation:** Return stable public error codes/messages and a
  correlation ID; keep the full exception only in structured, redacted server
  logs.

### GW-13 — Placeholder-token diagnostics disclose secret prefixes

- **Severity:** Low
- **Evidence:** `vectorcode/src/gateway/config.py:853-877`
- **Finding:** When a token fails the placeholder-strength check, startup logs
  its first six characters. Even a rejected credential remains secret-bearing
  input, and logs commonly have broader retention/readership than runtime
  configuration. Prefix disclosure is unnecessary to identify the platform and
  environment variable that needs correction.
- **Fix recommendation:** Log only the platform and configuration key; never
  include any substring, hash, or length-derived representation of a secret.

### GW-14 — Live adapter paths write directly with `print()`

- **Severity:** Low
- **Evidence:** `vectorcode/src/gateway/platforms/discord.py:2084-2123`,
  `:3329-3345`; `vectorcode/src/gateway/platforms/telegram.py:1866`, `:1897`;
  `vectorcode/src/gateway/run.py:11595`
- **Finding:** Production resolution, inbound-media, send-failure, and gateway
  paths use `print()` rather than `loguru`. In a long-running daemon this bypasses
  structured severity, redaction, rotation, and correlation controls. Separate
  interactive onboarding/diagnostic CLIs also contain prints, but the evidence
  above is reachable in normal adapter operation.
- **Fix recommendation:** Replace production-path prints with structured
  `loguru` calls and reserve direct terminal output for clearly isolated CLI
  presentation code.

### GW-15 — Sixty gateway modules lack the required executable self-test

- **Severity:** Low
- **Evidence:** repository-wide check of `vectorcode/src/gateway/**/*.py` found
  60 of 63 Python files without an `if __name__ == "__main__":` block; examples
  include `run.py`, `session.py`, `pairing.py`, `platforms/base.py`,
  `platforms/api_server.py`, and the major platform adapters
- **Finding:** The package broadly violates the repository requirement that
  every file provide a real `__main__` smoke test. Only three of 63 modules have
  one, leaving basic import/config/lifecycle regressions without the mandated
  per-file executable check.
- **Fix recommendation:** Add small deterministic, side-effect-safe smoke tests
  for production modules (or document and approve a repository-wide replacement
  policy); keep network and credential-dependent behavior behind explicit test
  inputs rather than mocks.
