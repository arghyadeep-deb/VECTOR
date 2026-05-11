# Problem 19 — Code Style Violations

**Severity: LOW**
**Status: DOCUMENTED — fix incrementally**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Violations Found

### 1. requests instead of httpx (VECTOR-authored code only)

`agents/districts/investment/sentiment_bot.py` lines 51, 62:

```python
import requests
response = requests.get(url, ...)
```

Fix:
```python
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url, ...)
```

### 2. urllib.request instead of httpx (karpathy_lab + extra districts)

Files using `urllib.request.urlopen()` for Ollama calls:
- `agents/districts/karpathy_lab/data_prep.py:_call_ollama`
- `agents/districts/karpathy_lab/progress_tracker.py:_call_ollama`
- `agents/districts/karpathy_lab/architecture_builder.py:_call_ollama`
- `agents/districts/devops/__init__.py`
- `agents/districts/data_analytics/__init__.py`

All should use `core/inference/ollama_safe.chat()` wrapper which already
handles timeouts, fallbacks, and error logging.

Fix pattern:
```python
# Replace custom _call_ollama in each file with:
from core.inference.ollama_safe import chat as ollama_chat
response = ollama_chat(model=self.model, prompt=prompt, timeout=120)
```

### 3. print() in production server code

`phone_node/ambient_server.py:129`:
```python
print(f"[VECTOR][phone] ...")  # inside production server loop
```
Fix: `logger.info(f"[VECTOR][phone] ...")`

### 4. MD5 hash in decision_engine

`core/loop/decision_engine.py` line 108: `hashlib.md5(...)`.
SHA-256 is equivalent in length at 12-char truncation and not flagged by
security tooling.

```python
# Before
hashlib.md5(f"{...}".encode()).hexdigest()[:12]
# After
hashlib.sha256(f"{...}".encode()).hexdigest()[:12]
```

Note: this must be changed consistently with Problem 09 (situation hash
mismatch fix) — both fixes apply to the same lines.

### 5. Episodic DB write bloat

`core/loop/decision_engine.py` evaluates 4 candidates every 10 seconds
and logs ALL candidates to `episodic_memory`. That's 4 × 6 × 60 × 24 =
34,560 episodic rows/day from decision_engine alone.

Fix: add a sampling rate or only log the winning candidate:

```python
# Only store the winner to episodic_memory (not all 4 candidates)
# Full candidate list goes to reasoning_chains (where it belongs)
```

### 6. Extra ghost districts (empty folders)

Folders with only `__init__.py` and no actual agents:
- `agents/districts/ux_writing/`
- `agents/districts/product/`
- `agents/districts/qa_testing/`
- `agents/districts/accessibility/`
- `agents/districts/legal/`

These are not in the spec for any phase. Either scaffold them properly
or remove them to avoid confusion.
