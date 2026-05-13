# Wave 4 — Extensibility Port

**Goal:** Port Hermes plugin system, cron scheduler, ACP protocol adapter, optional skills, and TUI/voice extras. After this, VectorCode supports user-installable plugins, scheduled tasks, ACP interop, and full voice/curses interface.

**Dependencies:** Wave 0, 2, 3.

**Est effort:** 2–3 sessions.

---

## Read before coding

1. `00-MASTER-PLAN.md`
2. `vectorcode/python/vectorcode/plugins/plugin.py` (existing base)
3. `vectorcode/python/vectorcode/cli/plugins.py` (Wave 3 ported)
4. `GitHub/NousResearch_hermes-agent/repo/plugins/__init__.py`
5. `GitHub/NousResearch_hermes-agent/repo/acp_adapter/server.py`

---

## Batch order

### Batch 4A — Plugin discovery + isolation (3 files, ~3500 lines)

`hermes_cli/plugins.py` and `plugins_cmd.py` already ported in Wave 3 (CLI surface). This batch adds the runtime loader.

| Source | Target | Lines |
|--------|--------|------:|
| `plugins/__init__.py` | `plugins/__init__.py` (rewrite) | 30 |
| `plugins/loader.py` (Hermes) | `plugins/loader.py` (NEW) | ~600 |
| `plugins/manifest.py` (Hermes) | `plugins/manifest.py` (NEW) | ~400 |

Extract `loader.py` and `manifest.py` from `hermes_cli/plugins.py` (1035 lines) by splitting the runtime parts away from the CLI parts.

Plugin manifest format (`plugin.toml`):

```toml
[plugin]
name = "spotify"
version = "0.1.0"
description = "Control Spotify playback"
author = "you@example.com"

[hooks]
pre_tool_call = "hooks.pre_tool_call"
post_tool_call = "hooks.post_tool_call"

[tools]
"spotify_play" = "tools.spotify_play"
"spotify_pause" = "tools.spotify_pause"

[permissions]
network = ["api.spotify.com"]
secrets = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
```

### Batch 4B — Plugin sandbox (2 files, ~800 lines)

| Source | Target | Lines |
|--------|--------|------:|
| (extract) | `plugins/sandbox.py` (NEW) | ~500 |
| (extract) | `plugins/lifecycle.py` (NEW) | ~300 |

Sandbox isolates plugins via `importlib` with restricted globals (no `os.system`, no `subprocess.run` unless declared in `permissions.system`).

### Batch 4C — Plugin hub (Hermes plugins/ subdir, 40 files, ~690 KB)

Copy the entire Hermes `plugins/` tree to `vectorcode/python/vectorcode/plugins/builtin/` as reference plugins:

| Source | Target |
|--------|--------|
| `plugins/spotify_plugin.py` | `plugins/builtin/spotify/__init__.py` + manifest |
| `plugins/disk_cleanup_plugin.py` | `plugins/builtin/disk_cleanup/` |
| ... (38 more) | ... |

Each becomes a proper plugin package with `plugin.toml` manifest, `__init__.py`, and any helper scripts.

### Batch 4D — Cron scheduler (3 files, ~2500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `cron/__init__.py` | `cron/__init__.py` | 30 |
| `cron/scheduler.py` (Hermes) | `cron/scheduler.py` | ~1500 |
| `cron/storage.py` (Hermes) | `cron/storage.py` | ~970 |

Cron jobs stored in SQLite (`~/.vectorcode/cron.db`); scheduler runs in a daemon thread; jobs invoke `vector run` with stored prompt + context.

CLI: `vector cron add "<schedule>" "<prompt>"`, `vector cron list`, `vector cron remove <id>`.

### Batch 4E — ACP adapter (9 files, ~87 KB)

| Source | Target | Lines |
|--------|--------|------:|
| `acp_adapter/__init__.py` | `acp/__init__.py` (extend) | 40 |
| `acp_adapter/__main__.py` | `acp/__main__.py` | 25 |
| `acp_adapter/server.py` | `acp/server.py` (extend) | ~900 |
| `acp_adapter/session.py` | `acp/session.py` (NEW) | ~500 |
| `acp_adapter/auth.py` | `acp/auth.py` (NEW) | ~200 |
| `acp_adapter/events.py` | `acp/events.py` (NEW) | ~300 |
| `acp_adapter/permissions.py` | `acp/permissions.py` (NEW) | 80 |
| `acp_adapter/tools.py` | `acp/tools.py` (NEW) | 380 |
| `acp_adapter/entry.py` | `acp/entry.py` (NEW) | ~150 |

Plus `acp_registry/` (Hermes) → `acp/registry.py` for advertising VectorCode as an ACP-capable agent.

### Batch 4F — Optional skills (18 files, ~324 KB)

| Source | Target |
|--------|--------|
| `optional-skills/` | `skills/optional/` (copy tree) |

These are skills not enabled by default; user enables via `vector skills enable <name>`.

### Batch 4G — Built-in skills (27 files, ~275 KB)

| Source | Target |
|--------|--------|
| `skills/` | `skills/builtin/` (copy tree) |

Hermes ships with 27 built-in skills (memory, web search, codebase navigation, etc.). Already partially in `vectorcode/skills/` — merge.

### Batch 4H — Voice mode (already in Wave 3, polish here)

`hermes_cli/voice.py` already ported in Wave 3 Batch 3B13. This batch adds:

| Source | Target | Lines |
|--------|--------|------:|
| `tools/neutts_samples/` | `tools/neutts_samples/` (copy assets) | — |
| Voice config UI | `cli/voice_config.py` (NEW) | ~200 |

### Batch 4I — TUI gateway (8 files, ~202 KB)

| Source | Target |
|--------|--------|
| `tui_gateway/` | `tui_gateway/` (copy tree, port py) |

TUI gateway is a curses/textual interface for users without a web browser. 8 files include event loop, layout, key bindings, status bar.

### Batch 4J — Cron/scheduler glue (small)

Wire cron into Wave 0 engine: scheduled jobs spawn an `AIAgent` instance with the saved prompt, run to completion, save trajectory.

---

## Critical wiring

After Batch 4A–4B:

```python
# vectorcode/python/vectorcode/plugins/__init__.py
from .loader import discover_plugins, load_plugin
from .manifest import PluginManifest
from .sandbox import PluginSandbox

# Auto-load on engine init
def init_plugins(engine):
    for plugin in discover_plugins("~/.vectorcode/plugins/"):
        sandbox = PluginSandbox(plugin)
        sandbox.activate(engine)
```

After Batch 4D, cron daemon launches when `vector cron daemon start` is called. systemd unit file template at `packaging/systemd/vector-cron.service`.

After Batch 4E, `vector acp serve --port 8765` exposes the ACP endpoint.

---

## Acceptance tests

1. `vector plugins install ./examples/hello_plugin/` — manifest parsed, plugin registered, hook fires on next tool call
2. `vector plugins list` — shows installed plugins + their declared tools
3. `vector cron add "0 9 * * *" "summarize my GitHub activity"` — cron job stored, scheduler picks it up
4. `vector cron daemon start` — runs as background process; killing it preserves jobs
5. `vector acp serve --port 8765` — ACP client (e.g., Zed) can connect and invoke tools
6. `vector skills enable web-research` — optional skill activated, available in next REPL
7. `vector tui` — curses interface launches, accepts input, displays streaming response
8. `vector voice listen` — mic input transcribed, fed to agent, TTS reply spoken

**Run:** `pytest tests/test_wave4_plugins.py tests/test_wave4_cron.py tests/test_wave4_acp.py -v`

---

## Handoff to Wave 5

- Tag: `git tag absorption-wave-4-complete`
- Hermes is now 100% absorbed. Wave 5 covers Ruflo TS→Python.
