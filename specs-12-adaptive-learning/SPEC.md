# SPEC-12: Adaptive Learning — Self-Improvement via LoRA Fine-Tuning & RL

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's adaptive learning from 58/100 to 95/100 — automated LoRA fine-tuning of Ollama models per domain, continuous RL training of the decision engine, model distillation from cloud LLMs, and a weekly self-improvement cycle that measurably improves performance.

**Architecture:** Build an automated fine-tuning pipeline that collects high-quality training data from episodic memory, trains LoRA adapters for specific domains (coding, research, voice, personality), and deploys them to Ollama. Upgrade the A2C neural trainer with continuous online RL training. Build an evaluation harness that scores each adapter against benchmark prompts and rejects regressions. Implement knowledge distillation that compresses insights from large models (Claude, Gemini) into compact Ollama models. Orchestrate everything with a weekly self-improvement cycle.

**Tech Stack:** unsloth (fast LoRA training), peft, transformers, bitsandbytes, trl (PPO trainer), torch, datasets, wandb (optional experiment tracking), scipy (eval metrics)

**Score:** Current 58/100 → Target 95/100

---

## 1. Problem Statement

### 1.1 Current Limitations

Adaptive learning scores 58/100 across seven dimensions:

| Dimension | Score | Issue |
|-----------|-------|--------|
| Policy Memory (RL) | 70/100 | RL table with `get_score(before)` / `update_from_outcome(after)` works. 5-factor reward: user_feedback 40%, goal_progress 25%, not_overridden 15%, not_corrected 15%, completed 5%. Solid baseline. |
| A2C Neural Trainer | 65/100 | 64-dim state, 20 actions, trains on policy memory data. Works but no continuous training loop — must be manually triggered. |
| HP Evolution | 60/100 | Agent death → ghost memory → new generation. Good for agentic evolution but doesn't improve model capabilities. |
| Epistemic Tracking | 55/100 | Tracks what VECTOR knows and doesn't know. No connection to training pipeline — just logging. |
| Habit Finder | 50/100 | Detects behavioral patterns. No integration with model training to reinforce good habits. |
| Fine-Tuning | 0/100 | No fine-tuning pipeline exists. VECTOR uses base Ollama models as-is, with only prompt/context steering. |
| Model Distillation | 0/100 | No mechanism to transfer capabilities from large cloud models to local Ollama models. Cloud API costs are a sunk expense with no lasting benefit. |

### 1.2 Root Causes

1. **No training pipeline:** VECTOR has never fine-tuned any model. All behavior is guided by prompts and system messages — fragile and context-window-limited.
2. **No eval harness:** No standardized benchmarks to measure whether changes improve or degrade performance. Cannot detect regressions.
3. **No data curation:** Episodic memory contains millions of tokens of interaction data. No process to extract high-quality training pairs.
4. **No model routing upgrades:** `core/inference/llm_providers.py` routes based on cost tier (free/eco/auto/premium). No task-type routing to specialized adapters.
5. **No distillation:** Knowledge from expensive cloud calls evaporates — no compressed version persists locally.
6. **Manual RL training:** A2C trainer works but requires `python -m core.loop.decision_engine --train` — not integrated into any automatic cycle.

### 1.3 Impact

- VECTOR cannot learn from corrections — the same mistake recurs across sessions
- Cloud API costs grow linearly with usage (Claude/Gemini calls) with no compounding benefit
- Prompt engineering has hit diminishing returns — behavior does not qualitatively improve
- Each Ollama model is a generalist — no specialized expertise for coding, research, or voice
- RL policy only improves through manual training runs, not continuous adaptation

---

## 2. Current Architecture

### 2.1 Policy Memory

```
core/memory/policy.py — RL Table
  get_score(before_state) → action
  update_from_outcome(before_state, action, after_state)

  Reward factors:
    user_feedback: 40% (direct thumbs up/down, corrections)
    goal_progress: 25% (did the autonomous loop advance its goals)
    not_overridden: 15% (user did not manually override the decision)
    not_corrected: 15% (user did not correct the output)
    completed: 5% (task reached completion state)

  Storage: SQLite table with 64-dim state vectors and Q-values
```

### 2.2 A2C Neural Trainer

```
core/loop/decision_engine.py
  State: 64-dim (system resources, task queue, user state, time, context)
  Actions: 20 discrete (start_research, run_voice, check_memory, etc.)
  Architecture:
    Actor: 64 → 128 → 64 → 20 (action probabilities)
    Critic: 64 → 128 → 64 → 1 (state value)
  Training: Advantage Actor-Critic with entropy regularization
  
  Current usage:
    - __main__ block: CLI for manual training
    - dump_states(): export collected states for analysis
    - No automatic training schedule
```

### 2.3 Episodic Memory as Data Source

```
core/memory/episodic.py
  SQLite FTS5 + AES-256
  Stores: every user interaction, every VECTOR action, every decision
  Fields: timestamp, content, embedding, metadata, reward_signals
  
  Potential but unused:
    - User corrections are stored but not extracted for training
    - High-reward decisions are not labeled as training exemplars
    - Conversations are not formatted into training pairs
```

### 2.4 Inference Routing

```
core/inference/llm_providers.py
  Tiers: free → eco → auto → premium
  Routing: based on task complexity and cost budget
  
  No specialization routing:
    - Coding tasks use the same model as chit-chat
    - Voice responses use the same model as deep research
    - No task-specific adapters or models
```

---

## 3. Target Architecture

### 3.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    SelfImprovementCycle (weekly)                           │
│                                                                          │
│  ┌──────────────┐     ┌─────────────────┐     ┌────────────────────┐    │
│  │ DataCollector │────▶│  LoRATrainer    │────▶│  EvalHarness       │    │
│  │               │     │                 │     │                    │    │
│  │ episodic      │     │ unsloth + peft  │     │ benchmark prompts  │    │
│  │ memory scan   │     │ per-domain      │     │ score vs baseline  │    │
│  │ reward filter │     │ LoRA adapters   │     │ regression gate    │    │
│  └──────────────┘     └─────────────────┘     └────────┬───────────┘    │
│                                                         │                │
│  ┌──────────────────────────────────────────────────────▼────────────┐   │
│  │                    ModelRouter (upgraded)                          │   │
│  │  task_type → domain → adapter → Ollama model                      │   │
│  │  /api/chat → detect task → swap adapter dynamically               │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────┐     ┌──────────────────────┐                      │
│  │ KnowledgeDistiller│────▶│  Synthetic Data Gen  │                      │
│  │                   │     │                      │                      │
│  │ Claude/Gemini →   │     │ cloud model output   │                      │
│  │ compact Ollama    │     │ → training pairs      │                      │
│  └──────────────────┘     └──────────────────────┘                      │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  ContinuousRLTrainer (upgraded A2C)                              │    │
│  │  online training: every 1000 decisions → train step             │    │
│  │  auto-saves best checkpoint                                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Self-Improvement Cycle Flow

```
Week N:
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Sunday 03:00 — SelfImprovementCycle.run()                          │
  │                                                                     │
  │  1. DataCollector.collect()                                         │
  │     → Scan last 7 days of episodic memory                           │
  │     → Filter: decisions with reward > 0.7 → positive examples      │
  │     → Filter: decisions with reward < -0.3 → negative examples     │
  │     → Filter: user corrections → correction pairs                  │
  │     → Also extract: conversation logs, code sessions, voice logs   │
  │     → Output: 4 datasets (coding, research, voice, personality)    │
  │                                                                     │
  │  2. LoRATrainer.train_all()                                         │
  │     → For each domain with sufficient data (>100 examples):        │
  │       › Prepare dataset (chat template → tokenized pairs)          │
  │       › Train LoRA adapter (rank=16, alpha=32, target=q_proj+v_proj)│
  │       › Save adapter to models/adapters/{domain}/                  │
  │                                                                     │
  │  3. EvalHarness.evaluate_all()                                      │
  │     → For each domain, run benchmark prompts through:               │
  │       › Base model (no adapter) → baseline scores                   │
  │       › New adapter → candidate scores                              │
  │     → If improved AND no regression >2%: promote adapter            │
  │     → If regressed: keep previous adapter, log regression           │
  │                                                                     │
  │  4. ModelRouter.update_routing()                                    │
  │     → Update routing table to use promoted adapters                 │
  │                                                                     │
  │  5. KnowledgeDistiller.run()                                        │
  │     → Compress insights from cloud model calls into synthetic       │
  │       training data for local models                                │
  │                                                                     │
  │  6. ContinuousRLTrainer.train_step()                                │
  │     → Train A2C on last 1000 decisions                              │
  │     → Save if performance improved                                  │
  │                                                                     │
  │  7. Log improvements → episodic memory                              │
  └─────────────────────────────────────────────────────────────────────┘
```

### 3.3 LoRA Adapter Strategy per Domain

```
Domain: CODING
  Base model: vector-coder (Qwen2.5-Coder-7B or similar)
  Training data: code generation, bug fixes, code review, refactoring
  Adapter: models/adapters/coding/lora.safetensors
  Target modules: q_proj, v_proj, k_proj, o_proj
  Rank: 16 (balance of quality vs VRAM)
  Eval: HumanEval pass@1, code review quality, bug fix accuracy

Domain: RESEARCH
  Base model: vector-reasoning (Qwen2.5-7B-Instruct or similar)
  Training data: web searches, paper summaries, analysis, insight generation
  Adapter: models/adapters/research/lora.safetensors
  Target modules: q_proj, v_proj
  Rank: 8 (less data expected)
  Eval: fact extraction accuracy, summary quality, analysis depth

Domain: VOICE
  Base model: vector-focus (Llama-3.1-8B or similar)
  Training data: conversation turns, wake word responses, chit-chat
  Adapter: models/adapters/voice/lora.safetensors
  Target modules: q_proj, v_proj
  Rank: 8
  Eval: response relevance, latency to first token, personality consistency

Domain: PERSONALITY
  Base model: vector-chairman (Mixtral-8x7B or similar)
  Training data: preferred response style, reworded responses, tone corrections
  Adapter: models/adapters/personality/lora.safetensors
  Target modules: q_proj, v_proj, o_proj
  Rank: 16
  Eval: blind A/B test against previous personality version
```

---

## 4. Component Breakdown

### 4.1 LoRATrainer

**File:** `core/training/lora_trainer.py`

**Purpose:** Automated LoRA fine-tuning for Ollama models. Takes curated datasets → trains adapters → deploys to Ollama.

**Key Methods:**

```python
class LoRATrainer:
    def __init__(self):
        self.base_model_dir = str(config.training.models_dir)  # ./models/
        self.adapter_dir = str(config.training.adapters_dir)    # ./models/adapters/
        self.unsloth_available = self._check_unsloth()

    async def train_adapter(self, domain: str, dataset: Dataset, config: AdapterConfig) -> AdapterResult:
        """Full training pipeline for one domain adapter."""

    def _prepare_dataset(self, dataset: Dataset, template: str) -> Dataset:
        """Convert raw interaction data to chat-template formatted pairs.
           Supports: alpaca, chatml, vicuna, llama3 templates."""

    def _load_base_model(self, model_name: str, quant: str = "4bit"):
        """Load model with unsloth for fast LoRA training.
           Uses 4-bit quantization to fit 7B models in ~6GB VRAM."""

    def _apply_lora(self, model, peft_config: LoraConfig):
        """Apply LoRA PEFT configuration.
           Default: r=16, alpha=32, dropout=0.1, target_modules depends on domain."""

    def _train(self, model, tokenizer, dataset, training_args):
        """Run training with SFTTrainer or DPOTrainer.
           Saves best checkpoint based on eval loss."""

    def _export_adapter(self, adapter_path: str) -> Path:
        """Export LoRA weights to Ollama-compatible format.
           Creates: adapter_model.safetensors, adapter_config.json, README.md"""

    async def deploy_to_ollama(self, domain: str, adapter_path: Path) -> bool:
        """Create Ollama Modelfile pointing base model + adapter.
           docker cp or direct file reference depending on Ollama setup.
           ollama create vector-coder-lora -f Modelfile"""

    def _check_unsloth(self) -> bool:
        """Detect if unsloth is installed. Fall back to standard peft if not."""

    def estimate_vram(self, model_name: str, rank: int) -> int:
        """Estimate VRAM needed for training. Used to prevent OOM."""

@dataclass
class AdapterConfig:
    domain: str
    base_model: str
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.1
    target_modules: list[str] | None = None  # None = auto per domain
    learning_rate: float = 2e-4
    batch_size: int = 4
    gradient_accumulation: int = 4
    max_steps: int = 500
    warmup_steps: int = 50
    save_steps: int = 100
    eval_steps: int = 100
    max_seq_length: int = 2048
    use_unsloth: bool = True

@dataclass
class AdapterResult:
    domain: str
    status: str  # "success" | "skipped" | "failed"
    adapter_path: Path | None
    train_loss: float
    eval_loss: float
    train_duration_s: float
    vram_peak_mb: int
    error: str | None
```

**Training Template:**
```python
# unsloth optimized training for RTX 5070 Ti 12GB:
from unsloth import FastLanguageModel, is_bfloat16_supported

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=base_model,
    max_seq_length=2048,
    dtype=None,  # Auto-detect
    load_in_4bit=True,  # 4-bit QLoRA — fits 7B in ~6GB
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha=32,
    lora_dropout=0.1,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=2048,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_steps=50,
        max_steps=500,
        learning_rate=2e-4,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=10,
        save_steps=100,
        output_dir=str(adapter_path),
        optim="adamw_8bit",
        seed=42,
    ),
)
```

### 4.2 DataCollector

**File:** `core/training/data_collector.py`

**Purpose:** Curate high-quality training data from episodic memory and user interactions.

**Key Methods:**

```python
class DataCollector:
    def __init__(self):
        self.memory = EpisodicMemory()
        self.min_reward_threshold = 0.7
        self.max_reward_threshold = -0.3
        self.min_examples_per_domain = 100

    async def collect(self, days: int = 7) -> dict[str, Dataset]:
        """Collect training data from the last N days.
           Returns dict: domain → list of training pairs."""

    async def _scan_memory(self, since: datetime) -> list[dict]:
        """Query episodic memory for entries with reward signals."""

    def _classify_domain(self, entry: dict) -> str:
        """Classify entry into domain: coding, research, voice, personality.
           Based on entry metadata, intent classification, or LLM fallback."""

    def _extract_positive_pairs(self, entries: list[dict]) -> list[dict]:
        """From high-reward decisions: extract (user_input, vector_response) pairs.
           The response was well-received → use as training positive example."""

    def _extract_correction_pairs(self, entries: list[dict]) -> list[dict]:
        """From user corrections: extract (vector_response, user_correction) pairs.
           The correction shows the desired behavior → use as training target."""

    def _extract_conversation_logs(self, entries: list[dict]) -> list[dict]:
        """From raw conversations: extract multi-turn exchanges.
           Filter for coherence, relevance, and completeness."""

    def _format_for_training(self, pairs: list[dict], template: str) -> Dataset:
        """Convert raw pairs to chat-template format for the target model."""

    def _deduplicate(self, pairs: list[dict]) -> list[dict]:
        """Remove near-duplicate entries using embedding similarity.
           Threshold: cosine similarity > 0.95 → deduplicate."""

    def get_domain_stats(self) -> dict[str, int]:
        """Return count of available training examples per domain."""
```

### 4.3 EvalHarness

**File:** `core/training/eval_harness.py`

**Purpose:** Automated evaluation suite that scores adapter quality and rejects regressions.

**Key Methods:**

```python
class EvalHarness:
    def __init__(self):
        self.benchmarks: dict[str, Benchmark] = {
            "coding": CodingBenchmark(),
            "research": ResearchBenchmark(),
            "voice": VoiceBenchmark(),
            "personality": PersonalityBenchmark(),
        }
        self.results_dir = Path(config.training.eval_results_dir)

    async def evaluate(self, domain: str, model_id: str, adapter_path: Path | None = None) -> EvalResult:
        """Evaluate a model/adapter combination against the domain benchmark."""

    async def evaluate_all(self, adapters: dict[str, Path]) -> dict[str, EvalResult]:
        """Evaluate all domain adapters."""

    async def compare(self, domain: str, baseline: str, candidate: str) -> ComparisonResult:
        """Run baseline and candidate through same benchmark. Produce diff."""

    def should_promote(self, result: EvalResult, baseline: EvalResult) -> tuple[bool, str]:
        """Decision: promote adapter if improved AND no regression >2%."""

@dataclass
class EvalResult:
    domain: str
    model_id: str
    adapter_path: Path | None
    scores: dict[str, float]     # metric_name → score
    total_score: float
    samples: int
    duration_s: float
    errors: list[str]

@dataclass
class ComparisonResult:
    domain: str
    baseline: EvalResult
    candidate: EvalResult
    deltas: dict[str, float]     # metric_name → delta
    promoted: bool
    reason: str
```

**Domain Benchmarks:**

```python
class CodingBenchmark(Benchmark):
    """Benchmark prompts for coding domain."""
    def __init__(self):
        self.prompts = [
            # 20 prompts covering: function generation, bug fix, code review,
            # refactoring, test generation, API usage, algorithm implementation,
            # data structure usage, error handling, documentation
        ]
    
    async def score(self, model: Callable) -> dict[str, float]:
        """Score: pass@1 (functional correctness), style_score (linting),
           completeness_score (all requirements met), comment_quality."""

class ResearchBenchmark(Benchmark):
    """Benchmark prompts for research domain."""
    def __init__(self):
        self.prompts = [
            # 15 prompts covering: web search summarization, paper analysis,
            # fact extraction, source comparison, insight generation,
            # knowledge gap identification, methodology analysis
        ]
    
    async def score(self, model: Callable) -> dict[str, float]:
        """Score: fact_accuracy (LLM judge), completeness, citation_quality,
           analysis_depth (LLM judge)."""

class VoiceBenchmark(Benchmark):
    """Benchmark prompts for voice domain."""
    def __init__(self):
        self.prompts = [
            # 15 prompts covering: short responses, multi-turn,
            # follow-up questions, clarification requests,
            # interruption handling, personality consistency
        ]

class PersonalityBenchmark(Benchmark):
    """Benchmark for personality consistency."""
    def __init__(self):
        self.prompts = [
            # 10 personality probes: tone, formality, helpfulness,
            # refusal behavior, creative responses, empathy
        ]
    
    async def score(self, model: Callable) -> dict[str, float]:
        """Score: consistency_score (persona adherence), preference_match
           (matches stored user preferences), appropriateness."""
```

### 4.4 ModelRouter Upgrade

**File:** `core/inference/model_router.py` (new — replaces parts of `llm_providers.py`)

**Purpose:** Route requests to the optimal model/adapter based on task type, with dynamic adapter swapping.

**Key Methods:**

```python
class ModelRouter:
    def __init__(self):
        self.tiers: dict[str, str] = {
            "coding": "vector-coder-lora",       # base + LoRA adapter
            "research": "vector-reasoning-lora",
            "voice": "vector-focus-lora",
            "personality": "vector-chairman-lora",
            "default": "vector-focus",            # fallback
        }
        self.task_classifier = TaskClassifier()   # lightweight model for task detection
        self.adapter_registry: dict[str, AdapterInfo] = {}

    async def route(self, task: Task) -> ModelRoute:
        """Determine optimal model and adapter for a task."""

    async def _classify_task(self, task: Task) -> str:
        """Classify task into domain using lightweight classifier.
           Fallback: keyword matching, then LLM classification."""

    async def swap_adapter(self, domain: str, new_adapter: Path) -> bool:
        """Hot-swap the LoRA adapter for a domain.
           Uses Ollama API to reload model with new adapter."""

    async def detect_change(self, old_adapter: str, new_adapter: str) -> bool:
        """Detect if adapter has changed since last load."""

    def get_available_adapters(self) -> dict[str, list[str]]:
        """List all available adapters per domain."""

@dataclass
class ModelRoute:
    model_name: str            # Ollama model name
    adapter: str | None        # adapter name (None = no adapter)
    provider: str              # "ollama" | "cloud" 
    priority: int              # for fallback ordering
    estimated_cost: float      # estimated cost per token

class TaskClassifier:
    """Lightning-fast task classification using embedding similarity or keyword matching."""
    
    async def classify(self, task: Task) -> str:
        """Classify using: 1. Task metadata (if explicit). 2. Embedding similarity
           to domain exemplars. 3. Keyword matching. 4. LLM fallback (slow path)."""
```

**Task Detection Strategy:**
```
1. Fast path (~1ms): Task metadata
   - If task has explicit domain tag from source → use it directly
   - Coding assistant calls → "coding"
   - Voice pipeline calls → "voice"
   - Research engine calls → "research"

2. Medium path (~10ms): Embedding similarity
   - Pre-compute domain exemplar embeddings
   - Embed task description → cosine similarity to each domain
   - Threshold: >0.7 similarity → classify

3. Slow path (~100ms): LLM classification
   - Only if fast/medium paths disagree or confidence < 0.6
   - Tiny model (vector-focus) classifies the task
```

### 4.5 SelfImprovementCycle

**File:** `core/training/self_improvement_cycle.py`

**Purpose:** Weekly orchestration of data collection, training, evaluation, and deployment.

**Key Methods:**

```python
class SelfImprovementCycle:
    def __init__(self):
        self.data_collector = DataCollector()
        self.lora_trainer = LoRATrainer()
        self.eval_harness = EvalHarness()
        self.model_router = ModelRouter()
        self.knowledge_distiller = KnowledgeDistiller()
        self.rl_trainer = ContinuousRLTrainer()

    async def run(self):
        """Full weekly cycle. Called by autonomous loop."""
        logger.info("Starting weekly self-improvement cycle...")
        
        # Phase 1: Collect data
        datasets = await self.data_collector.collect(days=7)
        logger.info(f"Collected datasets: { {k: len(v) for k, v in datasets.items()} }")
        
        # Phase 2: Train adapters (one per domain with enough data)
        adapter_results = {}
        for domain, dataset in datasets.items():
            if len(dataset) < self.data_collector.min_examples_per_domain:
                logger.info(f"Skipping {domain}: only {len(dataset)} examples (need {self.data_collector.min_examples_per_domain})")
                continue
            result = await self.lora_trainer.train_adapter(domain, dataset, AdapterConfig(domain=domain))
            adapter_results[domain] = result
            logger.info(f"Adapter {domain}: {result.status} (loss={result.train_loss:.4f})")
        
        # Phase 3: Evaluate
        for domain, result in adapter_results.items():
            if result.status != "success":
                continue
            baseline = await self.eval_harness.evaluate(domain, config.training.base_model_for(domain))
            candidate = await self.eval_harness.evaluate(domain, config.training.base_model_for(domain), result.adapter_path)
            comparison = await self.eval_harness.compare(domain, baseline, candidate)
            
            if comparison.promoted:
                await self.model_router.swap_adapter(domain, result.adapter_path)
                logger.info(f"Promoted {domain} adapter: {comparison.reason}")
            else:
                logger.info(f"Rejected {domain} adapter: {comparison.reason}")
        
        # Phase 4: Knowledge distillation
        distillation_result = await self.knowledge_distiller.run()
        logger.info(f"Distillation: {distillation_result.pairs_generated} pairs, {distillation_result.tokens_saved} tokens")
        
        # Phase 5: Continuous RL training
        rl_result = await self.rl_trainer.train_step()
        logger.info(f"RL training: {rl_result.status}, policy_loss={rl_result.policy_loss:.4f}")
        
        # Phase 6: Log summary
        await self._log_cycle_summary(adapter_results, distillation_result, rl_result)

    async def _log_cycle_summary(self, adapter_results, distillation_result, rl_result):
        """Store cycle results in episodic memory for trend tracking."""

    def get_cycle_history(self) -> list[dict]:
        """Return history of all completed cycles for dashboard."""
```

### 4.6 KnowledgeDistiller

**File:** `core/training/knowledge_distiller.py`

**Purpose:** Compress insights from large cloud models into compact Ollama models via synthetic data generation.

**Key Methods:**

```python
class KnowledgeDistiller:
    def __init__(self):
        self.cloud_providers = ["claude", "gemini", "gpt4"]  # configured in config
        self.local_model = config.training.distillation_target_model

    async def run(self) -> DistillationResult:
        """Full distillation cycle."""

    async def _generate_synthetic_prompts(self, count: int = 100) -> list[str]:
        """Generate diverse prompts covering VECTOR's domain areas.
           Based on: topics from episodic memory, knowledge gaps from epistemic tracker,
           common user requests, edge cases from habit finder."""

    async def _query_cloud_models(self, prompts: list[str]) -> list[dict]:
        """Query all configured cloud models. Get diverse responses."""

    async def _format_training_pairs(self, responses: list[dict]) -> Dataset:
        """Format cloud responses into (prompt, response) training pairs.
           Filter: only responses where models agreed on quality aspects."""

    async def _train_local_model(self, dataset: Dataset):
        """Fine-tune local model on distilled data.
           Smaller effort — rank 8, 200 steps max."""

    def _estimate_tokens_saved(self, pairs: int, avg_tokens: int) -> int:
        """Estimate how many tokens of cloud API calls this distillation saves."""

@dataclass
class DistillationResult:
    pairs_generated: int
    tokens_saved: int           # estimated
    models_used: list[str]
    training_status: str
    adapter_path: Path | None
```

### 4.7 ContinuousRLTrainer

**File:** `core/training/continuous_rl_trainer.py`

**Purpose:** Extend the A2C trainer with online continuous training.

**Key Methods:**

```python
class ContinuousRLTrainer:
    def __init__(self):
        self.decision_engine = DecisionEngine()  # from core/loop/decision_engine.py
        self.min_decisions_per_step = 1000
        self.best_policy_path = Path(config.training.rl_policy_checkpoint)
        self.auto_save = True

    async def train_step(self, force: bool = False) -> RLResult:
        """Train one step of A2C if enough new decisions collected."""

    async def collect_recent_decisions(self, min_count: int) -> list[Decision]:
        """Get recent decisions from decision_engine with reward signals."""

    async def train_epoch(self, decisions: list[Decision]) -> dict:
        """Run one A2C training epoch on collected decisions."""

    async def save_checkpoint(self, metrics: dict):
        """Save best policy based on evaluation reward."""

    async def evaluate_policy(self) -> dict:
        """Run policy through eval suite: simulate 100 decisions, measure total reward."""

    def should_checkpoint(self, current_reward: float, best_reward: float) -> bool:
        """Checkpoint if current > best by 5% threshold."""

@dataclass
class RLResult:
    status: str
    decisions_trained: int
    policy_loss: float
    value_loss: float
    entropy: float
    avg_reward_before: float
    avg_reward_after: float
    checkpoint_saved: bool
```

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: LoRATrainer + DataCollector + KnowledgeDistiller

**Responsibility:** Build the fine-tuning pipeline, data curation, and distillation infrastructure.

**Tasks:**
1. Create `core/training/lora_trainer.py` with unsloth/peft integration
2. Create `core/training/training_config.py` — AdapterConfig, TrainingArgs Pydantic models
3. Create adapter storage structure: `models/adapters/{domain}/`
4. Create `core/training/data_collector.py` — episodic memory scanner + pair extractor
5. Create chat template formatters for popular model formats
6. Create `core/training/knowledge_distiller.py` — synthetic data generation from cloud models
7. Create Ollama deployment: Modelfile generation, `ollama create` integration
8. Test: `tests/training/test_lora_trainer.py`, `tests/training/test_data_collector.py`, `tests/training/test_knowledge_distiller.py`

### 5.2 Agent B: EvalHarness + ModelRouter + SelfImprovementCycle + ContinuousRLTrainer

**Responsibility:** Build evaluation, routing, cycle orchestration, and RL continuous training.

**Tasks:**
1. Create `core/training/eval_harness.py` with benchmark framework
2. Create domain benchmarks: CodingBenchmark, ResearchBenchmark, VoiceBenchmark, PersonalityBenchmark
3. Create baseline scoring and comparison logic
4. Create `core/inference/model_router.py` with TaskClassifier and adapter registry
5. Create hot-swap adapter mechanism via Ollama API
6. Create `core/training/self_improvement_cycle.py` orchestrating the weekly cycle
7. Create `core/training/continuous_rl_trainer.py` extending A2C trainer
8. Integrate cycle with autonomous loop (weekly schedule, Sunday 03:00)
9. Test: `tests/training/test_eval_harness.py`, `tests/training/test_model_router.py`, `tests/training/test_self_improvement_cycle.py`, `tests/training/test_continuous_rl_trainer.py`

---

## 6. Implementation Steps

### 6.1 Phase 1: Data Collection + LoRA Training (Agent A)

**Step 1.1: Training infrastructure**
- [ ] Create `core/training/` package with `__init__.py`
- [ ] Create `core/training/training_config.py` with all config dataclasses
- [ ] Create `models/adapters/` directory structure
- [ ] Verify unsloth installation: `python -c "from unsloth import FastLanguageModel"`

**Step 1.2: Data collector**
- [ ] Create `core/training/data_collector.py`
- [ ] Implement episodic memory scanner (query by date range, reward signals)
- [ ] Implement domain classifier (metadata → keyword → embedding → LLM)
- [ ] Implement positive pair extraction (high-reward decisions)
- [ ] Implement correction pair extraction (user corrections → training targets)
- [ ] Implement conversation log extraction
- [ ] Implement deduplication (embedding similarity)
- [ ] Implement chat template formatting for each target model type

**Step 1.3: LoRA trainer**
- [ ] Create `core/training/lora_trainer.py`
- [ ] Implement model loading with unsloth (4-bit QLoRA)
- [ ] Implement LoRA PEFT configuration per domain
- [ ] Implement training loop with SFTTrainer
- [ ] Implement checkpoint saving and adapter export
- [ ] Implement Ollama deployment (Modelfile generation, `ollama create`)
- [ ] Implement VRAM estimation to prevent OOM
- [ ] Test with a small dataset (50 examples) on coding domain

**Step 1.4: Test**
- [ ] `tests/training/test_data_collector.py` — scan memory, extract pairs, classify domains
- [ ] `tests/training/test_lora_trainer.py` — train small adapter, verify export, verify deployment

### 6.2 Phase 2: Eval Harness + Model Router (Agent B)

**Step 2.1: Eval harness**
- [ ] Create `core/training/eval_harness.py`
- [ ] Create base Benchmark class with scoring interface
- [ ] Create `core/training/benchmarks/coding_benchmark.py` — 20 coding prompts
- [ ] Create `core/training/benchmarks/research_benchmark.py` — 15 research prompts
- [ ] Create `core/training/benchmarks/voice_benchmark.py` — 15 voice prompts
- [ ] Create `core/training/benchmarks/personality_benchmark.py` — 10 personality probes
- [ ] Implement scoring: LLM judge, functional correctness, metric-based scoring
- [ ] Implement comparison logic (baseline vs candidate, regression detection)

**Step 2.2: Model router**
- [ ] Create `core/inference/model_router.py`
- [ ] Create TaskClassifier with multi-stage classification
- [ ] Create adapter registry (available adapters → models)
- [ ] Implement route determination (task → model + adapter)
- [ ] Implement hot-swap adapter mechanism (Ollama API calls)
- [ ] Integrate with existing `llm_providers.py` routing

**Step 2.3: Test**
- [ ] `tests/training/test_eval_harness.py` — run benchmark, verify scores, detect regression
- [ ] `tests/training/test_model_router.py` — classify tasks, route correctly, hot-swap

### 6.3 Phase 3: Self-Improvement Cycle + Continuous RL (Agent B)

**Step 3.1: Continuous RL trainer**
- [ ] Create `core/training/continuous_rl_trainer.py`
- [ ] Integrate with existing DecisionEngine from `core/loop/decision_engine.py`
- [ ] Implement recent decision collection (last 1000 from episodic memory)
- [ ] Implement A2C training step on collected decisions
- [ ] Implement policy evaluation (simulated decisions)
- [ ] Implement auto-save best checkpoint
- [ ] Test: collect decisions → train → evaluate → verify improvement

**Step 3.2: Self-improvement cycle**
- [ ] Create `core/training/self_improvement_cycle.py`
- [ ] Orchestrate: collect → train → eval → deploy → distill → rl_train
- [ ] Implement cycle logging to episodic memory
- [ ] Implement cycle history tracking
- [ ] Implement error recovery (if one phase fails, log and continue)

**Step 3.3: Autonomous loop integration**
- [ ] Add weekly schedule to `AutonomousLoop` (Sunday 03:00)
- [ ] Add config: `SelfImprovementConfig` (enabled, schedule_interval, min_data_threshold)
- [ ] Add cycle results to autonomous loop log

**Step 3.4: Knowledge distillation**
- [ ] Create `core/training/knowledge_distiller.py`
- [ ] Implement synthetic prompt generation (from memory topics, knowledge gaps)
- [ ] Implement cloud model query (Claude, Gemini, GPT-4)
- [ ] Implement response filtering and formatting
- [ ] Implement local model training on distilled data
- [ ] Estimate token savings for dashboard display

**Step 3.5: E2E test**
- [ ] Full cycle with synthetic data: collect → train → eval → compare → promote
- [ ] Verify: adapter loaded, routing works, no regression detected
- [ ] Measure: cycle time, VRAM usage, training loss curves

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `core/training/__init__.py` | ~30 | Training package facade |
| `core/training/training_config.py` | ~100 | AdapterConfig, TrainingArgs, EvalConfig dataclasses |
| `core/training/data_collector.py` | ~300 | Episodic memory scanner + training pair extraction |
| `core/training/lora_trainer.py` | ~350 | Unsloth/peft LoRA training + Ollama deployment |
| `core/training/eval_harness.py` | ~200 | Automated evaluation suite framework |
| `core/training/benchmarks/__init__.py` | ~20 | Benchmarks package |
| `core/training/benchmarks/coding_benchmark.py` | ~150 | 20 coding evaluation prompts + scoring |
| `core/training/benchmarks/research_benchmark.py` | ~120 | 15 research evaluation prompts + scoring |
| `core/training/benchmarks/voice_benchmark.py` | ~100 | 15 voice evaluation prompts + scoring |
| `core/training/benchmarks/personality_benchmark.py` | ~80 | 10 personality probes + scoring |
| `core/training/self_improvement_cycle.py` | ~250 | Weekly cycle orchestrator |
| `core/training/continuous_rl_trainer.py` | ~200 | A2C online training extension |
| `core/training/knowledge_distiller.py` | ~250 | Cloud→local knowledge compression |
| `core/inference/model_router.py` | ~300 | Task-based model+adapter routing |
| `tests/training/test_data_collector.py` | ~120 | Data collection tests |
| `tests/training/test_lora_trainer.py` | ~100 | LoRA training tests |
| `tests/training/test_eval_harness.py` | ~150 | Eval harness tests |
| `tests/training/test_model_router.py` | ~120 | Model router tests |
| `tests/training/test_self_improvement_cycle.py` | ~80 | Cycle orchestration tests |
| `tests/training/test_continuous_rl_trainer.py` | ~100 | RL trainer tests |
| `tests/training/test_knowledge_distiller.py` | ~80 | Distillation tests |

### Modify:

| File | Change |
|------|--------|
| `core/config.py` | Add TrainingConfig (adapters_dir, models_dir, unsloth_enabled, eval_results_dir, self_improvement section, distillation section) |
| `core/loop/autonomous_loop.py` | Add weekly self-improvement cycle schedule; wire continuous RL trainer |
| `core/loop/decision_engine.py` | Add `collect_recent_decisions()`, `evaluate_model()`; expose state buffer for RL training |
| `core/inference/llm_providers.py` | Integrate ModelRouter for adapter-aware routing |
| `core/inference/__init__.py` | Export ModelRouter |
| `core/memory/episodic.py` | Add query_by_reward_range(), query_by_date_range() for data collection |
| `core/memory/policy.py` | Add batch_get_states() for RL training data export |
| `hand/` (scheduled agents) | Add self-improvement hand that triggers the weekly cycle |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| LoRA training time (7B, rank 16, 500 steps) | N/A | <30min | Measure end-to-end on RTX 5070 Ti |
| LoRA VRAM usage | N/A | <8GB | nvidia-smi monitoring during training |
| Adapter load time (Ollama swap) | N/A | <5s | Measure from swap command to model ready |
| Data collection throughput | N/A | >1000 pairs/min | Memory scan rate |
| Eval harness execution time | N/A | <10min for all domains | Run all 4 benchmarks |
| Regression detection accuracy | N/A | 100% | Inject known regression, verify detection |
| Weekly cycle total time | N/A | <2h | From start to completion |
| Eval score improvement per cycle | N/A | >1% | Compare before/after scores |
| Maximum regression allowed | N/A | <2% | Comparison delta threshold |
| Knowledge distillation pairs | N/A | >500/week | Count generated training pairs |
| Cloud token savings via distillation | N/A | >100K tokens/week | Estimated from distillation |
| RL training step time | N/A | <5min | Train on 1000 decisions |
| RL policy improvement per cycle | N/A | >5% avg reward | Compare before/after simulated evaluation |

### 8.2 Qualitative Criteria

1. Fine-tuned adapters produce noticeably better responses in their domain (judged by user)
2. Model routing is invisible — no latency added, no routing errors
3. The self-improvement cycle runs silently without disrupting normal operations
4. Adapters can be swapped at runtime without restarting Ollama
5. If an adapter degrades performance, the previous version is automatically restored
6. The RL policy makes increasingly better decisions over weeks
7. Distilled knowledge from cloud models is indistinguishable from human-curated data

### 8.3 Regression Checks

1. Existing decision engine still works without RL trainer enabled
2. Existing inference routing still works without ModelRouter (feature-flag)
3. Episodic memory query performance not degraded by new query methods
4. All existing tests pass: `pytest tests/`
5. Ollama model serving not interrupted by adapter training/deployment
6. No tokenization mismatches between base model and adapter

---

## 9. Dependencies

### 9.1 External Packages

```txt
# Add to requirements.txt:
unsloth>=2024.12.0           # Fast LoRA training (2x speed, 50% less VRAM)
peft>=0.12.0                 # Parameter-Efficient Fine-Tuning
transformers>=4.42.0          # HuggingFace model loading
bitsandbytes>=0.43.0          # 4-bit quantization for QLoRA
trl>=0.9.0                   # SFTTrainer and DPOTrainer
torch>=2.3.0                  # PyTorch (likely already present)
datasets>=2.19.0              # Dataset handling
accelerate>=0.30.0            # Multi-GPU support (future)
scipy>=1.12.0                 # Evaluation metrics (already in requirements)
wandb>=0.17.0                 # Optional experiment tracking
```

### 9.2 System Requirements

- RTX 5070 Ti 12GB — LoRA training target: <8GB VRAM for 7B models at 4-bit
- 50GB free disk for adapter storage (~500MB per adapter, 50+ adapters)
- Ollama 0.3+ for Modelfile-based adapter deployment
- CUDA 12.1+ for unsloth/triton compatibility
- Training runs during idle hours (03:00 Sunday) to avoid GPU contention

### 9.3 Internal Dependencies

1. **specs-02 (Parallel Distribution):** Self-improvement cycle should eventually run as a background service via EventBus. For now, direct method calls.
2. **specs-04 (Security):** Data collection reads episodic memory — must respect encryption boundaries (AES-256). Training data must not leak sensitive information.
3. **specs-10 (Research Lab):** The research domain adapter training data can be enriched by research engine insights. Research benchmarks should use real research outputs.

### 9.4 VRAM Budget for Training

```
RTX 5070 Ti — 12GB VRAM budget:

Peak usage during 7B LoRA training (4-bit):
  Model weights:      ~4.5GB (4-bit GPTQ)
  Activations:        ~1.5GB (gradient checkpointing)
  Optimizer states:   ~0.5GB (AdamW 8-bit)
  LoRA adapters:      ~0.1GB (rank 16)
  CUDA overhead:      ~1.0GB
  Total:              ~7.6GB  ← fits comfortably

During training, VECTOR should:
  - Use CPU inference for user requests (via graceful degradation)
  - Or use a different model entirely (voice uses vector-focus, not training target)
  - Or queue requests until training completes (~30min)
```

---

## 10. Rollout Plan

### Phase 1 (Week 1): Foundation
- Training package structure
- Data collector scanning episodic memory
- LoRA trainer with unsloth
- Small-scale training test (50 examples, 100 steps)
- VRAM verification

### Phase 2 (Week 2): Evaluation + Routing
- Eval harness with 4 domain benchmarks
- Model router with task classification
- Hot-swap adapter mechanism
- Regression detection working

### Phase 3 (Week 3): Self-Improvement Cycle
- Weekly cycle orchestrator
- Continuous RL trainer
- Knowledge distillation pipeline
- First full end-to-end cycle

### Phase 4 (Week 4): Production
- Autonomous loop integration
- Silent background operation
- Dashboard integration (cycle history, adapter versions, scores)
- Monitoring: training success rate, eval trends, VRAM usage patterns

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| VRAM OOM during training + inference | Medium | High | Schedule training during idle hours; use graceful degradation to CPU mode during training |
| Adapter degrades performance | Medium | Medium | Eval harness rejects regressions >2%; automatic rollback to previous adapter |
| Insufficient training data | High | Low | Minimum 100 examples per domain; skip domains without enough data; augment with synthetic data |
| Unsloth compatibility issues | Low | Medium | Fall back to standard peft training; detect unsloth at import time |
| Training takes too long (user impact) | Low | Medium | Configurable max training duration; checkpoint and resume capability |
| Ollama adapter swapping fails | Low | Medium | Fall back to previous adapter; log error; retry with model restart |
| Distillation generates low-quality data | Medium | Medium | Filter by cloud model agreement; sample human-review before training |
| Model router misclassifies tasks | Medium | Low | Multi-stage classification with fallback; log misclassifications for tuning |
