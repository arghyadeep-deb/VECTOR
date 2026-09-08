# Known Issues

**Purpose:** Bugs, gaps, technical debt
**Level:** System Level (Level 1)

---

## Overview

This document tracks known issues, bugs, and technical debt in VECTOR.

**Key Properties:**
- **Critical** — blocks operation
- **High** — significant impact
- **Medium** — noticeable but workable
- **Low** — minor inconvenience
- **Deferred** — explicitly not fixing

---

## Critical Issues

### None Currently

All critical issues have been resolved.

---

## High Priority Issues

### 1. Voice Pipeline Partial

**Component:** TTS, Wake Word
**Status:** ⚠️ Partial
**Impact:** Voice interaction not fully operational

**Details:**
- Kokoro TTS model not downloaded (300MB)
- Wake word uses "hey_jarvis" placeholder
- Custom "Hey VECTOR" training needed

**Workaround:** Use text input via HUD/API

**Fix Required:**
```bash
# Download Kokoro model
pip install kokoro
# Download model weights (~300MB)

# Train wake word
# Record 10 samples of "Hey VECTOR"
# Run openWakeWord training
```

---

### 2. Face Recognition Not Installed

**Component:** Sensing
**Status:** ⚠️ Partial
**Impact:** Face ID not working

**Details:**
- Code is ready (`core/sensing/camera.py`)
- `face-recognition` and `mediapipe` not pip-installed
- CPU-only by design (no CUDA wheel for dlib)

**Workaround:** Skip face recognition features

**Fix Required:**
```bash
pip install face-recognition mediapipe
```

---

## Medium Priority Issues

### 3. Intent Classification Accuracy

**Component:** Governor
**Status:** ⚠️ 90-95% accuracy
**Impact:** Some queries misrouted

**Details:**
- Phase 1 (embedding similarity): 9/10 accuracy
- Phase 2 (BERT classifier): needs fine-tuning
- 148 classes with limited training data

**Workaround:** Manual district specification via API

**Fix in Progress:**
- Data augmentation (LLM-generated variations)
- District-only classification (38 classes)
- LoRA fine-tuning on qwen3:8b

---

### 4. Some Agents Have No Tests

**Component:** Testing
**Status:** ⚠️ Coverage gaps
**Impact:** Regressions possible

**Details:**
- 140+ tests passing
- Not all 133 agents have dedicated tests
- Integration tests cover main paths

**Workaround:** Manual testing

**Fix Required:**
- Add unit tests for remaining agents
- Increase coverage to 80%+

---

### 5. Heartbeat Rate-Limit Bug

**Component:** Observability
**Status:** ❌ Open
**Impact:** Excessive logging

**Details:**
- SRE monitor heartbeat fires too frequently
- Rate-limiting not properly configured

**Workaround:** Ignore heartbeat logs

**Fix Required:**
- Add rate-limiting to heartbeat
- Configure proper intervals

---

## Low Priority Issues

### 6. Ponytail Cuts Pending

**Component:** Coding
**Status:** ⚠️ Cuts #1–4 pending
**Impact:** Some code over-engineered

**Details:**
- Ponytail guard enforces minimal-code principle
- 4 cuts identified but not applied
- Not blocking, but adds complexity

**Workaround:** Accept current code

**Fix Required:**
- Apply ponytail cuts #1–4
- Refactor identified files

---

### 7. Documentation Gaps

**Component:** Docs
**Status:** ⚠️ Some modules undocumented
**Impact:** Onboarding slower

**Details:**
- Core modules documented
- Some district agents lack docstrings
- API docs auto-generated but incomplete

**Workaround:** Read source code

**Fix Required:**
- Add docstrings to all agents
- Generate complete API docs

---

## Deferred Issues (Explicitly Not Fixing)

### 1. Fly.io Brain Server

**Decision:** Owner declined (requires card)
**Alternative:** Cloudflare Worker has full endpoint parity
**Status:** ✅ Resolved

---

### 2. Next.js Dashboard

**Decision:** HUD frontend serves this role
**Alternative:** `frontend/` HUD (6.3k LOC)
**Status:** ✅ Resolved

---

### 3. Supabase SDK

**Decision:** Removed in favor of raw httpx REST
**Reason:** SDK packages bloated, removed 2026-08-05
**Status:** ✅ Resolved

---

### 4. Chromadb

**Decision:** Replaced with nano-vectordb (LightRAG internal)
**Reason:** Chromadb SDK removed from requirements.txt 2026-08-05
**Status:** ✅ Resolved

---

## Issue Summary

| Priority | Count | Status |
|----------|-------|--------|
| Critical | 0 | ✅ All resolved |
| High | 2 | ⚠️ Need setup |
| Medium | 3 | ⚠️ In progress |
| Low | 2 | ⚠️ Backlog |
| Deferred | 4 | ✅ Explicitly not fixing |
| **Total** | **11** | — |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `37_KNOWN_ISSUES.md` — this document
- `40_CRITICAL_FINDINGS.md` — Critical analysis
- `41_DEVELOPMENT_ROADMAP.md` — Roadmap

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
