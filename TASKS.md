# VECTOR Tasks

> Long-term engineering work tracker.
> For current status, see `docs/OPEN_ISSUES.md` (`.claude/rules/phase_status.md` is a historical tracker, last updated 2026-06-11).
> For current quarter plan, see `../V.E.C.T.O.R. Brain/Blueprint/Planning/2026-Q3.md`.

---

## Current Sprint

### In Progress

Status corrected 2026-09-24 (Kokoro/face-recognition verified on disk today; the rest from `docs/OPEN_ISSUES.md` / `docs/phase_status.md`, not re-verified):

- ~~Kokoro TTS model download + wiring~~ — **done**: `models/kokoro/kokoro-v1.0.fp16-gpu.onnx` + voices present; loads on GPU (per phase_status 2026-06-20)
- "Hey VECTOR" wake word — **blocked on owner**: training pipeline complete, but real-voice recall is ~13%; needs ~50-100 real recordings (`scripts/train_wake_word.py`). Whisper keyword-spotting fallback is what runs today
- ~~Face recognition activation~~ — **done**: `import face_recognition` succeeds today (the older "dlib blocked by Application Control" note in OPEN_ISSUES was stale)
- ~~Cloudflare Worker deployment~~ — **done**: live and answering authenticated requests (per phase_status 2026-06-20); local parity tests can't run because the repo path contains a space (CI/space-free clone only)
- Phone Termux node setup (`bash phone_node/setup.sh`) — **owner-only, not done**. (Separate: the Oppo A31 is ADB-connected as the posting device)

### TODO

- ~~Next.js dashboard (`dashboard/src/`)~~ — **superseded**: the `frontend/` HUD (served at `/hud/`) is the monitoring UI; `dashboard/` does not exist
- ~~Fly.io brain server deployment~~ — **dropped**: `cloud/brain_server/` removed; Cloudflare Worker is live instead
- ~~Gap 4: `counterfactual.py`~~ — **exists**: `core/memory/counterfactual.py`
- ~~Gap 6: `causal_graph.py`~~ — **exists**: `core/memory/causal_graph.py`
- ~~Gap 7: `person_model.py`~~ — **exists**: `core/brain/person_model.py`
- ~~Gap 8: `meta_cognition.py`~~ — **exists**: `core/city/meta_cognition.py`
- Open engineering work is tracked in `docs/OPEN_ISSUES.md` section 0 (loop-freeze re-verification, Governor district trust, permission-tier coverage, and the 2026-09-23 audit work, now committed)

### Blocked

- Fly.io deployment — requires credit card (owner declined; Cloudflare Worker used instead)
- OpenMythos training — verify `train.py` exists before Month 2

---

## Backlog

### High Priority

- Continuous evaluation framework (LangSmith integration)
- Monitoring and alerting pipeline
- Security audit of all districts
- Performance benchmarking across model routes
- VectorCode code intelligence expansion

### Medium Priority

- Prompt optimization pipeline (versioning + A/B testing)
- Cost tracking and optimization per agent
- Token usage analytics dashboard
- Agent collaboration protocols
- Multi-model fallback routing improvements

### Low Priority

- Autonomous improvement loops
- Self-healing error recovery
- Advanced caching strategies
- OpenMythos custom LLM pre-training (Month 4-6)
- Full vector-chairman fine-tune on reasoning chains (Year 2)

---

## Completed

- Core intelligence stack (context/decision/policy/permission/autonomous loop) *(Phase 1)*
- 38 district directories, 170 manifest-registered agents *(Phase 1-3; recounted 2026-09-24)*
- 31 LLM providers integrated *(2026-05-17; recounted 2026-09-24)*
- Neural intelligence layer (Ruflo absorption) *(2026-05-17)*
- Voice pipeline (STT + TTS + ambient listener) *(partial)*
- Sensing + control (camera, screen, health, PC, phone) *(2026-05-29)*
- Production hardening (SSRF, prompt injection, timeouts) *(2026-05-29)*
- Absorbed repos: nango, auto-browser, voicebox, pocketbase, postiz, OpenWA, Understand-Anything *(2026-05-27 to 2026-05-28)*
- Ponytail minimal-code enforcement wired into runtime *(2026-07-09)*
- Full audit completed *(2026-07-15)*
- All 7 ADRs documented *(2026-08-06)*
- Project documentation scaffolding *(2026-08-06)*
- **JWT authentication with refresh tokens** — `core/security/token_blacklist.py`, `core/api/routers/auth_jwt.py`, middleware integration, 22 tests, ADR-0007 *(2026-08-06)*

---

## Notes

- Review and update this file weekly
- Cross-reference with `docs/OPEN_ISSUES.md` for current status (`.claude/rules/phase_status.md` is historical)
- Cross-reference with `../V.E.C.T.O.R. Brain/Blueprint/Planning/2026-Q3.md` for quarter objectives
- Move items between sections as work progresses
- Add dates when moving to Completed
- Reference specific issues/PRs where applicable
