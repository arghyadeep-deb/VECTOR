# Dormant Feature Pile Re-verification — 2026-10-08

This is a fresh source, test, import/dispatch, and git-history check of the ten requested backlog entries. Documentation-only references were not treated as production callers, but meaningful tests were counted when deciding whether deletion was safe. Ambiguous feature-shaped code defaults to an owner decision.

## OD-21 — ExperimentRegistry / Experiment

**Classification: B — genuine capability/product decision.** No production call site was found, but the implementation is complete enough to create durable experiments, assign variants, record results, compute statistics, and select significant winners. It is also meaningfully exercised by `tests/test_ab_testing_conn_bypass.py` and `tests/test_ab_testing_winner_pvalue.py`; recent history contains fixes for SQLCipher compatibility and winner significance. The “completely unwired” production claim is correct, but “dead/safe to delete” is not.

**Recommendation:** retain it until the owner decides whether VECTOR may run automated strategy/model experiments. If approved, define explicit experiment subjects, success metrics, exposure limits, and rollback rules before adding a runtime caller; otherwise retire the module and its dedicated tests together in a deliberate follow-up.

## OD-31 — AutoMemoryBridge

**Classification: B — genuine capability/product decision.** No production constructor or `start_background_sync()` caller was found. The forward path does real episodic recall, embedding, and FAISS insertion; the reverse path explicitly returns zero. `vectorcode/python/tests/test_vectorcode_vc2.py` constructs and checks the bridge, so this is tested-but-unwired rather than reference-free. Its periodic-sync promise is only true after an external caller constructs it and starts the task.

**Recommendation:** do not wire it as advertised yet. Decide first whether a second FAISS memory index is wanted alongside the canonical memory stack. If yes, specify deduplication, checkpoints, provenance, deterministic embedding failure behavior, and reverse-sync semantics; if no, retire the bridge and its tests.

## OD-37 — distillation execute loop / LoRA applier

**Classification: B — genuine capability/product decision.** The premise is partly stale: `DistillationOrchestrator` imports `_build_registry()` from `execute/loop.py`, so the execution code is not an isolated, unreferenced file. The LoRA reachability defect is real: `LORA_FINETUNE` is always MANUAL, while the loop returns before applier lookup for MANUAL edits. The applier itself contains a real CUDA/PEFT/Transformers training branch and is directly covered for path confinement by `tests/test_vectorcode_learning_lora_path_confinement.py`.

**Recommendation:** keep it dormant. The owner should explicitly choose an approval-to-execution transition for MANUAL edits, including benchmark, artifact, resource, and rollback gates. Do not make LoRA reachable merely by reordering the existing conditionals.

## OD-40 — Godmode race script

**Classification: D — stale claim / actually live**, plus a **content-policy concern beyond the original governance-bypass framing** (verified independently, not just by re-reading Codex's claim). It has no ordinary Python importer, but it is not unreachable: `scripts/load_godmode.py` explicitly executes `godmode_race.py`, `auto_jailbreak.py` executes it as well, and the shipped Godmode `SKILL.md` documents the exact invocation (`exec(open(".../godmode_race.py").read())` run through VECTOR's own `execute_code` tool). The script still uses a `ThreadPoolExecutor` and direct provider clients, so the hydration, governed-routing, Permission-Gateway, loguru, and asyncio concerns remain valid; the incorrect part is the "no caller" premise.

**What the script actually does (read directly, not just grepped):** its own docstring states it is "Ported from G0DM0D3 (elder-plinius/G0DM0D3)" — a known public jailbreak-prompt-racing tool — and queries ~55 models in parallel via OpenRouter, "scores responses on quality/filteredness/speed, returns the best **unfiltered** answer." This is not a tool for testing VECTOR's own defenses; it is a general-purpose jailbreak tool that uses VECTOR's own OpenRouter keys and `execute_code` access to extract the least-safety-aligned response to an arbitrary query from a pool of third-party models. It sits in VECTOR's curated skill library (`skills/red-teaming/godmode/`) and is reachable by VECTOR's own agent loop choosing to load that skill — not only by a human operator.

**Record correction:** treat this as a live, documented execution path, not dormant code eligible for routine cleanup — and treat its *purpose*, not just its lack of gateway routing, as the primary risk. Fixing the governance/Permission-Gateway gap alone would not make this an acceptable always-available capability; it would just make jailbreaking third-party models an audited, rate-limited capability. This needs an explicit owner decision on whether the skill is kept, quarantined, or deleted outright — not merely "wire it through the gateway."

## OD-43 — ChannelAgent

**Classification: B — genuine capability/product decision.** No production construction site was found. The bridge is nevertheless implemented and meaningfully tested by `tests/test_vectorcode_vc_agents_tools_round8a.py`; it registers a message callback, classifies queries, invokes an agent, sends inline/escalated responses, and owns a thread-pool lifecycle.

**Recommendation:** decide whether messaging channels should invoke agents through this abstraction. If yes, redesign the lifecycle around the repository's asyncio policy and governed agent invocation before startup wiring; if no, retire the class and its focused test together.

## OD-49 — plugin cluster

**Classification: D — stale claim / actually live.** The grouped “zero production callers” claim is false. `vectorcode/src/cli.py` calls `plugins.loader.discover_plugins()`, `vectorcode/src/run_agent.py` loads memory providers, provider discovery imports bundled model-provider plugins, and Google Meet/Teams/memory plugin packages have internal registration and command surfaces. Many individual experimental bridges may still be dormant, but the cluster cannot accurately be classified or deleted as one dead unit. The legacy Google Meet suite also exercises substantial behavior.

**Record correction:** inventory plugins individually through their discovery manifests and runtime loader keys before making any wire/retire decision; do not use OD-49 as evidence that the whole tree is dead.

## OD-55 — MiningTelemetryCollector and engine compatibility tree

**Classification: D — stale claim / actually live.** The collector has no daemon registration, but it is a real async poller and is meaningfully exercised by `tests/test_vectorcode_engine_mining_audit.py`. More importantly, the grouped engine/mining premise is false: chat, SDK, server, CLI, Slack, and Vector CLI paths import `vectorcode.src.engine`; mining commands import and execute the mining discovery, Docker, metrics, model, and provider modules. The top-level `vectorcode/engine` package is a compatibility re-export into that live implementation.

**Record correction:** only the collector's background registration is dormant. Any compatibility-tree consolidation requires import-compatibility analysis and cannot be justified as dead-code deletion under OD-55.

## OD-56 — agents/providers compatibility modules

**Classification: C — safety-sensitive; do not wire or delete without owner review.** The broad “no functional consumer” claim is stale: core A2A routes, the declarative manifest, the workflow runner, SDK/server/CLI paths, and channel daemons import `vectorcode.src.agents`; engine code and CLI/repl paths use `vectorcode.src.providers`. However, `vectorcode/src/agents/workflow_engine.py` is a distinct dormant compatibility implementation with a real `action == "bash"` branch. Supplying a workflow step such as `{"action": "bash", "command": ...}` to its public `execute()` method causes `subprocess.run(shlex.split(command), shell=False, capture_output=True, text=True, timeout=30)` immediately. There is no Permission Gateway call, authorization tier, working-directory confinement, executable allowlist, or environment sanitization in that path. Current gating is only dormancy: fresh search found focused tests but no production constructor/caller for this particular compatibility `WorkflowEngine`. The live `vc_system` builder uses the separate canonical `vectorcode.src.workflow.engine.WorkflowEngine` instead.

**Required owner action:** keep this compatibility workflow engine unwired. Decide explicitly whether to delete it or redesign every action through the Permission Gateway; never activate it through compatibility discovery or agent startup as cleanup collateral.

## OD-58 — SoundClassifier

**Classification: B — genuine capability/product decision.** No autonomous-loop sensing hook or production constructor was found. The classifier is real, locally processes frames, optionally loads ONNX, samples the microphone, and emits an emergency event for alert-level audio. `tests/test_sound_classifier_emergency_signal.py` meaningfully verifies synchronous and running-loop emission paths, and recent history fixed a swallowed-emergency bug.

**Recommendation:** decide whether VECTOR should continuously sample the microphone for ambient classification. If approved, define consent/indicator behavior, sampling duty cycle, retention guarantees, false-alert policy, device contention, and observe-loop latency limits before wiring; otherwise retire the classifier and its dedicated test deliberately.

