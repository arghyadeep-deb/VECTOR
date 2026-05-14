# Getting Started with VectorCode

VectorCode is an autonomous coding agent that runs locally, connects to multiple LLM providers, and executes real tools (file ops, shell commands, web search, browser, MCP servers).

This guide gets you from zero to a working agent in 5 minutes.

---

## Prerequisites

| Requirement | Why |
|------------|-----|
| Python 3.11+ | Core runtime |
| Git | Cloning + version control tools |
| Ollama (optional) | Local model inference (free, private) |
| Docker (optional) | Sandboxed code execution |
| Node.js 18+ (optional) | MCP servers via `npx` |

---

## 1. Install

### Option A: From source (current)

```bash
git clone https://github.com/Arghyadeep-Deb/vectorcode.git
cd vectorcode
pip install -e ".[dev]"
```

### Option B: From PyPI (when published)

```bash
pip install vectorcode
```

### Option C: Docker

```bash
docker pull ghcr.io/arghyadeep-deb/vectorcode:latest
docker run -it --rm ghcr.io/arghyadeep-deb/vectorcode:latest
```

---

## 2. Verify install

```bash
vector version
vector doctor
```

`vector doctor` runs ~20 checks:
- Python version
- Required binaries (git, ollama, docker)
- Python dependencies
- VectorCode core modules
- Environment variables for provider API keys

If all checks show `[OK]` you're ready.

---

## 3. Configure a model provider

VectorCode supports 7 providers out of the box:

| Provider | Setup | API Key Env Var |
|----------|-------|-----------------|
| **Ollama** (recommended for local) | `ollama serve` | none — local |
| Anthropic Claude | sign up at console.anthropic.com | `ANTHROPIC_API_KEY` |
| OpenAI | sign up at platform.openai.com | `OPENAI_API_KEY` |
| Google Gemini | sign up at aistudio.google.com | `GOOGLE_API_KEY` |
| AWS Bedrock | configure aws CLI | `AWS_ACCESS_KEY_ID` |
| Groq | sign up at groq.com | `GROQ_API_KEY` |
| OpenRouter | sign up at openrouter.ai | `OPENROUTER_API_KEY` |

### Quick start with Ollama (no API keys needed)

```bash
# Install Ollama: https://ollama.ai
ollama pull qwen2.5-coder:7b

# Run VectorCode pointing at it
vector --model ollama/qwen2.5-coder:7b
```

### Quick start with Anthropic

```bash
export ANTHROPIC_API_KEY=sk-ant-...
vector --model anthropic/claude-sonnet-4-5
```

---

## 4. First task

```bash
$ vector
```

You'll see the welcome banner and a prompt:

```
repl · vector-fast
> 
```

Try a simple task:

```
> read the README.md and summarize it in 3 bullets
```

VectorCode will:
1. Call `read_file` tool to load README.md
2. Pass the content to the model
3. Stream back the 3-bullet summary

---

## 5. Common workflows

### Code review

```
> review the changes in src/main.py for bugs and performance issues
```

### Refactor

```
> rename `process_data` to `transform_records` everywhere in this repo
```

### Bug fix with TDD

```
> /sparc full add a unit test that catches the bug in tests/test_widget.py, then fix it
```

### Multi-step research + write

```
> @docs/spec.md research how openai's function calling differs from anthropic's tool use, then write a comparison doc in docs/compare.md
```

### Web research

```
> /search latest benchmarks for code generation models 2026
```

---

## 6. Slash commands

Inside the REPL, type `/` for quick actions:

| Command | What |
|---------|------|
| `/help` | List all commands |
| `/status` | Session info (model, mode, token usage, uptime) |
| `/model <provider/name>` | Switch model |
| `/models` | List configured providers + reachability |
| `/sparc full <task>` | Run SPARC methodology pipeline |
| `/compact` | Manually trigger context compression |
| `/cost` | Token usage + per-provider estimated cost |
| `/diff` | Show all file changes made this session |
| `/commit [msg]` | Commit changes with AI-generated message |
| `/spawn <task>` | Spawn a subagent |
| `/save` / `/restore` | Save / load session |
| `/clear` | Clear conversation |
| `/quit` | Exit |

---

## 7. Context references

Use `@` to attach files, diffs, URLs, or git refs:

| Reference | Effect |
|-----------|--------|
| `@path/to/file.py` | Inject file contents |
| `@diff` | Inject `git diff` output |
| `@diff HEAD~3` | Inject diff between HEAD and 3 commits ago |
| `@url https://example.com/doc` | Fetch + inject web page |
| `@folder src/utils/` | Inject all files in folder |
| `@git log --oneline -10` | Inject git log |

Example:
```
> @src/auth.py @tests/test_auth.py refactor the auth module to use JWT and update the tests
```

---

## 8. Gateway mode (HTTP API)

Run VectorCode as a service for IDE plugins, scripts, or other agents:

```bash
vector gateway start --host 127.0.0.1 --port 8123
```

Then call the API:

```bash
curl -X POST http://localhost:8123/run \
  -H "Content-Type: application/json" \
  -d '{"input": "list all .py files", "model": "ollama/qwen2.5-coder:7b"}'
```

Endpoints: `/run`, `/stream` (SSE), `/health`, `/status`, `/sessions`, `/sessions/{id}/cancel`, `/compact`, `/reset`, `/model`.

---

## 9. Cron (scheduled tasks)

```bash
vector cron add "0 9 * * *" "summarize my GitHub activity yesterday and email it to me"
vector cron list
vector cron daemon start  # runs in background
```

---

## 10. Plugins

Drop a folder into `~/.vectorcode/plugins/<name>/` with a `plugin.toml` and Python file:

```toml
# plugin.toml
[plugin]
name = "spotify"
version = "0.1.0"
```

```python
# __init__.py
def pre_llm_call(agent, message):
    """Inject current Spotify track into context."""
    return f"[Now playing: {get_current_track()}]"
```

---

## 11. Profiles

Switch between configurations (work / research / readonly):

```bash
vector profile create work --model anthropic/claude-sonnet-4-5 --mode standard
vector profile use work
vector  # uses 'work' profile
```

---

## What next?

- [API_REFERENCE.md](API_REFERENCE.md) — full module/function reference
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common issues + fixes
- `vector --help` — every command-line flag
