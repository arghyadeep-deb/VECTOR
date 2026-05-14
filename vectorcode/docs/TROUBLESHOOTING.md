# VectorCode Troubleshooting

Common issues and fixes. Run `vector doctor` first — it diagnoses 90% of setup problems automatically.

---

## Install / Setup

### `vector: command not found`

After `pip install`, the entry point may not be on `$PATH`.

**Fix:**
```bash
# Find where pip installed it
python -m pip show vectorcode | grep Location

# Either add the bin dir to PATH, or invoke directly:
python -m vectorcode --help
# or
python /path/to/vectorcode/vector.py --help
```

### `ModuleNotFoundError: No module named 'vectorcode'`

The package layout uses `vectorcode/python/vectorcode/`. Use the launcher:

```bash
# Don't:
python -c "import vectorcode"   # fails unless installed

# Do:
python vectorcode/vector.py     # uses the launcher
# or
pip install -e .                # editable install puts it on path
```

### `cannot import name 'X' from 'config'`

Stale `.pyc` files. Clear them:

```bash
find . -name __pycache__ -type d -exec rm -rf {} +
# Windows PowerShell:
Get-ChildItem -Path . -Filter __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
```

### Unicode encoding errors on Windows

Symptoms: `'charmap' codec can't encode character ...`

**Fix:** The launcher already calls `sys.stdout.reconfigure(encoding="utf-8")`. If you're running raw Python scripts, set:

```bash
$env:PYTHONIOENCODING = "utf-8"
```

Or persistently in your PowerShell profile.

---

## Provider issues

### `vector doctor` shows Ollama offline

```
[WARN] Ollama daemon: not reachable on localhost:11434
```

**Fix:**
```bash
# Start Ollama
ollama serve

# Or if it's running on a different host:
export OLLAMA_BASE_URL=http://your-host:11434
```

### `401 Unauthorized` from Anthropic / OpenAI

Your API key is missing, expired, or invalid.

**Fix:**
```bash
# Check what's set:
vector doctor | grep -E "ANTHROPIC|OPENAI"

# Re-export:
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

# Verify:
vector models   # in REPL: /models
```

### `429 Rate limit` errors

VectorCode's credential pool will rotate to the next available key. To add more keys:

```bash
vector auth add anthropic --key sk-ant-key2
vector auth add anthropic --key sk-ant-key3
vector auth list
```

If you only have one key and you're rate-limited, the agent falls back to a different provider/model when configured. Set:

```bash
export FALLBACK_MODEL=ollama/qwen2.5-coder:7b
```

### Specific Ollama model not found

```
Model 'vector-fast' not found
```

**Fix:**
```bash
ollama list
ollama pull qwen2.5-coder:7b   # or whatever you want
vector --model ollama/qwen2.5-coder:7b
```

---

## Runtime errors

### Tool calls aren't executing

Symptoms: model says "I'll read the file..." but nothing happens.

**Diagnostic:**
```bash
vector tools list   # should show 40+ tools
```

If 0 or very few tools listed, the registry didn't auto-discover. Try:

```bash
# Check imports
python -c "import sys; sys.path.insert(0,'vectorcode/python'); sys.path.insert(0,'vectorcode/python/vectorcode'); from tools.registry import registry, discover_builtin_tools; discover_builtin_tools(); print(len(registry._snapshot_entries()))"
```

If still 0, missing optional deps blocked tool imports. Install:

```bash
pip install openai playwright firecrawl-py duckduckgo-search
```

### Agent stuck in tool loop

Symptoms: same tool called repeatedly, never reaches a final answer.

**Cause:** Model isn't following the read-loop prevention hint.

**Fix:**
- Use a stronger model (`claude-sonnet-4-5`, `gpt-5`)
- Check `vector_state.db` — read tracker should be deduplicating
- Lower max_iterations: `vector --max-iter 30`

### Out of memory / context window exceeded

Symptoms: model returns truncated output or `length` finish reason.

**Fix:**
```
> /compact            # manually compact history
> /status             # check current token usage
```

Auto-compaction triggers at 90% context. To lower the threshold, set:

```bash
export VECTOR_COMPACT_THRESHOLD=0.7
```

### `Permission denied: write to <sensitive path>`

VectorCode blocks writes to:
- `/etc/`, `/boot/`, `/usr/lib/systemd/`
- `~/.ssh/`, `~/.aws/`, `~/.gnupg/`, `~/.kube/`
- `~/.vectorcode/.env`

**To override** (not recommended): Set `VECTOR_WRITE_SAFE_ROOT` to allow writes anywhere under that root:

```bash
export VECTOR_WRITE_SAFE_ROOT=/tmp/sandbox
```

---

## Performance

### Startup is slow (>2 seconds)

Lazy-load model metadata. Set:

```bash
export VECTOR_LAZY_MODELS=1
```

Or pre-warm the model registry:

```bash
vector models > /dev/null   # caches model list
```

### First token latency is high

Local models: VRAM contention. Close other GPU apps.

Cloud models: enable prompt caching:

```bash
export VECTOR_PROMPT_CACHE=1
```

Anthropic / Bedrock support cache_control automatically.

---

## Gateway

### `vector gateway start` fails with `address already in use`

```bash
vector gateway start --port 8124   # use a different port
# or kill whatever's on 8123:
# Windows: netstat -ano | findstr :8123
# Linux/Mac: lsof -i :8123
```

### CORS errors from browser-based clients

Gateway has `allow_origins=["*"]` by default. Restrict via:

```bash
export VECTOR_GATEWAY_CORS_ORIGINS=http://localhost:3000
```

### WebSocket disconnects every ~60s

A reverse proxy (nginx, Cloudflare) is timing out idle WS. Configure proxy:

```nginx
proxy_read_timeout 3600;
proxy_send_timeout 3600;
```

---

## Memory

### Memory not being recalled

```
> @memory what did I ask about yesterday?
```

If empty, memory backend isn't writing. Check:

```bash
ls -la ~/.vectorcode/memory.md
```

Memory writes happen on agent turn end. To force a flush:

```
> /memory sync
```

### Vector search returns wrong results

Re-index:

```bash
vector memory reindex
```

---

## Debugging

### Enable verbose logging

```bash
export VECTOR_LOG_LEVEL=DEBUG
export VECTOR_LOG_JSON=1   # structured JSON output
vector ...
```

Logs at: `~/.vectorcode/logs/vector.log` (rotating, 10 MB × 5).

### Save trajectories for offline debugging

```bash
vector --save-trajectories
# trajectories saved to ~/.vectorcode/trajectories/
```

### Test a specific provider

```bash
vector models test anthropic/claude-sonnet-4-5
```

Returns `{ok, latency_ms, response}` — useful for diagnosing connection issues.

---

## Common error messages

### `_KIND_TO_VECTOR has no key 'X'`

Permission decision lookup failed. The kind is unknown. Update `acp_adapter/permissions.py` or pass `--mode autonomous`.

### `cannot import name 'get_subprocess_home'`

Old install. Pull latest and reinstall:
```bash
git pull && pip install -e . --force-reinstall
```

### `RuntimeError: Event loop is closed`

Asyncio cleanup race. Ensure `vector` is the only active event loop. If you embed in another async app, use:

```python
from vectorcode.engine import AIAgent
agent = AIAgent(...)
result = await agent.run_conversation(text)
```

(Don't wrap with `asyncio.run` if you're already inside a loop.)

---

## Getting help

1. Run `vector doctor` and share the output
2. Check logs: `tail -f ~/.vectorcode/logs/vector.log`
3. Open an issue: https://github.com/Arghyadeep-Deb/vectorcode/issues
4. Include: OS, Python version, `vector version`, and the failing command

---

## Reset everything

If you want a fresh start:

```bash
# Backup first if you care about session history
cp -r ~/.vectorcode ~/.vectorcode.bak

# Wipe state
rm -rf ~/.vectorcode

# Re-init
vector setup
```
