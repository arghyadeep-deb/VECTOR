# Wave 2 — Agent Subsystems Port

**Goal:** Port VectorCode `agent/` directory (52 files, ~1.15 MB, ~35k lines). Provider adapters, context management, credentials, display, prompts, memory.

**Dependencies:** Wave 0. Can run parallel with Wave 1.

**Est effort:** 3–4 sessions.

---

## Read before coding

1. `00-MASTER-PLAN.md`, `01-wave-0-runtime.md`
2. `vectorcode/python/vectorcode/transports/` (existing adapter base)
3. `vectorcode/python/vectorcode/providers/` (existing router)
4. `GitHub/VectorCode_vectorcode/repo/agent/__init__.py`

---

## Batch order

### Batch 2A — Provider adapters (6 files, ~13,500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/anthropic_adapter.py` | `transports/anthropic.py` (rewrite) | 1930 |
| `agent/bedrock_adapter.py` | `transports/bedrock.py` (new) | 1280 |
| `agent/codex_responses_adapter.py` | `transports/codex.py` (new) | 1185 |
| `agent/gemini_native_adapter.py` | `transports/gemini_native.py` (new) | 895 |
| `agent/gemini_cloudcode_adapter.py` | `transports/gemini_cloudcode.py` (new) | 905 |
| `agent/auxiliary_client.py` | `transports/auxiliary.py` (new) | 3950 |

Keep `transports/base.py` signatures stable — all adapters implement the same `TransportProtocol`.

### Batch 2B — Provider support (6 files, ~3000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/model_metadata.py` | `providers/model_metadata.py` (rewrite) | 1575 |
| `agent/models_dev.py` | `providers/models_dev.py` (new) | 560 |
| `agent/gemini_schema.py` | `providers/gemini_schema.py` (new) | 90 |
| `agent/moonshot_schema.py` | `providers/moonshot_schema.py` (new) | 200 |
| `agent/image_gen_provider.py` | `providers/image_gen_provider.py` (new) | 200 |
| `agent/image_gen_registry.py` | `providers/image_gen_registry.py` (new) | 100 |

### Batch 2C — Credentials (3 files, ~2000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/credential_pool.py` | `credentials.py` (rewrite) | 1600 |
| `agent/credential_sources.py` | `credential_sources.py` (rewrite) | 440 |
| `agent/nous_rate_guard.py` | `providers/nous_rate_guard.py` (new) | 290 |

### Batch 2D — Context + compression (5 files, ~3800 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/context_engine.py` | `context/engine.py` (rewrite) | 210 |
| `agent/context_compressor.py` | `context/compactor.py` (rewrite) | 1720 |
| `agent/context_references.py` | `context/references.py` (rewrite) | 445 |
| `agent/manual_compression_feedback.py` | `context/manual_feedback.py` (new) | 45 |
| `agent/prompt_caching.py` | `providers/prompt_caching.py` (extend) | 60 |

### Batch 2E — Memory (2 files, ~800 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/memory_manager.py` | `memory/manager.py` (rewrite) | 520 |
| `agent/memory_provider.py` | `memory/provider.py` (rewrite) | 270 |

### Batch 2F — Display + spinner (1 large file, ~1000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/display.py` | `display/` (split into `kawaii_spinner.py`, `diff_preview.py`, `tool_messages.py`, `emoji_map.py`) | 1000 |

### Batch 2G — Prompt + onboarding (3 files, ~1600 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/prompt_builder.py` | `context/prompt_builder.py` (rewrite) | 1360 |
| `agent/onboarding.py` | `context/onboarding.py` (new) | 190 |
| `agent/skill_preprocessing.py` | `skills/preprocessing.py` (new) | 115 |

### Batch 2H — Skills support (2 files, ~700 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/skill_commands.py` | `skills/commands.py` (new) | 385 |
| `agent/skill_utils.py` | `skills/skill_utils.py` (extend) | 425 |

### Batch 2I — Insights + tracking (4 files, ~2000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/insights.py` | `insights.py` (rewrite) | 1035 |
| `agent/account_usage.py` | `providers/account_usage.py` (new) | 310 |
| `agent/usage_pricing.py` | `utils/usage_pricing.py` (extend) | 680 |
| `agent/rate_limit_tracker.py` | `providers/rate_limit_tracker.py` (extend) | 230 |

### Batch 2J — OAuth + copilot (3 files, ~2300 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/google_oauth.py` | `cli/auth_google.py` (new) | 990 |
| `agent/google_code_assist.py` | `providers/google_code_assist.py` (new) | 445 |
| `agent/copilot_acp_client.py` | `providers/copilot_acp_client.py` (new) | 590 |

### Batch 2K — Error + recovery (2 files, ~1000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/error_classifier.py` | `providers/error_classifier.py` (rewrite) | 970 |
| `agent/retry_utils.py` | `providers/retry_utils.py` (extend) | 50 |

### Batch 2L — Utils (5 files, ~1000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `agent/redact.py` | `utils/redact.py` (rewrite) | 340 |
| `agent/subdirectory_hints.py` | `utils/subdirectory_hints.py` (rewrite) | 215 |
| `agent/title_generator.py` | `utils/title_generator.py` (rewrite) | 145 |
| `agent/file_safety.py` | `tools/file_safety.py` (extend) | 100 |
| `agent/trajectory.py` | `context/trajectory.py` (new) | 55 |
| `agent/image_routing.py` | `providers/image_routing.py` (new) | 225 |

### Batch 2M — Transports (subdir, ~800 lines)

| Source | Target | Notes |
|--------|--------|-------|
| `agent/transports/` | `transports/` (merge tree) | HTTP helpers, streaming parsers |

---

## Critical wiring

After Batch 2A–2C, wire in `providers/__init__.py`:

```python
from .model_metadata import resolve_model
from ..transports.anthropic import AnthropicTransport
from ..transports.bedrock import BedrockTransport
# ... etc

ROUTER = ModelRouter(
    transports={
        "anthropic": AnthropicTransport,
        "bedrock": BedrockTransport,
        "gemini": GeminiNativeTransport,
        "gemini-cc": GeminiCloudCodeTransport,
        "codex": CodexTransport,
        "openai": OpenAICompatTransport,
        "ollama": OllamaTransport,
    },
    credential_manager=CredentialManager.global_instance(),
    rate_limit_tracker=rate_limit_tracker,
)
```

Engine (Wave 0) imports from `providers` not `transports` directly.

---

## Acceptance tests

1. `test_anthropic_adapter_streaming` — streamed response parses into content blocks
2. `test_bedrock_credential_rotation` — on 429, credential pool rotates, retries succeed
3. `test_context_compression_preserves_focus` — compressing 100-turn chat keeps focus_topic fidelity
4. `test_memory_manager_prefetch` — prefetch returns top-k relevant memories before turn
5. `test_display_diff_preview` — edit tool output renders unified diff with ANSI colors
6. `test_insights_cost_tracking` — conversation cost updates session_db after each turn
7. `test_redact_api_keys` — `sk-...` strings never appear in `~/.vectorcode/logs/`
8. `test_subdirectory_hints_unexplored` — after 5 file reads in `src/`, hint suggests exploring `tests/`

**Run:** `pytest tests/test_wave2.py tests/transports/ tests/providers/ -v`

---

## Handoff to Wave 3

- Tag: `git tag absorption-wave-2-complete`
- Required before Wave 3: provider router functional, credentials rotating, display rendering.
