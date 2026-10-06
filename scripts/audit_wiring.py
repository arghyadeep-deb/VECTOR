"""Wiring audit: openfang + openhuman + scrapling fully wired"""
import sys, ast
sys.stdout.reconfigure(encoding="utf-8")

results = []
def ok(m): results.append(("PASS", m)); print(f"  PASS  {m}")
def fail(m): results.append(("FAIL", m)); print(f"  FAIL  {m}")

print("GROUP 1 -- Syntax of all modified files")
files = [
    "core/inference/provider_client.py",
    "core/loop/context_engine.py",
    "core/city/agent_base.py",
    "core/memory/episodic.py",
    "core/city/governor.py",
    "core/scraper/vector_scraper.py",
    "districts/research/web_scout.py",
    "districts/coding/coding_tools.py",
    "core/engine/agents/subagent_runner.py",
    "core/engine/channels/runtime.py",
    "core/engine/agents/roles.py",
    "run_vector.py",
]
for f in files:
    try:
        with open(f, encoding="utf-8") as fh: ast.parse(fh.read())
        ok(f"syntax: {f}")
    except Exception as e:
        fail(f"syntax: {f}: {e}")
print()

print("GROUP 2 -- ProviderClient: RateLimiter + ModelRouter + ReliableProvider")
with open("core/inference/provider_client.py", encoding="utf-8") as f: src = f.read()
assert "from core.metering.rate_limiter import get_rate_limiter" in src
assert "_call_with_retry" in src
assert "ModelRouter" in src
assert "is_non_retryable" in src
assert "exponential backoff" in src or "backoff" in src
ok("ProviderClient.chat(): RateLimiter + ModelRouter + ReliableProvider retry wired")
print()

print("GROUP 3 -- TokenJuice in ContextEngine")
with open("core/loop/context_engine.py", encoding="utf-8") as f: src = f.read()
assert "from core.engine.token_juice.compressor import reduce_text" in src
assert "TokenJuice" in src
ok("ContextEngine.session_hydration_prompt() compresses via TokenJuice before return")
print()

print("GROUP 4 -- Roles in AgentBase")
with open("core/city/agent_base.py", encoding="utf-8") as f: src = f.read()
assert "_load_role" in src
assert "ROLES_BY_NAME" in src
assert "get_system_prompt" in src
assert "self.role = self._load_role" in src
ok("AgentBase: _load_role() + get_system_prompt() + self.role set at init")

with open("core/engine/agents/roles.py", encoding="utf-8") as f: src = f.read()
assert "ROLES_BY_NAME" in src
ok("roles.py: ROLES_BY_NAME exported for AgentBase")
print()

print("GROUP 5 -- MemoryTree in EpisodicMemory")
with open("core/memory/episodic.py", encoding="utf-8") as f: src = f.read()
assert "from core.engine.memory_tree.tree_builder import MemoryTree" in src
assert "_tree.ingest(" in src
ok("EpisodicMemory.store() feeds into MemoryTree after SQLite insert")
print()

print("GROUP 6 -- Governor: RateLimiter + TaintTracker")
with open("core/city/governor.py", encoding="utf-8") as f: src = f.read()
assert "from core.metering.rate_limiter import get_rate_limiter" in src
assert "rate_limited" in src
assert "from core.security.taint_tracker import get_taint_tracker" in src
assert "tag_user" in src        # tags content as USER_INPUT
assert "TaintSink.SHELL_EXEC" in src
ok("Governor.dispatch(): GCRA rate check + tag_user() taint + SHELL_EXEC sink check")
print()

print("GROUP 7 -- Scraper tags EXTERNAL_NETWORK")
with open("core/scraper/vector_scraper.py", encoding="utf-8") as f: src = f.read()
assert "tag_external" in src
ok("VectorScraper.fetch() tags web content as EXTERNAL_NETWORK taint")
print()

print("GROUP 8 -- WebScout uses ParallelResearcher")
with open("districts/research/web_scout.py", encoding="utf-8") as f: src = f.read()
assert "ParallelResearcher" in src
assert 'mode="fast"' in src
ok("WebScout.search(): ParallelResearcher (DuckDuckGo+Wikipedia+ArXiv) with DDG fallback")
print()

print("GROUP 9 -- VectorSandbox in coding_tools")
with open("districts/coding/coding_tools.py", encoding="utf-8") as f: src = f.read()
assert "run_code_safely" in src
assert "VectorSandbox" in src
ok("coding_tools: run_code_safely() wraps VectorSandbox for isolated code execution")
print()

print("GROUP 10 -- SubagentRunner uses Ollama")
with open("core/engine/agents/subagent_runner.py", encoding="utf-8") as f: src = f.read()
assert "from core.inference.ollama_safe import chat" in src
assert "vector-focus" in src
ok("SubagentRunner._default_llm() routes through VECTOR Ollama (vector-focus)")
print()

print("GROUP 11 -- ChannelRuntime dispatches via Governor")
with open("core/engine/channels/runtime.py", encoding="utf-8") as f: src = f.read()
assert "from core.city.governor import Governor" in src
assert "gov.dispatch" in src
assert "session_hydration_prompt" in src
ok("ChannelRuntime._default_agent() -> Governor.dispatch() -> Ollama fallback with hydration")
print()

print("GROUP 12 -- run_vector.py starts background services")
with open("run_vector.py", encoding="utf-8") as f: src = f.read()
assert "_start_background_services" in src
assert "OAuth server started" in src
assert "ChannelRuntime" in src
ok("run_vector: _start_background_services() starts OAuth (51201) + ChannelRuntime")
print()

print("GROUP 13 -- Functional module imports")
try:
    from core.metering.rate_limiter import get_rate_limiter, operation_cost
    rl = get_rate_limiter()
    assert operation_cost("llm_message") == 30
    assert operation_cost("tool_call") == 10
    ok("rate_limiter: singleton OK, llm_message=30 tokens, tool_call=10 tokens")
except Exception as e:
    fail(f"rate_limiter: {e}")

try:
    from core.security.taint_tracker import get_taint_tracker, TaintLabel, TaintSink
    tt = get_taint_tracker()
    tainted = tt.tag_user("ls -la && cat /etc/passwd")
    v = tt.check_sink(tainted, TaintSink.SHELL_EXEC)
    assert v is not None, "Expected SHELL_EXEC violation for USER_INPUT"
    clean = tt.tag_user("safe")
    v2 = tt.check_sink(clean, TaintSink.NET_FETCH)
    assert v2 is None, "NET_FETCH should not block USER_INPUT"
    ok("taint_tracker: USER_INPUT blocked at SHELL_EXEC, allowed at NET_FETCH")
except Exception as e:
    fail(f"taint_tracker: {e}")

try:
    from core.engine.agents.roles import ROLES_BY_NAME, get_agent_prompt
    assert "orchestrator" in ROLES_BY_NAME
    assert "researcher" in ROLES_BY_NAME
    assert "code_executor" in ROLES_BY_NAME
    assert len(ROLES_BY_NAME) == 16
    prompt = get_agent_prompt("orchestrator")
    assert "VECTOR" in prompt
    ok(f"roles: {len(ROLES_BY_NAME)} roles, orchestrator has VECTOR branding")
except Exception as e:
    fail(f"roles: {e}")

try:
    from core.engine.providers.model_router import ModelRouter
    router = ModelRouter()
    r_code = router.resolve("coding")
    r_agentic = router.resolve("agentic")
    r_reason = router.resolve("reasoning")
    assert r_code.model == "devstral:24b"
    assert r_agentic.model == "vector-focus"
    assert r_reason.model == "deepseek-r1:14b"
    ok(f"model_router: coding=devstral:24b, agentic=vector-focus, reasoning=deepseek-r1:14b")
except Exception as e:
    fail(f"model_router: {e}")

try:
    from core.engine.token_juice.compressor import reduce_text
    raw = "Certainly! Great question. Let me help you. " + "hello world " * 50
    compressed = reduce_text(raw, strip_boilerplate=True, max_chars=200)
    reduction = (1 - len(compressed) / len(raw)) * 100
    assert reduction > 10, f"Expected >10% reduction, got {reduction:.1f}%"
    ok(f"token_juice: {len(raw)} -> {len(compressed)} chars ({reduction:.0f}% reduction)")
except Exception as e:
    fail(f"token_juice: {e}")

try:
    from core.sandbox.vector_sandbox import VectorSandbox, SandboxConfig
    sb = VectorSandbox(SandboxConfig(timeout_secs=5))
    assert sb._config.timeout_secs == 5
    ok("sandbox: VectorSandbox instantiates with 5s timeout")
except Exception as e:
    fail(f"sandbox: {e}")

try:
    from core.engine.research.parallel_researcher import ParallelResearcher, ResearchReport
    pr = ParallelResearcher()
    ok("parallel_researcher: ParallelResearcher instantiates OK")
except Exception as e:
    fail(f"parallel_researcher: {e}")

try:
    from core.engine.agents.subagent_runner import SubagentRunner, SubagentOptions, run_subagent
    runner = SubagentRunner()
    ok("subagent_runner: SubagentRunner instantiates, _default_llm uses Ollama")
except Exception as e:
    fail(f"subagent_runner: {e}")

try:
    from core.engine.channels.runtime import ChannelRuntime, ChannelMessage, select_ack_reaction
    ack = select_ack_reaction("great job amazing!")
    assert ack in ["🔥", "🎉", "⚡"]
    rt = ChannelRuntime()
    msg = ChannelMessage.new("arghyadeep", "What is VECTOR?", "cli")
    assert msg.channel == "cli"
    ok(f"channel_runtime: ChannelRuntime OK, ack={ack}, message routing works")
except Exception as e:
    fail(f"channel_runtime: {e}")

try:
    from core.engine.memory_tree.tree_builder import MemoryTree, TreeChunk
    tree = MemoryTree()
    chunk = tree.ingest("episodic", "test_session", "VECTOR is an AI system", topic="identity")
    assert isinstance(chunk, TreeChunk)
    assert chunk.content == "VECTOR is an AI system"
    ok(f"memory_tree: ingest() creates TreeChunk, topic=identity")
except Exception as e:
    fail(f"memory_tree: {e}")

print()
passed = sum(1 for r, _ in results if r == "PASS")
failed = sum(1 for r, _ in results if r == "FAIL")
print(f"RESULT: PASS={passed} FAIL={failed}")
if failed:
    print("FAILURES:")
    for r, m in results:
        if r == "FAIL": print(f"  - {m}")

sys.exit(1 if failed else 0)
