# iii-main Audit

**Repo:** iii — Distributed worker runtime (ELv2 license, Rust engine)
**Audited:** 2026-06-02

---

## 1. Repo Reality

iii ("three") is a Rust-engine distributed worker runtime. Core primitives:
- **Worker** — a process that registers with the engine via WebSocket
- **Function** — unit of work with a stable ID (e.g. `content::classify`)
- **Trigger** — what causes a function to run: HTTP, cron, queue, state change, stream, direct call

The Rust engine (`engine/` — ELv2 non-OSS for commercial use) hosts the catalog. SDKs: Node.js, Python (`pip install iii-sdk`), Rust.

Python SDK (`sdk/packages/python/iii/`): async/await WebSocket client, function decorator registration, typed trigger declarations (HTTP, cron, queue, state), stream primitives, OpenTelemetry integration.

**License:** ELv2 — free for personal/non-commercial use; not for SaaS redistribution.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Status |
|---------|------------------|--------|
| Cron scheduling | `core/loop/cron_jobs.py` (APScheduler) | ✅ |
| Intra-process pub-sub | `core/event_bus/` (async, circuit breakers, DLQ) | ✅ |
| HTTP-triggered functions | `core/api/routers/` (FastAPI endpoints) | ✅ |
| Queue subscription | `core/api/routers/queue.py` | ✅ |
| Cross-process worker catalog | ❌ All districts run in-process | ❌ (not needed for single-owner) |
| Distributed multi-machine | ❌ VECTOR is local-first | ❌ (out of scope) |
| Typed trigger config pattern | APScheduler ad-hoc calls | ⚠️ Less structured |

---

## 3. Frontend: N/A

---

## 4. Verdict

**SAFE TO DELETE** (engine) — The Rust engine is overkill for VECTOR's local-first single-owner architecture. VECTOR's asyncio + APScheduler + FastAPI covers all the same patterns without the operational overhead of a Rust sidecar.

**Harvest:** Python SDK trigger pattern abstractions (`TriggerHandler`, `TriggerConfig`, `TriggerTypeRef`) are well-designed and worth using as a reference when refactoring `core/loop/cron_jobs.py` to be more inspectable.

**Delete-readiness:** DELETE-NOW source clone. SDK patterns are a reference-only harvest.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | `cron_jobs.py` uses ad-hoc APScheduler calls — no typed trigger configuration, hard to inspect at runtime | `core/loop/cron_jobs.py` | LOW |
| G2 | No unit tests for cron trigger registrations | `tests/test_cron_jobs.py` (missing) | LOW |
