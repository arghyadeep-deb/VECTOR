# Wave 5 — VectorCode TS → Python Port

**Goal:** Port VectorCode's TypeScript runtime to Python. Covers `vectorcode/src/`, `v3/` core, `v2/` SPARC methodology, and `ruvocal/` web UI.

**Dependencies:** Wave 0 (engine), Wave 1 (tools). Can run parallel with Waves 2–4.

**Est effort:** 4–5 sessions.

---

## Read before coding

1. `00-MASTER-PLAN.md`
2. `vectorcode/python/vectorcode/mcp_client/client.py` (existing, ~25KB)
3. `vectorcode/python/vectorcode/agents/coordinator.py` (existing v3 stub)
4. `GitHub/vectorcode_vectorcode/repo/CLAUDE.md` (architecture overview)
5. `GitHub/vectorcode_vectorcode/repo/AGENTS.md` (agent definitions)
6. `GitHub/vectorcode_vectorcode/repo/vectorcode/src/` (main TS source)
7. `GitHub/vectorcode_vectorcode/repo/v3/src/` (newer architecture)

---

## Scope

| Source | Files | Lines | Strategy |
|--------|------:|------:|----------|
| `vectorcode/src/mcp-bridge/` | 3 | ~2000 | Already partial in `mcp_client/` — complete |
| `vectorcode/src/scripts/` | 2 | ~300 | Port to `scripts/vectorcode_*.py` |
| `vectorcode/src/ruvocal/` | 3 | ~100 | SvelteKit shim — port API only, drop UI |
| `vectorcode/v3/src/` | 23 | ~2500 | Core agent runtime (port to `agents/v3/`) |
| `vectorcode/v3/implementation/` | 135 | ~50,000 | Implementation modules — port high-value subset |
| `vectorcode/v3/mcp/` | 86 | ~25,000 | MCP tool definitions — port as tool schemas |
| `vectorcode/v3/plugins/` | 326 | ~110,000 | Plugin definitions — convert to manifests |
| `vectorcode/v2/` | 993 + 1115 | ~30,000 | SPARC methodology — port as skills + workflow |
| `vectorcode/v3/@claude-flow/` | 1798 | ~500,000 | Vendored deps — DO NOT PORT, use Python equivs |
| `vectorcode/agents/` | YAML | — | Agent manifests — convert to `agents/definitions/*.yaml` |

**Note:** `@claude-flow/` is a bundled npm dependency. Replace with Python equivalents (already in `mcp_client/`).

---

## Batch order

### Batch 5A — MCP bridge completion (~2000 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `vectorcode/src/mcp-bridge/index.js` | `mcp_client/bridge.py` (NEW) | 600 |
| `vectorcode/src/mcp-bridge/mcp-stdio-kernel.js` | `mcp_client/stdio_kernel.py` (NEW) | 800 |
| `vectorcode/src/mcp-bridge/group-router.js` | `mcp_client/group_router.py` (NEW) | 400 |
| `vectorcode/src/mcp-bridge/tool-discovery.js` | `mcp_client/tool_discovery.py` (NEW) | 200 |

Functions to add to existing `mcp_client/client.py`:
- `connect_stdio(command, args)` — spawn child, JSON-RPC over stdio
- `discover_tools()` — query `tools/list` from connected server
- `route_by_group(tool_name)` — prefix-based group routing (`mem.*`, `web.*`, `code.*`)

### Batch 5B — Scripts (~300 lines)

| Source | Target |
|--------|--------|
| `vectorcode/src/scripts/install-deps.js` | `scripts/install_deps.py` |
| `vectorcode/src/scripts/post-install.js` | `scripts/post_install.py` |

### Batch 5C — Ruvocal API (~100 lines)

The ruvocal web UI is SvelteKit — too heavy to port. Instead:

| Source | Target |
|--------|--------|
| `vectorcode/src/ruvocal/api.js` | `gateway/ruvocal_api.py` (port endpoints only) |
| `vectorcode/src/ruvocal/state.js` | `gateway/ruvocal_state.py` |

Web UI itself: ship the existing SvelteKit build as static assets if user wants; otherwise drop. Document at `docs/ruvocal-ui.md`.

### Batch 5D — V3 core agents (~2500 lines)

| Source | Target | Lines |
|--------|--------|------:|
| `vectorcode/v3/src/agent.ts` | `agents/v3/agent.py` (rewrite existing stub) | 600 |
| `vectorcode/v3/src/coordinator.ts` | `agents/v3/coordinator.py` (rewrite existing) | 800 |
| `vectorcode/v3/src/workflow_engine.ts` | `agents/v3/workflow_engine.py` (rewrite existing) | 500 |
| `vectorcode/v3/src/registry.ts` | `agents/v3/registry.py` | 300 |
| `vectorcode/v3/src/loader.ts` | `agents/v3/loader.py` | 200 |
| `vectorcode/v3/src/lifecycle.ts` | `agents/v3/lifecycle.py` (NEW) | 100 |

V3 agents are domain entities for the agent lifecycle system: spawn → init → ready → working → idle → terminated.

### Batch 5E — V3 implementation (selective port, ~5000 lines)

`vectorcode/v3/implementation/` has 135 files / 50k lines. **Port only high-value modules:**

| Source | Target |
|--------|--------|
| `v3/implementation/queen.ts` | `queen.py` (extend) |
| `v3/implementation/swarm.ts` | `swarm.py` (extend) |
| `v3/implementation/router.ts` | `router.py` (extend) |
| `v3/implementation/message_bus.ts` | `message_bus.py` (extend) |
| `v3/implementation/memory_backends.ts` | `memory/backends.py` (extend) |
| `v3/implementation/topology/*.ts` | `swarm_topologies/*.py` |

Skip everything else (bench harness, internal tooling, demo files).

### Batch 5F — V3 MCP tool schemas (~5000 lines)

`vectorcode/v3/mcp/` has 86 files defining MCP tool schemas. Convert to Python:

| Source | Target |
|--------|--------|
| `v3/mcp/intelligence/*.ts` | `mcp/tools/intelligence/*.py` |
| `v3/mcp/agents/*.ts` | `mcp/tools/agents/*.py` |
| `v3/mcp/memory/*.ts` | `mcp/tools/memory/*.py` |
| `v3/mcp/devtools/*.ts` | `mcp/tools/devtools/*.py` |
| `v3/mcp/security/*.ts` | `mcp/tools/security/*.py` |
| `v3/mcp/browser/*.ts` | `mcp/tools/browser/*.py` |
| `v3/mcp/neural/*.ts` | `mcp/tools/neural/*.py` |

Each TS schema becomes a Python `dataclass` with the same fields, registered in `mcp/tool_registry.py`. Implementations call back into existing VectorCode tools.

### Batch 5G — V3 plugin manifests (~10,000 lines)

`vectorcode/v3/plugins/` has 326 files / 110k lines. These are plugin **definitions**, not implementations.

Strategy: parse each `plugin.yaml` / `plugin.toml` and emit Python equivalents in `plugins/builtin/` (alongside Wave 4 VectorCode plugins).

Use a **conversion script** (one-time):

```python
# scripts/port_vectorcode_plugins.py
for plugin_dir in Path("v3/plugins").iterdir():
    manifest = parse_yaml(plugin_dir / "plugin.yaml")
    py_path = Path("plugins/builtin/vectorcode") / plugin_dir.name / "__init__.py"
    emit_python_plugin(manifest, py_path)
```

Run once, commit results, delete script.

### Batch 5H — V2 SPARC methodology (~5000 lines)

`vectorcode/v2/` has SPARC examples (Specification → Pseudocode → Architecture → Refinement → Completion).

| Source | Target |
|--------|--------|
| `v2/sparc/coordinator.ts` | `skills/builtin/sparc/coordinator.py` |
| `v2/sparc/specification.ts` | `skills/builtin/sparc/specification.py` |
| `v2/sparc/pseudocode.ts` | `skills/builtin/sparc/pseudocode.py` |
| `v2/sparc/architecture.ts` | `skills/builtin/sparc/architecture.py` |
| `v2/sparc/refinement.ts` | `skills/builtin/sparc/refinement.py` |
| `v2/sparc/completion.ts` | `skills/builtin/sparc/completion.py` |
| `v2/sparc/data_pipeline.ts` | `skills/builtin/sparc/data_pipeline.py` |
| `v2/sparc/error_handling.ts` | `skills/builtin/sparc/error_handling.py` |

Each SPARC stage becomes a slash command: `/sparc-spec`, `/sparc-pseudo`, etc. The coordinator orchestrates the full SPARC cycle.

### Batch 5I — VectorCode agents (YAML)

| Source | Target |
|--------|--------|
| `vectorcode/agents/*.yaml` | `agents/definitions/vectorcode_*.yaml` |

Direct copy + namespace.

### Batch 5J — VectorCode skills (113 markdown files)

`vectorcode/plugins/*.md` (113 files, ~124 KB) — already mostly mapped to `vectorcode/skills/vc-*.md` (143 files). Diff and absorb missing ones.

```bash
# scripts/diff_vectorcode_skills.py
for md in $(find GitHub/vectorcode_vectorcode/repo/plugins -name "*.md"); do
    name=$(basename "$md" .md)
    if [ ! -f "vectorcode/skills/vc-$name.md" ]; then
        cp "$md" "vectorcode/skills/vc-$name.md"
    fi
done
```

---

## Critical wiring

After Batch 5A: `MCPClient.connect_stdio()` works; can spawn `npx some-mcp-server` and use its tools.

After Batch 5F: V3 MCP tool schemas register at startup. `vector tools list --group intelligence` shows them.

After Batch 5G: All VectorCode plugins discoverable via `vector plugins list`.

After Batch 5H: SPARC slash commands work in REPL.

---

## Acceptance tests

1. `test_mcp_client_stdio` — connects to `npx @modelcontextprotocol/server-everything`, lists tools, calls one
2. `test_mcp_group_routing` — `mem.read` routes to memory MCP server, `web.search` to web MCP server
3. `test_v3_agent_lifecycle` — agent spawns, transitions through all states, terminates cleanly
4. `test_sparc_coordinator` — `/sparc full <task>` runs all 5 stages, produces final code
5. `test_vectorcode_plugin_loaded` — at least 50 VectorCode plugins discoverable after wave
6. `test_skill_diff_zero` — every skill in `vectorcode/plugins/*.md` has a `vectorcode/skills/vc-*.md` equivalent

**Run:** `pytest tests/test_wave5_vectorcode.py -v`

---

## Skip list (intentionally NOT ported)

- `vectorcode/v3/@claude-flow/` — vendored npm bundle. Use Python MCP servers instead.
- `vectorcode/v3/__tests__/` — Jest tests. Port logic-equivalent tests in Wave 6 (pytest).
- `vectorcode/ruvocal` SvelteKit UI — out of scope. Document as optional companion app.
- `vectorcode/v2/*.md` (1115 markdown) — these are docs, not runtime. Cherry-pick relevant ones.
- `vectorcode/scripts/*` (build/deploy scripts) — not needed; we have our own build.

---

## Handoff to Wave 6

- Tag: `git tag absorption-wave-5-complete`
- Wave 6 ports the entire test suite from both repos.
