---
name: vector-config-and-flags
description: Load when configuring VECTOR — reading/setting a config value, understanding an env flag, adding a config axis, or debugging "the feature didn't turn on". Catalog of VECTOR's configuration surface. Triggers: "config", "env var", "flag", "setting", "how do I enable", "VECTOR_", ".env", "CONFIG".
---

# VECTOR Config & Flags

Where every configuration axis lives and how to change it. Ground truth
2026-07-07. Re-verify a value before relying on it — flags drift.

## When NOT to use this skill
For the model catalog specifically use `vector-inference-routing`. For running
the app use `vector-run-and-operate`.

## The three config surfaces
1. **`core/config.py`** — the `CONFIG` dict (pydantic BaseSettings, `SecretStr`
   for secrets, no hardcoded keys). Sub-configs as `CONFIG["voice"]`,
   `CONFIG["permission"]`, `CONFIG["media"]`, `CONFIG["sensing"]`, etc. Nested
   env override: `SECTION__FIELD=value` (e.g. `SENSING__SCREEN_ENABLED=true`).
   Direct-run `python core/config.py` prints status + validates (the strip-own-
   dir guard makes it work despite the core/email shadowing bug).
2. **`.env`** — secrets + flags. Auto-loaded at `core/__init__` import
   (2026-07-04) via `load_dotenv`; existing os.environ wins. Gitignored.
3. **`core/inference/model_catalog.yaml`** — owner-editable LLM catalog (see
   `vector-inference-routing`).

## The VECTOR_*_LLM feature flags
Read via `os.environ.get("VECTOR_X") == "1"`. Gate LLM-backed enhancements out
of default runs (so tests never hit live LLMs). **13 ENABLED 2026-07-04**:
RESEARCH_LLM_DESIGN, PREDICTIVE_USE_MEMORY, OBSIDIAN_RAG_QUERY,
FASTAPI_REVIEW_LLM, PYTHON_REVIEW_LLM, SECURITY_REVIEW_LLM, SEO_LLM,
GOOGLE_ADS_LLM, FEEDBACK_LLM, STYLE_LLM, WEB_SCOUT_LLM, REDDIT_MINER_LLM,
SKILLS_LLM. **3 deliberately OFF (heavy/risky):** `VECTOR_LIVE_TESTS`
(tests hit live models), `VECTOR_TRAINING_REAL` (real GPU LoRA), and
`VECTOR_DB_RECOVERY_CHECK` (keep off unless DB backed up).

## Key config values worth knowing
- `CONFIG["cf_worker_url"]` — deployed Cloudflare Worker (D1 command queue).
- `CONFIG["permission"]["green"/"yellow"/"red"]` — action tiers; `trust_ladder_enabled`,
  `trust_promotion_streak` (20).
- `CONFIG["voice"]` — kokoro_speed 0.85, wake_phrase "hey_vector", `llm_intent_fallback`,
  `llm_intent_cloud_budget_sec`.
- `CONFIG["sensing"]` — `screen_enabled` (default False — flip to enable Coding
  Companion), `stuck_*`, `vc_session_marker`, `defer_llm_while_owner_codes`.
- `CONFIG["media"]["wan2gp_url"]` — local video server URL (set to enable free video).
- `CONFIG["models"]` — ambient/focus/reasoning/coder/deep/... → Ollama tags.

## Adding a config axis (checklist)
1. Add the field to the right pydantic sub-model in `core/config.py` (with a
   default + validator if bounded).
2. If it maps from an env var, add it to the CONFIG dict assembly and (if
   ALL-CAPS env) the env→path map near the bottom.
3. Never hardcode the value in business logic — read `CONFIG["..."]`.
4. Re-verify: `python core/config.py | tail -1` (expect `config.py OK`).

## Provenance and maintenance
Dated 2026-07-07. Re-verify flags: `python -c "import core,os; print([k for k in os.environ if k.startswith('VECTOR_')])"`.
Re-verify config loads: `python core/config.py | tail -1`.
