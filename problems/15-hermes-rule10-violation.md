# Problem 15 — Hermes RULE 10 Violation + Three Competing Implementations

**Severity: HIGH**
**Status: DOCUMENTED — requires consolidation to ACP protocol**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Symptom

Three separate HermesAdapter implementations exist and none of them connects
to the actual Hermes agent protocol. Communications district is effectively dead.

## Root Cause

RULE 10 states:
> "Hermes already has multi-platform messaging — do not rebuild from scratch.
> Use `ollama launch hermes --model kimi-k2.6:cloud`"

What was built instead:

| File | What it does | Problem |
|------|-------------|---------|
| `agents/districts/communications/hermes_adapter.py` | HTTP client to custom `/notify`, `/messages` REST API | These endpoints don't exist on Hermes |
| `integrations/hermes/hermes_adapter.py` | Different HTTP client, also targets localhost:8080 | Different endpoints, same wrong approach |
| `agents/districts/communications/hermes/` | Full ACP protocol implementation (cloned Hermes codebase) | Never imported or invoked by VECTOR |

The actual Hermes ACP protocol lives at
`agents/districts/communications/hermes/acp_adapter/entry.py` but is never
called by any VECTOR loop code.

## Additional Issue

`CONFIG` has no `hermes` key. Both custom adapters do
`CONFIG.get("hermes", {})` which returns `{}`, so the Hermes URL always
falls back to the hardcoded `"http://127.0.0.1:8080"`. No configuration
is possible without code changes.

## Fix Required

### Step 1: Delete the two hand-rolled adapters

- `agents/districts/communications/hermes_adapter.py` → DELETE
- `integrations/hermes/hermes_adapter.py` → DELETE

### Step 2: Add hermes config block to core/config.py

```python
hermes_url: str = Field(default="http://127.0.0.1:8080", env="HERMES_URL")
hermes_acp_port: int = Field(default=8765, env="HERMES_ACP_PORT")
```

### Step 3: Wire the ACP adapter

`agents/districts/communications/__init__.py` or a new `hermes_bridge.py`:

```python
from agents.districts.communications.hermes.acp_adapter.entry import run_acp_adapter
# Or use the HTTP bridge that Hermes exposes after `ollama launch hermes`
```

### Step 4: Add gateway for message actions

`send_message_routine` → YELLOW gate
`send_message_important` → RED gate

These are currently not gated through `permission_gateway.py` in any
hermes adapter.

## Temporary Workaround

Until Hermes ACP is properly wired, the `cloud/comms_service/service.py`
Hermes bridge subprocess approach is the most honest: start Hermes as a
subprocess and delegate, returning an error if Hermes is not running (not
`ok: True` unconditionally as the current code does).
