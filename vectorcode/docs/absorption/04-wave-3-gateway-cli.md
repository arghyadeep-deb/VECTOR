# Wave 3 — Gateway + CLI Port

**Goal:** Port Hermes `gateway/` (53 files, ~2.67 MB) + `hermes_cli/` (58 files, ~2.39 MB). After this, VectorCode runs as a service with a full command surface.

**Dependencies:** Wave 0, Wave 2.

**Est effort:** 6–8 sessions.

---

## Read before coding

1. `00-MASTER-PLAN.md`
2. `GitHub/NousResearch_hermes-agent/repo/gateway/__init__.py`
3. `GitHub/NousResearch_hermes-agent/repo/hermes_cli/__init__.py`
4. `vectorcode/python/vectorcode/gateway/server.py` (existing skeleton)
5. `vectorcode/python/vectorcode/cli.py` (existing 38KB entry)

---

## Part A — Gateway (53 files)

### Batch 3A1 — Core gateway (3 files, ~14,000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `gateway/run.py` | `gateway/run.py` (NEW — split into submodules) | **12,600** |
| `gateway/session.py` | `gateway/session.py` (rewrite) | 1280 |
| `gateway/config.py` | `gateway/config.py` (rewrite) | 1500 |

`gateway/run.py` is the monster (565 KB!). Split into:
- `gateway/run/entry.py` — main entry, argparse
- `gateway/run/routing.py` — platform → handler dispatch
- `gateway/run/queue.py` — message queue + debounce
- `gateway/run/lifecycle.py` — startup/shutdown hooks
- `gateway/run/agent_bridge.py` — bridges Wave 0 engine
- `gateway/run/reconciler.py` — state reconciliation
- `gateway/run/__init__.py` — facade

### Batch 3A2 — Stream + delivery (3 files, ~1400 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `gateway/stream_consumer.py` | `gateway/stream_consumer.py` | 1085 |
| `gateway/delivery.py` | `gateway/delivery.py` (extend) | 200 |
| `gateway/mirror.py` | `gateway/mirror.py` | 130 |

### Batch 3A3 — Status + session support (4 files, ~1200 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `gateway/status.py` | `gateway/status.py` | 640 |
| `gateway/session_context.py` | `gateway/session_context.py` | 140 |
| `gateway/channel_directory.py` | `gateway/channel_directory.py` | 300 |
| `gateway/hooks.py` | `gateway/hooks.py` (extend) | 180 |

### Batch 3A4 — Platform adapters (subdir `gateway/platforms/`, ~15 files)

Ported into `gateway/platforms/`. Each file handles one messaging platform inbound/outbound:
- telegram, discord, slack, whatsapp, signal, matrix, feishu, dingtalk, wecom, yuanbao, email, webhook, homeassistant, bluebubbles, qq

Keep existing `vectorcode/python/vectorcode/comms/*_bot.py` — they become the OUTBOUND senders; gateway platforms become the INBOUND routers.

### Batch 3A5 — Builtin hooks (subdir, ~8 files)

| Source | Target |
|--------|--------|
| `gateway/builtin_hooks/` | `gateway/builtin_hooks/` (copy tree) |

Hooks for: rate limiting, message dedup, user allowlist, profanity filter, pre-tool approval.

### Batch 3A6 — Misc gateway (6 files, ~1500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `gateway/whatsapp_identity.py` | `gateway/whatsapp_identity.py` | 160 |
| `gateway/sticker_cache.py` | `gateway/sticker_cache.py` | 80 |
| `gateway/pairing.py` | `gateway/pairing.py` | 265 |
| `gateway/display_config.py` | `gateway/display_config.py` | 170 |
| `gateway/restart.py` | `gateway/restart.py` | 20 |
| `gateway/__init__.py` | `gateway/__init__.py` | 25 |

---

## Part B — CLI (58 files)

Move existing `vectorcode/python/vectorcode/cli.py` content into `cli/main.py` during this wave.

### Batch 3B1 — Main entry + config (3 files, ~18,500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/main.py` | `cli/main.py` (rewrite) | **7,800** |
| `hermes_cli/config.py` | `cli/config.py` (rewrite) | **3,900** |
| `hermes_cli/commands.py` | `cli/commands.py` (rewrite) | 1,400 |

`main.py` is 392 KB — split like Wave 3A1 into `cli/main/entry.py`, `cli/main/args.py`, `cli/main/dispatch.py`, `cli/main/init.py`.

### Batch 3B2 — Auth (5 files, ~4500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/auth.py` | `cli/auth.py` (rewrite — extend existing) | **3,700** |
| `hermes_cli/auth_commands.py` | `cli/auth_commands.py` | 535 |
| `hermes_cli/copilot_auth.py` | `cli/copilot_auth.py` | 295 |
| `hermes_cli/dingtalk_auth.py` | `cli/dingtalk_auth.py` | 225 |
| `hermes_cli/nous_subscription.py` | `cli/nous_subscription.py` | 625 |

### Batch 3B3 — Gateway CLI (2 files, ~5400 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/gateway.py` | `cli/gateway.py` | 3,825 |
| `hermes_cli/web_server.py` | `cli/web_server.py` | 2,660 |

### Batch 3B4 — Setup + install (3 files, ~3600 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/setup.py` | `cli/setup.py` | 2,950 |
| `hermes_cli/uninstall.py` | `cli/uninstall.py` | 410 |
| `hermes_cli/backup.py` | `cli/backup.py` | 630 |

### Batch 3B5 — Models (3 files, ~4300 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/models.py` | `cli/models.py` | 2,540 |
| `hermes_cli/model_switch.py` | `cli/model_switch.py` | 1,270 |
| `hermes_cli/model_catalog.py` | `cli/model_catalog.py` | 250 |
| `hermes_cli/model_normalize.py` | `cli/model_normalize.py` | 360 |

### Batch 3B6 — Providers + runtime (2 files, ~1600 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/providers.py` | `cli/providers.py` | 455 |
| `hermes_cli/runtime_provider.py` | `cli/runtime_provider.py` | 1,190 |

### Batch 3B7 — Plugins + hooks (3 files, ~2200 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/plugins.py` | `cli/plugins.py` | 1,035 |
| `hermes_cli/plugins_cmd.py` | `cli/plugins_cmd.py` | 1,005 |
| `hermes_cli/hooks.py` | `cli/hooks.py` | 310 |

### Batch 3B8 — Skills CLI (3 files, ~1500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/skills_hub.py` | `cli/skills_hub.py` | 1,345 |
| `hermes_cli/skills_config.py` | `cli/skills_config.py` | 160 |
| `hermes_cli/skin_engine.py` | `cli/skin_engine.py` | 935 |

### Batch 3B9 — Doctor + debug (3 files, ~1900 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/doctor.py` | `cli/doctor.py` (extend) | 1,310 |
| `hermes_cli/debug.py` | `cli/debug.py` | 505 |
| `hermes_cli/dump.py` | `cli/dump.py` | 235 |

### Batch 3B10 — Profiles + memory (2 files, ~1200 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/profiles.py` | `cli/profiles.py` (extend) | 840 |
| `hermes_cli/memory_setup.py` | `cli/memory_setup.py` | 360 |

### Batch 3B11 — MCP config + tools config (2 files, ~2700 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/mcp_config.py` | `cli/mcp_config.py` | 595 |
| `hermes_cli/tools_config.py` | `cli/tools_config.py` | 2,115 |

### Batch 3B12 — TUI + curses (2 files, ~570 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/curses_ui.py` | `cli/curses_ui.py` | 370 |
| `hermes_cli/banner.py` | `cli/banner.py` | 515 |

### Batch 3B13 — Slash + one-shot + cron (4 files, ~1000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/oneshot.py` | `cli/oneshot.py` | 190 |
| `hermes_cli/cron.py` | `cli/cron.py` | 240 |
| `hermes_cli/fallback_cmd.py` | `cli/fallback_cmd.py` | 295 |
| `hermes_cli/voice.py` | `cli/voice.py` | 460 |

### Batch 3B14 — Clipboard + pty + misc (10 files, ~2800 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `hermes_cli/clipboard.py` | `cli/clipboard.py` | 370 |
| `hermes_cli/pty_bridge.py` | `cli/pty_bridge.py` | 180 |
| `hermes_cli/tips.py` | `cli/tips.py` | 605 |
| `hermes_cli/webhook.py` | `cli/webhook.py` | 185 |
| `hermes_cli/slack_cli.py` | `cli/slack_cli.py` | 125 |
| `hermes_cli/logs.py` | `cli/logs.py` | 295 |
| `hermes_cli/status.py` | `cli/status.py` | 430 |
| `hermes_cli/pairing.py` | `cli/pairing.py` | 75 |
| `hermes_cli/claw.py` | `cli/claw.py` | 595 |
| `hermes_cli/azure_detect.py` | `cli/azure_detect.py` | 265 |

### Batch 3B15 — Small utils (11 files, ~1500 lines)

| Source | Target | Notes |
|--------|--------|-------|
| `hermes_cli/colors.py` | `cli/colors.py` | — |
| `hermes_cli/completion.py` | `cli/completion.py` (extend) | — |
| `hermes_cli/timeouts.py` | `cli/timeouts.py` | — |
| `hermes_cli/platforms.py` | `cli/platforms.py` | — |
| `hermes_cli/callbacks.py` | `cli/callbacks.py` | — |
| `hermes_cli/env_loader.py` | `cli/env_loader.py` | — |
| `hermes_cli/cli_output.py` | `cli/cli_output.py` | — |
| `hermes_cli/codex_models.py` | `cli/codex_models.py` | — |
| `hermes_cli/default_soul.py` | `cli/default_soul.py` | — |
| `hermes_cli/__init__.py` | `cli/__init__.py` | — |

---

## Critical wiring

After Part A: `vector gateway start` launches the HTTP/WS server; external platforms (telegram webhook, slack slash) hit `/gateway/<platform>/webhook`.

After Part B: `vector <cmd>` entry dispatches through `cli/main.py` argparse. Old top-level `cli.py` becomes an alias shim:

```python
# vectorcode/cli.py (shim for backwards-compat)
from vectorcode.cli.main import main
if __name__ == "__main__":
    main()
```

---

## Acceptance tests

1. `vector gateway start --port 8123` — server binds, `/health` returns 200
2. `vector gateway --platform telegram --webhook` — valid telegram update triggers agent run
3. `vector auth add anthropic` — interactive OAuth PKCE flow completes, credential stored in pool
4. `vector doctor` — runs 25+ checks (env, creds, models, skills, plugins, disk, deps)
5. `vector models list` — shows resolved model catalog from models.dev
6. `vector profile switch work` — next REPL uses `work` profile settings
7. `vector run --oneshot "hello" --json` — JSON output with status/content/tool_calls
8. `vector skills hub install <skill>` — downloads skill, validates, registers
9. `vector plugins list` — discovers `~/.vectorcode/plugins/` + built-ins

**Run:** `pytest tests/test_wave3_gateway.py tests/test_wave3_cli.py -v`

---

## Handoff to Wave 4

- Tag: `git tag absorption-wave-3-complete`
- After this wave, VectorCode is feature-complete CLI + service. Wave 4 adds plugins/cron/acp/voice/TUI.
