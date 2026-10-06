"""Generate data/training/seed.jsonl and data/training/coding/seed.jsonl.

50 hand-written instruction/response pairs covering VECTOR's core domains:
coding, system architecture, security, memory/research, and general AI.

Run: python scripts/build_seed_dataset.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

EXAMPLES: list[dict] = [
    # ── Python / async (1-10) ────────────────────────────────────────────
    {
        "instruction": "Write an async Python function that retries a coroutine up to n times with exponential backoff.",
        "input": "",
        "output": (
            "async def retry(coro_fn, retries=3, base=1.0):\n"
            "    import asyncio\n"
            "    for attempt in range(retries):\n"
            "        try:\n"
            "            return await coro_fn()\n"
            "        except Exception:\n"
            "            if attempt == retries - 1:\n"
            "                raise\n"
            "            await asyncio.sleep(base * 2**attempt)"
        ),
    },
    {
        "instruction": "Show a FastAPI endpoint that returns a JSON health-check with status 200.",
        "input": "",
        "output": (
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n\n"
            "@app.get('/health')\n"
            "async def health():\n"
            "    return {'status': 'ok'}"
        ),
    },
    {
        "instruction": "Write a Python function to insert a row into SQLite using parameterised queries.",
        "input": "Table: users(id TEXT, name TEXT, hp INTEGER)",
        "output": (
            "def insert_user(conn, user_id: str, name: str, hp: int) -> None:\n"
            "    conn.execute(\n"
            "        'INSERT INTO users (id, name, hp) VALUES (?, ?, ?)',\n"
            "        (user_id, name, hp),\n"
            "    )\n"
            "    conn.commit()"
        ),
    },
    {
        "instruction": "Configure loguru to rotate logs at 10 MB and retain 7 days.",
        "input": "",
        "output": (
            "from loguru import logger\n"
            "logger.add(\n"
            "    'logs/vector.log',\n"
            "    rotation='10 MB',\n"
            "    retention='7 days',\n"
            "    level='INFO',\n"
            "    colorize=False,\n"
            ")"
        ),
    },
    {
        "instruction": "Write a Python async context manager that measures and logs execution time.",
        "input": "",
        "output": (
            "from contextlib import asynccontextmanager\n"
            "import time\n"
            "from loguru import logger\n\n"
            "@asynccontextmanager\n"
            "async def timed(label: str):\n"
            "    start = time.perf_counter()\n"
            "    try:\n"
            "        yield\n"
            "    finally:\n"
            "        elapsed = time.perf_counter() - start\n"
            "        logger.info('[VECTOR][timer] {} took {:.3f}s', label, elapsed)"
        ),
    },
    {
        "instruction": "Explain asyncio.gather and give a short example.",
        "input": "",
        "output": (
            "asyncio.gather runs multiple coroutines concurrently and returns their "
            "results in order.\n\n"
            "async def main():\n"
            "    a, b = await asyncio.gather(fetch('url_a'), fetch('url_b'))\n"
            "    return a, b"
        ),
    },
    {
        "instruction": "Write a Pydantic BaseModel for an agent health record.",
        "input": "Fields: agent_id (str), name (str), hp (int 0-1000), district (str).",
        "output": (
            "from pydantic import BaseModel, Field\n\n"
            "class AgentHealth(BaseModel):\n"
            "    agent_id: str\n"
            "    name: str\n"
            "    hp: int = Field(default=500, ge=0, le=1000)\n"
            "    district: str"
        ),
    },
    {
        "instruction": "How do you avoid circular imports in Python packages?",
        "input": "",
        "output": (
            "Use lazy imports inside functions or methods rather than at module level. "
            "Alternatively, extract shared types into a separate _types.py module that "
            "both sides can import without creating a cycle."
        ),
    },
    {
        "instruction": "Write a Python dataclass that is comparable by a numeric score field.",
        "input": "",
        "output": (
            "from dataclasses import dataclass, field\n\n"
            "@dataclass(order=True)\n"
            "class ScoredResult:\n"
            "    score: float\n"
            "    label: str = field(default='', compare=False)\n"
            "    data: dict = field(default_factory=dict, compare=False)"
        ),
    },
    {
        "instruction": "Write a rate-limiting async decorator that allows at most N calls per second.",
        "input": "",
        "output": (
            "import asyncio, time\n"
            "from functools import wraps\n\n"
            "def rate_limit(calls_per_sec: float):\n"
            "    min_interval = 1.0 / calls_per_sec\n"
            "    last = [0.0]\n"
            "    def decorator(fn):\n"
            "        @wraps(fn)\n"
            "        async def wrapper(*args, **kwargs):\n"
            "            elapsed = time.monotonic() - last[0]\n"
            "            if elapsed < min_interval:\n"
            "                await asyncio.sleep(min_interval - elapsed)\n"
            "            last[0] = time.monotonic()\n"
            "            return await fn(*args, **kwargs)\n"
            "        return wrapper\n"
            "    return decorator"
        ),
    },
    # ── VECTOR system (11-20) ─────────────────────────────────────────────
    {
        "instruction": "How does the VECTOR HP system work?",
        "input": "",
        "output": (
            "Agents start at 500 HP (range 0-1000). Completing tasks awards +30 to +100 HP; "
            "failures deduct HP. An agent at 0 HP dies — ghost memory (lessons, best decisions) "
            "is preserved and passed to the next generation. HP also gates model access: "
            ">800 HP uses Claude Sonnet, 600-800 cloud orchestrator, 400-600 focus model, "
            "200-400 reasoning model, <200 ambient model."
        ),
    },
    {
        "instruction": "What does VECTOR's permission gateway do?",
        "input": "",
        "output": (
            "The permission gateway classifies every proposed action as GREEN (auto-approved), "
            "YELLOW (requires confirmation), or RED (blocked/requires human approval). "
            "No LLM call goes directly to an external API — all actions route through the "
            "gateway first. This prevents autonomous agents from making irreversible or risky "
            "moves without oversight."
        ),
    },
    {
        "instruction": "Explain VECTOR's autonomous loop lifecycle.",
        "input": "",
        "output": (
            "The loop runs four phases continuously:\n"
            "1. observe (0.5s) — collect events from sensors, inbox, schedule\n"
            "2. think (event-driven) — context engine + decision engine selects best action\n"
            "3. act (permission-gated) — gateway approves, governor dispatches to district\n"
            "4. reflect (2AM) — daily review, HP updates, training data generation"
        ),
    },
    {
        "instruction": "What happens when an agent's HP drops to zero?",
        "input": "",
        "output": (
            "The agent dies. Its ghost memory is saved: last 20 lessons, last 10 best decisions, "
            "personality traits, and death timestamp. The governor spawns a successor in the same "
            "district. The new agent calls inherit_ghost() to load the ghost memory, giving it "
            "the dead agent's accumulated knowledge from generation N."
        ),
    },
    {
        "instruction": "How does VECTOR's governor route a task?",
        "input": "",
        "output": (
            "The governor first checks the skill matcher for a high-confidence skill match (>0.6). "
            "If found, the skill executes via the sandbox runner. Otherwise it looks up the task "
            "type in DISTRICT_TASK_MAP. If a district agent is found, it dispatches run(task). "
            "If no match, the LLM classify fallback infers the correct district."
        ),
    },
    {
        "instruction": "What is the difference between episodic and semantic memory in VECTOR?",
        "input": "",
        "output": (
            "Episodic memory stores time-stamped events (what happened, when, tags, reward) "
            "using SQLite FTS5 for full-text search. Semantic memory stores key-value facts "
            "that persist across sessions (agent HP snapshots, loop state). Both live in the "
            "same SQLite DB under separate tables."
        ),
    },
    {
        "instruction": "How does VECTOR's decision engine score action candidates?",
        "input": "",
        "output": (
            "Each candidate action is scored: goal_alignment(30%) + confidence(25%) + "
            "policy(20%) + urgency(15%) + timing(10%) - cost(5%). The policy score comes "
            "from historical outcome data via EMA smoothing. The highest-scoring candidate "
            "is selected and sent to the permission gateway."
        ),
    },
    {
        "instruction": "What is VECTOR's LLM Council and when does it activate?",
        "input": "",
        "output": (
            "The council is a deliberative group of 4 local LLMs (reasoning, r1, "
            "qwen3:30b-a3b, chairman) that vote on high-stakes decisions. It only activates "
            "when stakes='high' or 'critical'. Only agents with >700 HP can vote. All sessions "
            "are stored in reasoning_chains as future training data. Cost: zero — fully local."
        ),
    },
    {
        "instruction": "How does VECTOR store cross-agent shared knowledge?",
        "input": "",
        "output": (
            "Via SharedFacts — a singleton in-memory + SQLite store. Any agent calls "
            "self.know(key, value, confidence=0.7) to publish a fact. Other agents call "
            "self.recall_fact(key) to retrieve it. Facts decay in confidence over time "
            "and are superseded when higher-confidence updates arrive."
        ),
    },
    {
        "instruction": "What does the rules engine bypass do in VECTOR?",
        "input": "",
        "output": (
            "Before routing voice or text input through the full LLM decision pipeline, "
            "the rules engine checks for simple pattern matches (greetings, time queries, "
            "status queries). If matched, it returns a deterministic response immediately — "
            "no LLM call, no governor dispatch. This saves latency and model tokens."
        ),
    },
    # ── Security (21-28) ──────────────────────────────────────────────────
    {
        "instruction": "What is a MITRE ATT&CK technique?",
        "input": "",
        "output": (
            "A MITRE ATT&CK technique is a specific adversarial behavior (e.g., T1059 "
            "Command and Scripting Interpreter, T1110 Brute Force). Techniques are grouped "
            "under Tactics (TA0002 Execution, TA0006 Credential Access). They form a "
            "knowledge base used to map detections to real-world attack patterns."
        ),
    },
    {
        "instruction": "What is a circuit breaker in software resilience?",
        "input": "",
        "output": (
            "A circuit breaker monitors calls to a dependency. When failures exceed a "
            "threshold, it opens — all further calls fail fast. After a recovery window, "
            "it enters HALF_OPEN and tests with one call. If it succeeds, it closes. "
            "This prevents cascading failures under load."
        ),
    },
    {
        "instruction": "How would you detect brute force login attempts in logs?",
        "input": "",
        "output": (
            "Monitor authentication failure rate: if more than 5 failures in 60 seconds, "
            "flag as T1110 Brute Force. Pattern match on: 'auth fail', 'invalid password', "
            "'authentication error'. Trigger playbook: log evidence, capture process snapshot, "
            "notify operator, consider IP block."
        ),
    },
    {
        "instruction": "What is process injection in the context of MITRE ATT&CK?",
        "input": "",
        "output": (
            "Process injection (T1055) is a technique where adversaries insert malicious code "
            "into a legitimate process. Indicators include WriteProcessMemory, VirtualAllocEx, "
            "CreateRemoteThread API calls, ptrace on Linux, or LD_PRELOAD. Severity 9/10 — "
            "immediate alert and escalation required."
        ),
    },
    {
        "instruction": "How does the SIEM pipeline in VECTOR work?",
        "input": "",
        "output": (
            "Log events flow from LogAggregator (loguru sink to SQLite) to DetectionRules "
            "(evaluates threshold, pattern, rate, composite conditions against MITRE YAML "
            "rules). When a rule fires, it creates a RuleMatch. The SIEMPipeline finds the "
            "matching playbook ID from the rule response field and executes it via "
            "IncidentPlaybookRunner."
        ),
    },
    {
        "instruction": "What actions are available in VECTOR incident playbooks?",
        "input": "",
        "output": (
            "Available actions: block_ip, unblock_ip, capture_process_snapshot, kill_process, "
            "notify, log_evidence, isolate_process, collect_memory_dump, run_antivirus, "
            "escalate_to_human. Each step has a configurable timeout and rollback steps "
            "execute in reverse order if any step fails."
        ),
    },
    {
        "instruction": "What is defense evasion in the MITRE ATT&CK framework?",
        "input": "",
        "output": (
            "Defense Evasion (TA0005) groups techniques adversaries use to avoid detection. "
            "Common techniques: T1070 (clearing logs), T1036 (masquerading), T1027 "
            "(obfuscated files). Detection: monitor for wevtutil cl, Clear-EventLog, "
            "log file deletion. Severity 9/10."
        ),
    },
    {
        "instruction": "Explain the HP validator's role in VECTOR.",
        "input": "",
        "output": (
            "The HP validator prevents gaming of the agent HP system. It: (1) clamps "
            "individual deltas to ±200 max; (2) uses EMA smoothing (alpha=0.3); "
            "(3) cross-validates large deltas (>=50 HP); (4) detects seesaw attacks — "
            "alternating +/- to inflate total HP. Result: validated_delta replaces "
            "raw delta before any HP change."
        ),
    },
    # ── Memory / Research (29-35) ─────────────────────────────────────────
    {
        "instruction": "How does LightRAG differ from a simple vector database?",
        "input": "",
        "output": (
            "LightRAG combines dense vector retrieval with a knowledge graph. "
            "When querying, it retrieves semantically similar chunks AND traverses "
            "entity relationships in the graph to find connected facts. This gives "
            "better performance on multi-hop queries."
        ),
    },
    {
        "instruction": "What does VECTOR's research hub do each night?",
        "input": "",
        "output": (
            "The autoresearch runner runs nightly hypothesis generation: reads the owner's "
            "current goals, generates 3-5 research questions, queries DuckDuckGo + ArXiv + "
            "Reddit, filters by relevance score, stores results in episodic memory, and "
            "writes a synthesis note to the Obsidian vault."
        ),
    },
    {
        "instruction": "How does Obsidian sync work in VECTOR?",
        "input": "",
        "output": (
            "A watchdog monitors the Obsidian vault directory for .md file changes. "
            "On change, ConsolidationBot reads the file, extracts key concepts, and "
            "upserts them into LightRAG as semantic facts. Nightly consolidation merges "
            "duplicate facts and prunes low-confidence entries older than 90 days."
        ),
    },
    {
        "instruction": "What is the reasoning bank in VECTOR?",
        "input": "",
        "output": (
            "The reasoning bank stores every thought chain the decision engine produces. "
            "Chains with reward > 0.7 are flagged as training-worthy. The "
            "SelfImprovementCycle collects these and uses them as LoRA fine-tuning data — "
            "VECTOR literally trains on its own good decisions."
        ),
    },
    {
        "instruction": "How does VECTOR track what it does not know?",
        "input": "",
        "output": (
            "The epistemic tracker monitors claim confidence over time. Claims decay 20% "
            "per week. When confidence drops below 0.3, the topic is flagged as a knowledge "
            "gap. Staleness detection flags facts older than 14 days without reconfirmation. "
            "The research hub uses this gap list to prioritise nightly research."
        ),
    },
    {
        "instruction": "Describe VECTOR's memory schema.",
        "input": "",
        "output": (
            "Five SQLite tables (never renamed): episodic_memory (time-stamped events, "
            "FTS5, reward), semantic_memory (key-value facts, confidence, source), "
            "policy_memory (action to outcome EMA), reasoning_chains (thought chains, "
            "training-worthy flag), agent_history (HP snapshots per agent per day)."
        ),
    },
    {
        "instruction": "What is the synthesis bridge in VECTOR?",
        "input": "",
        "output": (
            "The synthesis bridge (core/brain/synthesis_bridge.py) runs every 30 minutes. "
            "It reads recent entries across all memory domains and looks for cross-domain "
            "patterns. These patterns are stored as high-confidence semantic facts and "
            "surfaced in the morning briefing."
        ),
    },
    # ── General AI / LLM (36-50) ─────────────────────────────────────────
    {
        "instruction": "What is LoRA fine-tuning?",
        "input": "",
        "output": (
            "LoRA (Low-Rank Adaptation) fine-tunes large models by adding small "
            "rank-decomposition weight matrices to attention layers. Only these adapter "
            "matrices are trained — typically less than 1% of model parameters. This allows "
            "fine-tuning a 14B model on a single GPU in hours."
        ),
    },
    {
        "instruction": "What is the difference between SFT and RLHF?",
        "input": "",
        "output": (
            "SFT (Supervised Fine-Tuning) trains on instruction/response pairs — the model "
            "imitates preferred outputs. RLHF adds a reward model trained on human preference "
            "comparisons, then uses PPO to optimise against it. RLHF better captures nuanced "
            "preferences but requires more infrastructure. VECTOR uses SFT via LoRA."
        ),
    },
    {
        "instruction": "Explain the Alpaca instruction-tuning template.",
        "input": "",
        "output": (
            "The Alpaca template structures training examples as:\n\n"
            "### Instruction:\n<task>\n\n"
            "### Input:\n<optional context>\n\n"
            "### Response:\n<ideal answer>\n\n"
            "This separates the task from optional context, making the model learn to "
            "follow structured prompts."
        ),
    },
    {
        "instruction": "What is a bulkhead pattern in software architecture?",
        "input": "",
        "output": (
            "A bulkhead isolates components so a failure in one does not cascade. "
            "In VECTOR, BulkheadExecutor uses semaphores: each district gets a "
            "max_concurrent limit and a queue. If both are full, calls are rejected with "
            "BulkheadRejectedError — the caller degrades gracefully."
        ),
    },
    {
        "instruction": "What is the purpose of a session hydration prompt?",
        "input": "",
        "output": (
            "A session hydration prompt is prepended to every LLM call to give the model "
            "context it cannot infer alone: current date/time, active goals, recent episodic "
            "events, agent HP state, pending tasks, owner profile. Without it, the LLM acts "
            "stateless. VECTOR's context_engine.session_hydration_prompt() builds this from "
            "14 domains."
        ),
    },
    {
        "instruction": "How does MoE (Mixture of Experts) routing work?",
        "input": "",
        "output": (
            "MoE has multiple expert sub-networks and a gating network. For each token, the "
            "gate selects top-k experts (typically 2). Only those experts activate — so a "
            "30B MoE model uses just 3B active parameters per forward pass. VECTOR's "
            "GNNRouter uses an 8-expert MoE as Layer 0."
        ),
    },
    {
        "instruction": "What is Flash Attention and why does it matter?",
        "input": "",
        "output": (
            "Flash Attention rewrites the attention computation to tile inputs into blocks "
            "that fit in GPU SRAM, avoiding materialising the full N x N attention matrix "
            "in HBM. This reduces memory from O(N^2) to O(N) and improves throughput by "
            "roughly 3x. Critical for long-context inference on the RTX 5070 Ti."
        ),
    },
    {
        "instruction": "Explain the difference between RAG and fine-tuning.",
        "input": "",
        "output": (
            "RAG injects retrieved documents into the prompt at inference time — no model "
            "weights change. Fine-tuning updates model weights on domain data. RAG is cheaper "
            "and updatable without retraining, better for factual recall. Fine-tuning changes "
            "reasoning patterns. VECTOR uses both: LightRAG for facts, LoRA for behaviour."
        ),
    },
    {
        "instruction": "What is the VECTOR Modelfile convention for naming models?",
        "input": "",
        "output": (
            "VECTOR custom models use hyphen-separated names: vector-ambient, vector-focus, "
            "vector-coder, vector-reasoning, vector-deep, vector-chairman. HP-based routing: "
            "ambient (<200 HP), reasoning (200-400), focus (400-600), orchestrator (600-800), "
            "cloud_coder (>800)."
        ),
    },
    {
        "instruction": "Why does VECTOR use Ollama as the primary inference backend?",
        "input": "",
        "output": (
            "Ollama is local (zero cloud cost, zero latency overhead, zero privacy risk), "
            "runs on the RTX 5070 Ti with CUDA, and manages model loading/unloading. "
            "VECTOR Rule 11: Ollama is tried first for every inference call. Cloud providers "
            "are fallback only — triggered when Ollama is unavailable or the task requires "
            "cloud-grade capabilities."
        ),
    },
    {
        "instruction": "What does VECTOR's autonomous loop do when an error occurs?",
        "input": "",
        "output": (
            "The loop catches every exception inside the while True block: logs with "
            "logger.error, then awaits asyncio.sleep(5) before retrying. It never propagates "
            "the exception — the loop must not die. The 5-second backoff prevents tight "
            "error loops that would spin the CPU."
        ),
    },
    {
        "instruction": "How does the event bus work in VECTOR?",
        "input": "",
        "output": (
            "core/event_bus/bus.py is the single async event bus — never raw asyncio.Queue. "
            "Agents subscribe_to(event_type). The bus dispatches events to all subscribers "
            "via handle_event(). Cross-district events go through the bus, ensuring decoupled "
            "communication without direct agent-to-agent imports."
        ),
    },
    {
        "instruction": "What is a ghost memory in VECTOR?",
        "input": "",
        "output": (
            "When an agent's HP reaches 0, die() is called. It saves: name, district, "
            "generation, final_hp, last 20 lessons, last 10 best_decisions, personality_traits, "
            "died_at. The successor calls inherit_ghost(ghost) to load this. Cross-generational "
            "learning: the new agent starts with institutional memory from its predecessor."
        ),
    },
    {
        "instruction": "What is VECTOR's approach to test coverage?",
        "input": "",
        "output": (
            "VECTOR currently enforces a smoke coverage floor for stable CI shards, not a "
            "production-grade whole-repo coverage target. Tests live in tests/ and focus on "
            "core invariants such as permission_gateway, routing, auth, memory persistence, "
            "and route wiring. External APIs and device-bound paths are mocked or owner-gated."
        ),
    },
    {
        "instruction": "How does VECTOR handle Windows vs Linux path differences?",
        "input": "",
        "output": (
            "All paths use pathlib.Path throughout — no hardcoded slashes. Windows-specific "
            "subprocess calls (netsh, tasklist) use creationflags=CREATE_NO_WINDOW. "
            "The autonomous loop wraps add_signal_handler() in try/except since Windows "
            "does not support SIGTERM."
        ),
    },
]


def _write_jsonl_atomic(path: Path, examples: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as output:
            tmp_name = output.name
            for example in examples:
                output.write(json.dumps(example, ensure_ascii=False) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)


def build() -> None:
    assert len(EXAMPLES) == 50, f"Expected 50 examples, got {len(EXAMPLES)}"

    seed_path = Path("data/training/seed.jsonl")
    _write_jsonl_atomic(seed_path, EXAMPLES)

    coding_path = Path("data/training/coding/seed.jsonl")
    _write_jsonl_atomic(coding_path, EXAMPLES)

    print(f"[seed] Written {len(EXAMPLES)} examples to {seed_path}")
    print(f"[seed] Written {len(EXAMPLES)} examples to {coding_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
    print("build_seed_dataset.py OK")
