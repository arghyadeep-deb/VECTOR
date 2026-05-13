# Wave 6 — Tests + CI

**Goal:** Port Hermes's 821 tests + Ruflo's tests to pytest. Wire up GitHub Actions CI. Reach 80%+ code coverage.

**Dependencies:** Waves 0–5 complete (everything must be ported before tests can pass).

**Est effort:** 3–4 sessions.

---

## Read before coding

1. `00-MASTER-PLAN.md`
2. `vectorcode/python/tests/conftest.py` (existing fixtures)
3. `GitHub/NousResearch_hermes-agent/repo/tests/conftest.py` (Hermes fixtures)
4. `GitHub/NousResearch_hermes-agent/repo/tests/` directory listing
5. `pytest.ini` at repo root

---

## Scope

| Source | Files | Notes |
|--------|------:|-------|
| `hermes/tests/` | 821 | Already pytest-style |
| `ruflo/tests/` | 9 | Jest — need conversion |
| `ruflo/v3/__tests__/` | ~20 | Jest — convert |
| `ruflo/v2/tests/` | ~30 | Jest — convert |
| Existing VectorCode tests | 7 | Keep (vc1–vc7 plan tests) |

**Total target:** ~880 test files, ~40,000 test lines.

---

## Test infrastructure

### Step 6.0 — Pytest config + fixtures

Create / extend:

```ini
# pytest.ini (repo root)
[pytest]
testpaths = vectorcode/python/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra -q --strict-markers --tb=short --cov=vectorcode/python/vectorcode --cov-report=term --cov-report=html
markers =
    slow: marks tests as slow (deselect with -m "not slow")
    integration: real network / model calls
    requires_ollama: needs local Ollama
    requires_anthropic: needs ANTHROPIC_API_KEY
    requires_browser: needs Chromium installed
asyncio_mode = auto
```

Add fixtures in `vectorcode/python/tests/conftest.py`:

- `tmp_session_db` — fresh SQLite session DB
- `mock_provider` — fake Anthropic/OpenAI/Ollama
- `mock_credential_pool` — pool with 3 fake keys
- `tmp_skills_dir` — isolated skills directory
- `agent_factory` — builds AIAgent with mocks
- `permission_gateway_allow_all` — bypass for unit tests
- `permission_gateway_deny_all` — for negative tests
- `mock_mcp_server` — local stdio MCP server

---

## Batch order

### Batch 6A — Engine tests (Wave 0 modules, ~80 files)

Source: `hermes/tests/test_run_agent_*.py`, `test_iteration_budget*.py`, `test_state*.py`

| Hermes test | Target |
|-------------|--------|
| `test_run_agent_basic.py` | `tests/engine/test_agent_basic.py` |
| `test_run_agent_iteration.py` | `tests/engine/test_iteration_budget.py` |
| `test_run_agent_compression.py` | `tests/engine/test_compression.py` |
| `test_run_agent_subagent.py` | `tests/engine/test_subagent.py` |
| `test_state_migration.py` | `tests/test_session_db.py` |
| `test_tool_dispatch.py` | `tests/tools/test_registry.py` |
| ... (~75 more) | ... |

### Batch 6B — Tool tests (Wave 1, ~250 files)

For every tool ported in Wave 1, port its test file. Use the source path mapping:

```
hermes/tests/test_<tool_name>.py → tests/tools/test_<tool_name>.py
```

Categories:
- File ops (~30 tests)
- Terminal/bash (~20 tests)
- Web/browser (~40 tests)
- MCP (~25 tests)
- Skills (~25 tests)
- Image/voice/vision (~30 tests)
- Memory (~20 tests)
- Delegate/clarify/todo (~15 tests)
- Approval/security (~25 tests)
- Cron/RL (~20 tests)

Replace any `mock_anthropic_client()` with VectorCode `mock_provider` fixture.

### Batch 6C — Agent subsystem tests (Wave 2, ~150 files)

Source: `hermes/tests/test_anthropic_adapter*.py`, `test_credential*.py`, `test_context*.py`, `test_memory*.py`, `test_display*.py`, etc.

| Hermes test | Target |
|-------------|--------|
| `test_anthropic_adapter.py` | `tests/transports/test_anthropic.py` |
| `test_bedrock_adapter.py` | `tests/transports/test_bedrock.py` |
| `test_credential_pool_rotation.py` | `tests/test_credentials.py` |
| `test_context_compressor.py` | `tests/context/test_compactor.py` |
| `test_memory_manager.py` | `tests/memory/test_manager.py` |
| `test_display_diff.py` | `tests/display/test_diff_preview.py` |
| `test_redact.py` | `tests/utils/test_redact.py` |
| ... | ... |

### Batch 6D — Gateway tests (Wave 3 part A, ~80 files)

| Hermes test | Target |
|-------------|--------|
| `test_gateway_run.py` | `tests/gateway/test_run.py` |
| `test_gateway_session.py` | `tests/gateway/test_session.py` |
| `test_gateway_telegram.py` | `tests/gateway/platforms/test_telegram.py` |
| `test_gateway_discord.py` | `tests/gateway/platforms/test_discord.py` |
| ... (one per platform) | ... |
| `test_stream_consumer.py` | `tests/gateway/test_stream_consumer.py` |

### Batch 6E — CLI tests (Wave 3 part B, ~100 files)

| Hermes test | Target |
|-------------|--------|
| `test_cli_main.py` | `tests/cli/test_main.py` |
| `test_cli_auth.py` | `tests/cli/test_auth.py` |
| `test_cli_doctor.py` | `tests/cli/test_doctor.py` |
| `test_cli_models.py` | `tests/cli/test_models.py` |
| `test_cli_setup.py` | `tests/cli/test_setup.py` |
| `test_cli_profiles.py` | `tests/cli/test_profiles.py` |
| ... (~95 more) | ... |

### Batch 6F — Plugin / cron / ACP tests (Wave 4, ~60 files)

| Hermes test | Target |
|-------------|--------|
| `test_plugins_loader.py` | `tests/plugins/test_loader.py` |
| `test_plugins_sandbox.py` | `tests/plugins/test_sandbox.py` |
| `test_cron_scheduler.py` | `tests/cron/test_scheduler.py` |
| `test_acp_server.py` | `tests/acp/test_server.py` |
| `test_acp_session.py` | `tests/acp/test_session.py` |
| ... | ... |

### Batch 6G — Ruflo tests (Wave 5, ~60 files)

Convert Jest → pytest:

| Ruflo test (TS/Jest) | Target (Python/pytest) |
|----------------------|------------------------|
| `ruflo/tests/mcp-bridge.test.ts` | `tests/mcp/test_bridge.py` |
| `v3/__tests__/agent.test.ts` | `tests/agents/v3/test_agent.py` |
| `v3/__tests__/coordinator.test.ts` | `tests/agents/v3/test_coordinator.py` |
| `v2/sparc/__tests__/*.test.ts` | `tests/skills/sparc/test_*.py` |
| ... | ... |

Conversion rules:
- `describe(...)` → `class Test...` or module-level
- `it(...)` → `def test_...`
- `expect(x).toBe(y)` → `assert x == y`
- `beforeEach` → pytest fixture
- `jest.mock(...)` → `monkeypatch` / `unittest.mock.patch`

### Batch 6H — Integration + E2E (~50 files, NEW)

End-to-end tests that hit real local services:

```python
# tests/e2e/test_full_loop.py
@pytest.mark.integration
@pytest.mark.requires_ollama
async def test_full_agent_loop_against_ollama():
    """vector run "list files in this dir" → returns real file list"""
    result = await run_command("vector run 'list files in tests/'")
    assert result.exit_code == 0
    assert "test_full_loop.py" in result.stdout
```

E2E targets:
- Full agent loop against local Ollama
- Gateway → telegram webhook → response
- Plugin install + invoke
- Cron job execution
- MCP client → local MCP server → tool call
- ACP session lifecycle

### Batch 6I — Property + fuzz (NEW, optional)

| Module | Test |
|--------|------|
| `tools/path_security.py` | Hypothesis: random paths never escape sandbox |
| `tools/file_safety.py` | Hypothesis: blocked components always rejected |
| `utils/redact.py` | Hypothesis: API keys never leak through redaction |
| `tools/schema_sanitizer.py` | Hypothesis: malformed schemas don't crash |

---

## CI configuration

`.github/workflows/test.yml`:

```yaml
name: tests
on: [push, pull_request]
jobs:
  unit:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -e ".[dev]"
      - run: pytest -m "not integration and not slow" --cov
      - uses: codecov/codecov-action@v4

  integration:
    runs-on: ubuntu-latest
    services:
      ollama:
        image: ollama/ollama:latest
        ports: [11434:11434]
    steps:
      - uses: actions/checkout@v4
      - run: |
          ollama pull qwen2.5-coder:1.5b
          pytest -m "integration and requires_ollama"

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff black mypy
      - run: ruff check vectorcode/
      - run: black --check vectorcode/
      - run: mypy vectorcode/python/vectorcode/
```

---

## Coverage targets

| Module | Target |
|--------|-------:|
| `engine/` | 90% |
| `tools/` | 85% |
| `transports/` | 85% |
| `providers/` | 80% |
| `gateway/` | 70% |
| `cli/` | 70% |
| `plugins/` | 80% |
| `mcp_client/` + `mcp/` | 85% |
| `agents/` | 75% |
| **Overall** | **≥80%** |

CI fails if coverage drops below 80%.

---

## Acceptance

1. `pytest -m "not integration"` — green on CI in <5 min on Ubuntu
2. `pytest -m integration` — green when Ollama available
3. Coverage ≥80% reported by codecov
4. Lint clean: `ruff`, `black`, `mypy` no errors
5. All 880 ported tests pass on Windows + Linux + macOS
6. New PRs blocked if any test fails or coverage drops

---

## Handoff to Wave 7

- Tag: `git tag absorption-wave-6-complete`
- Wave 7 packages everything for distribution.
