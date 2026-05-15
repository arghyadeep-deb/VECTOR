# Wave 1 — Tool Subsystem Port

**Goal:** Port all 82 VectorCode tools (~2.14 MB, ~42k lines) to VectorCode.

**Dependencies:** Wave 0 complete (engine + registry working).

**Est effort:** 4–5 sessions.

---

## Read before coding

1. `vectorcode/docs/absorption/00-MASTER-PLAN.md`
2. `vectorcode/docs/absorption/01-wave-0-runtime.md` (how tools are dispatched)
3. `vectorcode/python/vectorcode/tools/registry.py`
4. `GitHub/VectorCode_vectorcode/repo/tools/__init__.py`

---

## Batch order (by dependency)

### Batch 1A — Core file/shell/path (5 tools)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/path_security.py` | `tools/path_security.py` | 30 |
| `tools/file_safety.py` | `tools/file_safety.py` (extend) | 80 |
| `tools/binary_extensions.py` | `tools/binary_extensions.py` | 40 |
| `tools/file_state.py` | `tools/file_state.py` | 300 |
| `tools/ansi_strip.py` | `tools/ansi_strip.py` | 50 |

### Batch 1B — File operations (3 tools, ~3000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/file_tools.py` | `tools/file_tools.py` (rewrite) | 1260 |
| `tools/file_operations.py` | `tools/file_operations.py` (new) | 1240 |
| `tools/patch_parser.py` | `tools/patch_parser.py` | 530 |

### Batch 1C — Terminal/bash (3 tools, ~2600 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/terminal_tool.py` | `tools/terminal.py` (rewrite) | 2240 |
| `tools/process_registry.py` | `tools/process_registry.py` | 1400 |
| `tools/interrupt.py` | `tools/interrupt.py` | 90 |

### Batch 1D — Approval + security (4 tools, ~2200 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/approval.py` | `tools/approval.py` | 1260 |
| `tools/tirith_security.py` | `tools/tirith_security.py` | 640 |
| `tools/url_safety.py` | `tools/url_safety.py` | 230 |
| `tools/osv_check.py` | `tools/osv_check.py` | 120 |

### Batch 1E — Delegate + subagent (2 tools, ~2600 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/delegate_tool.py` | `tools/delegate_tool.py` (rewrite) | 2580 |
| `tools/clarify_tool.py` | `tools/clarify_tool.py` | 120 |

### Batch 1F — Code execution + checkpoint (3 tools, ~2000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/code_execution_tool.py` | `tools/code_execution.py` (rewrite) | 1500 |
| `tools/checkpoint_manager.py` | `tools/checkpoint_manager.py` (rewrite) | 770 |
| `tools/budget_config.py` | `tools/budget_config.py` | 50 |

### Batch 1G — Web + browser (9 tools, ~7800 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/web_tools.py` | `tools/web_tools.py` (rewrite) | 2120 |
| `tools/browser_tool.py` | `tools/browser.py` (rewrite) | 2830 |
| `tools/browser_supervisor.py` | `tools/browser_supervisor.py` | 1370 |
| `tools/browser_cdp_tool.py` | `tools/browser_cdp_tool.py` (rewrite) | 545 |
| `tools/browser_camofox.py` | `tools/browser_camofox.py` | 530 |
| `tools/browser_camofox_state.py` | `tools/browser_camofox_state.py` | 40 |
| `tools/browser_dialog_tool.py` | `tools/browser_dialog_tool.py` | 135 |
| `tools/browser_providers/` | `tools/browser_providers/` (copy tree) | ~800 |
| `tools/website_policy.py` | `tools/website_policy.py` | 240 |

### Batch 1H — Memory + session search (3 tools, ~3700 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/memory_tool.py` | `tools/memory_tool.py` (rewrite) | 570 |
| `tools/session_search_tool.py` | `tools/session_search_tool.py` | 595 |
| `tools/tool_result_storage.py` | `tools/tool_result_storage.py` | 195 |

### Batch 1I — Skills tools (5 tools, ~5900 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/skills_tool.py` | `tools/skills_tool.py` (rewrite) | 1320 |
| `tools/skill_manager_tool.py` | `tools/skill_manager_tool.py` | 735 |
| `tools/skills_sync.py` | `tools/skills_sync.py` | 405 |
| `tools/skills_hub.py` | `tools/skills_hub.py` | 2910 |
| `tools/skills_guard.py` | `tools/skills_guard.py` | 900 |

### Batch 1J — MCP tool + OAuth (3 tools, ~4100 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/mcp_tool.py` | `tools/mcp_tool.py` (rewrite) | 3000 |
| `tools/mcp_oauth.py` | `tools/mcp_oauth.py` | 540 |
| `tools/mcp_oauth_manager.py` | `tools/mcp_oauth_manager.py` | 580 |

### Batch 1K — Image/vision/audio (6 tools, ~4200 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/image_generation_tool.py` | `tools/image_gen.py` (rewrite) | 920 |
| `tools/vision_tools.py` | `tools/vision_tools.py` (rewrite) | 770 |
| `tools/tts_tool.py` | `tools/tts_tool.py` (rewrite) | 1420 |
| `tools/transcription_tools.py` | `tools/transcription_tools.py` | 870 |
| `tools/neutts_synth.py` | `tools/neutts_synth.py` | 90 |
| `tools/voice_mode.py` | `tools/voice_mode.py` (rewrite) | 950 |

### Batch 1L — Messaging (3 tools, ~3300 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/send_message_tool.py` | `tools/send_message_tool.py` (rewrite) | 1670 |
| `tools/discord_tool.py` | `tools/discord_tool.py` | 830 |
| `tools/homeassistant_tool.py` | `tools/homeassistant_tool.py` | 445 |

### Batch 1M — Feishu + Yuanbao (3 tools, ~1050 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/feishu_drive_tool.py` | `tools/feishu_drive_tool.py` | 325 |
| `tools/feishu_doc_tool.py` | `tools/feishu_doc_tool.py` | 100 |
| `tools/yuanbao_tools.py` | `tools/yuanbao_tools.py` | 670 |

### Batch 1N — Cron + RL + misc (7 tools, ~2400 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/cronjob_tools.py` | `tools/cron_tools.py` (rewrite) | 620 |
| `tools/rl_training_tool.py` | `tools/rl_training_tool.py` | 1400 |
| `tools/mixture_of_agents_tool.py` | `tools/mixture_of_agents_tool.py` | 545 |
| `tools/todo_tool.py` | `tools/todo_tool.py` (rewrite) | 245 |
| `tools/fuzzy_match.py` | `tools/fuzzy_match.py` | 650 |
| `tools/env_passthrough.py` | `tools/env_passthrough.py` | 135 |
| `tools/debug_helpers.py` | `tools/debug_helpers.py` | 90 |

### Batch 1O — Schema + infra (6 tools, ~1100 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `tools/schema_sanitizer.py` | `tools/schema_sanitizer.py` | 195 |
| `tools/tool_output_limits.py` | `tools/tool_output_limits.py` | 85 |
| `tools/tool_backend_helpers.py` | `tools/tool_backend_helpers.py` | 115 |
| `tools/credential_files.py` | `tools/credential_files.py` | 365 |
| `tools/managed_tool_gateway.py` | `tools/managed_tool_gateway.py` | 130 |
| `tools/registry.py` | already done in Wave 0 | — |

### Batch 1P — Environments (subdir, ~900 lines)

| Source | Target | Notes |
|--------|--------|-------|
| `tools/environments/` | `tools/environments/` (copy tree) | SWE-bench env definitions |

---

## Rules per batch

1. **Always port full file.** Don't skip functions. Mark any skipped with `# TODO absorption:wave1-skip`.
2. **Preserve signatures.** External callers in VectorCode use these; matching helps cross-reference.
3. **Register every tool in `tools/registry.py`** with schema + risk_level.
4. **Swap `vectorcode_*` imports → `vectorcode.*`.** Add alias shim `vector_constants = vector_constants` in a compat layer if needed.
5. **Every tool gets a smoke test** in `tests/tools/test_<tool>.py`: init, one happy-path call, one error-path call.

---

## CHECKPOINT per batch

After each batch (1A–1P):

```bash
pytest tests/tools/ -k "wave1_batch_<letter>" --tb=short
```

All new tests green + no regressions in existing tests.

---

## Final wave acceptance

1. `vector run "list all Python files in this repo"` → terminal tool executes `find` / `Get-ChildItem`
2. `vector run "search web for 'agentic coding benchmarks'"` → web_tools returns real results
3. `vector run "read tests/test_wave0.py and patch the first test to print OK"` → file_tools read + patch applied
4. `vector run "spawn a subagent to count markdown files"` → delegate_tool works
5. `vector tools list` outputs all 82 tools registered

---

## Handoff to Wave 2

- Tag: `git tag absorption-wave-1-complete`
- Update master plan: wave 1 → [DONE]
- Wave 2 can start in parallel with Wave 3 planning.
