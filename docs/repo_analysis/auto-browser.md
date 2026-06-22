# auto-browser-main - VECTOR Absorption Review

**Verdict:** IMPLEMENT selected browser-control safety patterns. Optional external sidecar; do not duplicate the whole service inside VECTOR.

**Priority:** HIGH-MEDIUM for real-world/browser automation

**Effort:** 1-2 sessions for VECTOR browser governance upgrades; more for sidecar integration

**License:** MIT

**Repo size inspected:** About 287 files, excluding git/build/cache directories.

## What It Is

Auto Browser is an MCP-native Playwright browser control plane for authorized workflows. It provides shared browser sessions, human takeover, reusable auth profiles, approvals, audit trails, PII scrubbing, witness receipts, local-first Docker deployment, and optional isolated browser containers.

It includes:

- controller API
- browser-node service
- Python client
- MCP stdio/HTTP bridge
- operator dashboard and noVNC takeover
- approvals and audit events
- auth-state encryption
- PII scrubbing
- witness receipt verification
- convergence harness for browser skill induction

## VECTOR Overlap

VECTOR already has:

- Playwright scraping for time/calendar
- browser/MCP tests and absorption history
- PermissionGateway for real-world actions
- Cloudflare/Termux remote command plan
- research/browser scraping needs

Auto Browser is relevant because VECTOR wants safe browser action, not just static page fetch.

## Real Value For VECTOR

Useful narrow additions:

- browser action approval gates
- operator identity required for sensitive browser sessions
- auth profile encryption and explicit reuse
- witness/audit receipts for browser actions
- human takeover path for brittle flows
- PII scrubbing around screenshots, DOM text, and network logs
- curated vs full MCP browser tool profile
- per-session isolation and max session age

## Risks

- browser automation can perform real-world actions accidentally
- saved auth profiles are high-value secrets
- screenshots/DOM/network logs may contain PII or tokens
- full MCP tool surface may be too broad for autonomous agents
- running a separate Docker browser service adds operational complexity

## Recommendation For Sonnet

Implement browser governance first, sidecar second.

1. Define a browser action risk model in VECTOR.
2. Require PermissionGateway approval for login, form submit, purchase, upload, delete, message-send, and account-change actions.
3. Add audit receipts for browser actions with URL, action, timestamp, operator/session id, and redacted screenshot hash.
4. Encrypt any reusable auth profile and make reuse explicit.
5. Add a "human takeover required" state for CAPTCHA/login/brittle workflows.
6. Later, consider Auto Browser as an external sidecar through a small adapter.

## Acceptance Criteria

- No browser action that changes external state can run without permission.
- Auth profiles are encrypted or disabled.
- PII/token scrubbing runs before logs/screenshots enter memory.
- Tool surface defaults to curated/minimal.
- VECTOR still works if the browser sidecar is unavailable.

