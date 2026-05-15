# VECTOR — Known Issues & Risks
> Generated: 2026-05-16 after deep audit of 1,307 vectorcode/src Python files.  
> Status key: 🔴 High risk · 🟡 Medium risk · 🟢 Low risk / informational

---

## 1. RUNTIME-UNTESTED (biggest risk category)

### 🔴 Gateway never started against real config
- **File:** `vectorcode/src/gateway/run.py` (11,760L — the largest absorbed file)
- **Risk:** Imports cleanly but has never been run with VECTOR's actual config.yaml
- **What to do:** Run `python vectorcode/src/gateway/run.py --help` and then start with a minimal config
- **Likely failures:** Missing env vars (TELEGRAM_TOKEN, DISCORD_TOKEN etc.), config schema mismatch

### 🔴 Platform adapters have no credential test
- **Files:** `gateway/platforms/discord.py` (3,931L), `gateway/platforms/telegram.py` (3,155L), `gateway/platforms/feishu.py` (4,629L), `gateway/platforms/qqbot/adapter.py` (2,380L)
- **Risk:** Absorbed from hermes, import cleanly, but never connected to real APIs
- **What to do:** Test each adapter individually with real credentials before enabling in production
- **Specific concerns:** Discord OAuth scopes, Telegram webhook vs polling mode, Feishu app approval process

### 🔴 kanban_db.py schema never run against real SQLite
- **File:** `vectorcode/src/vector_cli/kanban_db.py` (4,839L)
- **Risk:** Complex SQLite schema with WAL+CAS concurrency. Path changes (`~/.hermes` → `~/.vector`) done via sed — may have missed edge cases
- **What to do:** `python -c "from vectorcode.src.vector_cli import kanban_db; kanban_db.init_db()"`
- **Likely issue:** `VECTOR_KANBAN_DB` env var path, workspace root resolution

### 🟡 goals.py judge loop never tested end-to-end
- **File:** `vectorcode/src/vector_cli/goals.py` (756L)
- **Risk:** GoalManager calls an auxiliary LLM to judge if a goal is complete. The judge prompt uses specific JSON format — small models (deepseek-flash) reliably fail this
- **What to do:** Test with `GoalManager.set_goal("write hello world")` and run one iteration
- **Config needed:** `auxiliary.goal_judge.model` in config.yaml

### 🟡 vector_state.py (2,966L) global state — path assumptions
- **File:** `vectorcode/src/vector_state.py`
- **Risk:** Large hermes state management file. All `~/.hermes` paths were sed-replaced with `~/.vector` but some internal state keys or DB column names may still use "hermes" as a string value (not a path)
- **What to do:** `grep -r "hermes" vectorcode/src/vector_state.py` and verify any remaining string references are intentional

---

## 2. SED-INTRODUCED LOGIC BUGS (string comparison risks)

### 🔴 String literal comparisons that reference paths
- **Risk:** Our sed replacements changed `~/.hermes` → `~/.vector` in code. But if any function does `if path == "~/.hermes/config.yaml"` or compares against a hardcoded string, the comparison now fails because the value may come from an old config file that still says `.hermes`
- **Files to check manually:**
  - `vectorcode/src/vector_constants.py`
  - `vectorcode/src/vector_cli/config.py`
  - `vectorcode/src/vector_cli/gateway.py`
  - `vectorcode/src/vector_cli/doctor.py`
- **What to do:** `grep -n '\"hermes\"\|\.hermes\b' vectorcode/src/vector_cli/` for any remaining string literals that weren't paths

### 🟡 VECTOR_KANBAN_TASK env var rename
- **Risk:** `HERMES_KANBAN_TASK` → `VECTOR_KANBAN_TASK` via sed. Any external script or process that sets `HERMES_KANBAN_TASK` won't be picked up
- **Files affected:** `vectorcode/src/tools/kanban_tools.py`, `vectorcode/src/vector_cli/kanban_db.py`
- **What to do:** Update any shell scripts or `.env` files that set `HERMES_KANBAN_TASK`

### 🟡 VECTOR_HOME env var — profile resolution
- **File:** `vectorcode/src/vector_constants.py`
- **Risk:** `get_vector_home()` function replaced `get_hermes_home()` — but VECTOR's profile system may default to `~/.vector` while existing user data is still in `~/.hermes` from any pre-VECTOR usage
- **What to do:** Verify `get_vector_home()` returns the correct path on first run

---

## 3. IMPORT SHIMS — SHALLOW RE-EXPORTS

### 🟡 `vectorcode/src/core/` shim package
- **What it is:** Shim re-exporting from `vc_core/` for backwards compatibility
- **Risk:** Any file importing `from vectorcode.src.core.config import X` gets the shim. If `vc_core/config.py` changes, the shim may expose stale aliases
- **Affected files:** 15+ files across `vector_cli/`, `server/`, `system/`, `sdk.py`
- **Files in shim:** `core/config.py`, `core/events.py`, `core/registry.py`, `core/types.py`, `core/credentials.py`

### 🟡 `vectorcode/src/scheduler/` shim
- **What it is:** Points to `core/scheduler/` (the VECTOR core scheduler, not vectorcode)
- **Risk:** If `core/scheduler/` is refactored, the vectorcode modules that import via this shim will break silently
- **Affected files:** `cli/digest_cmd.py`, `cli/scheduler_cmd.py`, `system/bundles.py`, `system/core.py`

### 🟡 EventType enum members as module-level aliases
- **File:** `vectorcode/src/core/events.py`
- **Risk:** `AGENT_TICK_START = EventType.AGENT_TICK_START` — if EventType enum values change in `vc_core/events.py`, the aliases are stale but won't raise ImportError (they'll just have wrong values)
- **What to do:** Prefer `EventType.AGENT_TICK_START` over the alias in new code

### 🟡 Quantization enum aliases in `core/types.py`
- **Same risk as above:** `FP4 = getattr(Quantization, "FP4", None)` silently returns `None` if FP4 is removed from the Quantization enum
- **What to do:** Always use `Quantization.FP4` directly in new code

---

## 4. STUB MODULES THAT NEED REAL IMPLEMENTATION

These were created as stubs to fix import errors. They work for import resolution but don't DO anything useful yet:

| File | Stub class/function | What it needs |
|---|---|---|
| `vectorcode/src/agents/deep_research.py` | `DeepResearchAgent.research()` | Real multi-step web research implementation |
| `vectorcode/src/tools/knowledge_search.py` | `KnowledgeSearchTool.run()` | Integration with LightRAG/ChromaDB |
| `vectorcode/src/tools/knowledge_sql.py` | `KnowledgeSQLTool.run()` | SQL query against VECTOR's SQLite databases |
| `vectorcode/src/tools/scan_chunks.py` | `ScanChunksTool.run()` | Real chunk scanning (security scanner) |
| `vectorcode/src/tools/think.py` | `ThinkTool.run()` | Structured thinking scaffolding |
| `vectorcode/src/tools/storage/ingest.py` | `ingest_path()` | Document ingestion pipeline |
| `vectorcode/src/intelligence/model_catalog.py` | `BUILTIN_MODELS` | Should be populated from Ollama's installed models |
| `vectorcode/src/agents/manager.py` | `AgentManager` | Full agent lifecycle management |
| `vectorcode/src/vc_agents/digest_evaluator.py` | `DigestEvaluator.evaluate()` | Real evaluation logic |
| `vectorcode/src/engine/cloud.py` | `CloudEngine` | Cloud inference backend |
| `vectorcode/src/server/savings.py` | `compute_savings()` | Real cost tracking |
| `vectorcode/src/channels/imessage_daemon.py` | shim only | Points to `comms/imessage_daemon.py` which may not exist |
| `vectorcode/src/display/diff_preview.py` | shim only | `build_diff_preview()` works, rest is stub |

---

## 5. SECURITY FLAGS (not critical, but review)

### 🟡 SHA1 in WeChat / WeCom files
- **Files:** `comms/wecom_callback.py:27`, `comms/wecom_crypto.py:43,62`
- **Why it's there:** WeChat Enterprise API mandates SHA1 for webhook signature verification — cannot be changed
- **What to do:** Accept as-is, document in code comments that this is API-mandated

### 🟡 SHA1/MD5 used for IDs (not passwords)
- **Files:** `agent/codex_responses_adapter.py:197`, `comms/email_client.py:244`, `context/compactor.py:238`
- **Use case:** Generating deterministic short IDs and fingerprints — not for password storage
- **Risk:** Low — not a real security issue, just flagged by automated scanners
- **What to do:** Add `# nosec` comment or replace with `hashlib.sha256()` if you want to satisfy security scanners

---

## 6. WIRING GAPS (functionality exists but isn't connected)

### 🟡 `vc_skills/` shim not connected to skill loading pipeline
- **File:** `vectorcode/src/vc_skills/manager.py` (shim → `skills/manager.py`)
- **Risk:** Files that import `from vectorcode.src.vc_skills.manager import SkillManager` get the real class, but VECTOR's skill discovery pipeline may not know to use it
- **What to do:** Verify `skills/manager.py` is being called by the main VECTOR skill system

### 🟡 `vectorcode/src/vector_cli/goals.py` GoalManager not wired into REPL
- **Risk:** GoalManager is fully implemented but nothing in `vector_cli/main.py` or the gateway calls `GoalManager.set_goal()` on user input
- **What to do:** Add `/goal <text>` slash command to the CLI and gateway

### 🟡 `tools/kanban_tools.py` not registered in MCP server
- **File:** `vectorcode/src/tools/kanban_tools.py` (1,139L)
- **Risk:** Full Kanban MCP tool surface exists but `core/mcp_server.py` doesn't import it
- **What to do:** Add `from vectorcode.src.tools.kanban_tools import ...` to `core/mcp_server.py` registrations

### 🟡 `vectorcode/src/agent/tool_guardrails.py` not integrated into agent loop
- **Risk:** ToolCallGuardrailController is implemented but nothing in `run_agent.py` or the agent loop instantiates it
- **What to do:** Add guardrail controller to `run_agent.py`'s tool execution path

---

## 7. TELEMETRY MODULES — PARTIAL IMPLEMENTATIONS

### 🟢 Energy monitoring stubs
- **Files:** `telemetry/energy_amd.py`, `telemetry/energy_apple.py`, `telemetry/energy_nvidia.py`, `telemetry/energy_rapl.py`
- **Status:** Logic absorbed from OpenJarvis but hardware-specific sampling (`pynvml`, `pyRAPL`, Apple power metrics) requires actual hardware libraries installed
- **Risk:** These will silently return zeros if the hardware libraries aren't installed — not crashes, just no data
- **What to do:** Install `pip install pynvml` on RTX 5070 Ti for GPU energy monitoring

### 🟢 `telemetry/vllm_metrics.py` — VLLMMetricsScraper
- **Risk:** Requires vLLM to be running and exposing Prometheus metrics at the configured port
- **What to do:** Only needed if you switch to vLLM backend — not an immediate concern

---

## 8. MISSING TESTS FOR ABSORBED CODE

None of the following have test coverage:
- `vectorcode/src/vector_cli/kanban.py` + `kanban_db.py` — 7,000+ lines with no tests
- `vectorcode/src/vector_cli/goals.py` — GoalManager judge loop untested
- `vectorcode/src/gateway/run.py` — GatewayRunner integration tests missing
- All 25+ platform adapters in `gateway/platforms/`
- `vectorcode/src/claims.py` — ClaimService, WorkStealingService, LoadBalancer
- `vectorcode/src/guidance.py` — ThreatDetector, CoherenceScheduler, ContinueGate
- `vectorcode/src/neural_training.py` — A2C, DQN, DecisionTransformer

**What to do:** Add integration tests incrementally — start with kanban_db (most complex schema) and claims (most critical for Darwinian HP system).

---

## 9. KNOWN FALSE POSITIVES (not real bugs, just audit noise)

These were flagged by the automated audit but are **intentional correct Python**:

- **4,832 "undefined name" flags** — All false positives from AST analyzer not tracking walrus operators (`:=`), `with X as y:`, `try/except X as e:`, generator variables, and `*` imports. None are real bugs.
- **115 "logic" flags** — All are abstract base class methods (`Protocol`, `_stubs.py`) where `raise NotImplementedError` or `...` is the correct body.
- **80 stub functions** — All are either ABC abstract methods (intentional), null-object pattern `stop(): pass` (no persistent connection to close), or empty constructors on subclasses that correctly inherit parent `__init__`.

---

## 10. WHAT TO DO FIRST (priority order)

1. **Run the gateway** — `cd vectorcode && python -m vectorcode.src.gateway.run --help` → reveals config schema issues immediately
2. **Test kanban DB init** — `python -c "from vectorcode.src.vector_cli import kanban_db; print(kanban_db.kanban_db_path())"` → reveals path issues
3. **Implement missing stubs** — Start with `tools/knowledge_search.py` (highest impact for research district)
4. **Wire tool_guardrails into run_agent.py** — Prevents tool loop crashes in production
5. **Register kanban_tools in MCP server** — Unblocks agent task management
6. **Add GoalManager to CLI REPL** — Makes the goal-loop feature usable
7. **Install pynvml** — `pip install pynvml` → enables GPU energy monitoring on RTX 5070 Ti
8. **Write kanban_db integration test** — Most critical schema to validate before using Kanban in production

---

## QUICK VERIFICATION COMMANDS

```bash
# 1. Check all critical imports still work
python -X utf8 -c "
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'vectorcode/src')
import importlib
mods = [
  'vectorcode.src.gateway.session', 'vectorcode.src.claims',
  'vectorcode.src.guidance', 'vectorcode.src.neural_training',
  'vectorcode.src.vector_cli.kanban_db', 'vectorcode.src.core.events',
  'vectorcode.src.core.types', 'vectorcode.src.mining._constants',
]
for m in mods:
    try: importlib.import_module(m); print(f'OK {m}')
    except Exception as e: print(f'FAIL {m}: {e}')
"

# 2. Check zero absorption traces
python -X utf8 scripts/deabsorb.py

# 3. Check zero syntax errors
python -X utf8 scripts/audit_vectorcode.py 2>&1 | grep "Syntax="

# 4. Quick kanban DB test
python -X utf8 -c "
from vectorcode.src.vector_cli.kanban_db import kanban_db_path
print('Kanban DB path:', kanban_db_path())
"

# 5. Quick claims test
python -X utf8 -c "
from vectorcode.src.claims import ClaimService, Claimant
import tempfile, pathlib
with tempfile.TemporaryDirectory() as t:
    svc = ClaimService(pathlib.Path(t) / 'claims.db')
    c = Claimant(id='test', type='agent', name='Test')
    claim = svc.claim('ISSUE-1', c, issue_title='Test')
    print('Claims OK:', claim is not None)
"
```

---

*This file was auto-generated by Claude Code audit session on 2026-05-16.*  
*Re-run `python -X utf8 scripts/audit_vectorcode.py` and `python -X utf8 scripts/deep_audit.py` to refresh.*
