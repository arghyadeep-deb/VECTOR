# SPEC-10: Research Lab — Automated Experiment Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's research lab from 35/100 to 90/100 — an automated hypothesis→experiment→analysis→report pipeline with sandboxed execution that generates ArXiv-style research papers autonomously.

**Architecture:** Build an end-to-end automated research pipeline. HypothesisEngine generates testable hypotheses from episodic memory patterns. ExperimentDesigner converts hypotheses into structured experiments with controlled variables, metrics, and sample sizes. SandboxExecutor runs experiments in isolated Docker/nsjail containers with CPU/RAM/time/network limits. ResultAnalyzer applies statistical testing (scipy/statsmodels) and generates publication-quality plots. ReportAssembler composes everything into a structured markdown report. AutoResearchAgent orchestrates the full cycle on demand or on a schedule, storing results in episodic memory and the Obsidian vault.

**Tech Stack:** Docker SDK, nsjail (optional Linux sandbox), scipy, statsmodels, matplotlib, plotly, pandas, jinja2 (report templates), black/ruff (code formatting before execution)

**Score:** Current 35/100 → Target 90/100

---

## 1. Problem Statement

### 1.1 Current Limitations

The research lab scores 35/100 across six dimensions:

| Dimension | Score | Issue |
|-----------|-------|-------|
| Research Engine Quality | 70/100 | `core/research_engine/` has 34 sub-modules. Deep web search, code research, paper search, arXiv search all work well. Pattern extraction and insight generation are solid. |
| Automated Experimentation | 0/100 | No experiment pipeline exists. Every research insight must be manually validated. No hypothesis → test → verify cycle. |
| Code Execution Safety | 20/100 | Coding assistant can execute code but runs in-process with no sandboxing. A buggy experiment script can crash VECTOR or corrupt memory. |
| Reproducibility | 10/100 | No experiment logging, no seed tracking, no parameter recording. Results cannot be reproduced. |
| Report Generation | 30/100 | Research insights are stored as text in episodic memory. No structured reports, no plots, no methodology sections. |
| End-to-End Automation | 0/100 | No single trigger that takes a research question through to a published report. Everything is manual, ad-hoc. |

### 1.2 Root Causes

1. **No experiment abstraction:** No `Experiment`, `Variable`, `Hypothesis`, `Result` data classes exist. Research insights are free-form text.
2. **No sandbox:** `core/coding_assistant/` executes code with `exec()` or subprocess — same memory space, same filesystem, same GPU. A memory leak kills VECTOR.
3. **No analysis toolkit:** No statistical testing pipeline. Research insights are qualitative — "I noticed X pattern" without significance testing.
4. **No report template:** No structured format for research output. Results live in ephemeral chat context, not persistent documents.
5. **No orchestrator:** No agent that chains hypothesis → experiment → analysis → report. Each step requires manual intervention.

### 1.3 Impact

- Research insights are unvalidated — VECTOR cannot distinguish genuine patterns from noise
- Running a coding experiment risks process crashes or GPU OOM
- Results are non-reproducible — no record of parameters, seeds, or methodology
- No shareable artifacts — insights stay in chat history
- Each experiment takes hours of manual orchestration

---

## 2. Current Architecture

### 2.1 Research Engine Structure

```
core/research_engine/
├── __init__.py              # ResearchEngine facade
├── deep_web_research.py     # Deep web search with recursive exploration
├── code_research.py         # Source code analysis and pattern extraction
├── paper_research.py        # Academic paper search and summarization
├── arxiv_search.py          # arXiv API client with paper retrieval
├── insight_generator.py     # Pattern extraction and insight synthesis
├── topic_tracker.py         # Topic clustering and trend detection
├── source_tracker.py        # Source credibility and citation tracking
├── comparison_engine.py     # Cross-source comparison and synthesis
├── methodology_analyzer.py  # Methodology extraction from papers
├── citation_graph.py        # Citation network analysis
├── hypothesis_engine.py     # Hypothesis generation from patterns
├── data_source_manager.py   # Multi-source data integration
├── search_quality.py        # Search result quality scoring
├── knowledge_gap.py         # Knowledge gap identification
├── information_quality.py   # Information quality assessment
└── ... (20 more modules)

districts/research/
├── __init__.py              # ResearchDistrict agent
├── research_agent.py        # Main research orchestration agent
└── ...
```

### 2.2 Karpathy Lab Structure

```
districts/karpathy_lab/
├── __init__.py              # KarpathyLab district agent
├── autoresearch_runner.py   # Auto-research execution runner
├── code_typer.py            # Code generation and typing simulation
├── architecture_builder.py  # Architecture design and implementation
├── data_prep.py             # Dataset preparation and preprocessing
├── progress_tracker.py      # Progress tracking and checkpointing
└── ...
```

### 2.3 Coding Assistant Structure

```
core/coding_assistant/
├── __init__.py              # CodingAssistant facade
├── acp_protocol.py          # Agent-Computer Protocol implementation
├── code_conductor.py        # Code orchestration and file management
├── code_executor.py         # Code execution (in-process — UNSAFE)
├── code_generator.py        # Code generation with context
├── command_builder.py       # Shell command construction
├── file_manager.py          # File creation and modification
├── project_manager.py       # Project structure management
└── ...
```

### 2.4 Current Hypothesis → Insight Flow

```
ResearchEngine.analyze(topic)
  → deep_web_research(), paper_research(), etc.
  → insight_generator.extract_patterns()
  → hypothesis_engine.generate_hypotheses()
  → [STOPS HERE — no experiment, no validation]
  → insight stored as text in episodic memory
```

No experiment design, no execution, no analysis, no report.

---

## 3. Target Architecture

### 3.1 High-Level Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        AutoResearchAgent                                  │
│                                                                          │
│  1. HypothesisEngine.generate(topic)                                     │
│     → "Using LoRA rank 16 vs rank 32 on 5070 Ti: rank 16 achieves       │
│        90% of the performance at 60% of the VRAM"                        │
│                                                                          │
│  2. ExperimentDesigner.design(hypothesis)                                │
│     → Independent var: LoRA rank (16, 32)                                │
│     → Dependent vars: perplexity, training time, VRAM peak               │
│     → Controlled vars: model, dataset, learning rate, seed               │
│     → Sample size: 3 runs per condition                                  │
│     → Script template generated                                          │
│                                                                          │
│  3. SandboxExecutor.run(experiment)                                      │
│     → Docker container: 4GB RAM, 2 CPUs, no network                     │
│     → Injects experiment script                                          │
│     → Captures stdout, stderr, return code, resource usage               │
│     → Returns structured results dict                                    │
│                                                                          │
│  4. ResultAnalyzer.analyze(results)                                      │
│     → Descriptive statistics per group                                   │
│     → Shapiro-Wilk normality test                                        │
│     → Mann-Whitney U test (non-parametric comparison)                    │
│     → Effect size (Cohen's d)                                            │
│     → Plot: bar chart with error bars, violin plot                       │
│     → Returns AnalysisResult with stats, plots, interpretations          │
│                                                                          │
│  5. ReportAssembler.assemble(analysis)                                   │
│     → Title, Authors (VECTOR), Abstract                                  │
│     → Introduction, Methodology, Results, Discussion, Conclusion         │
│     → Embedded plots (base64 or file refs)                               │
│     → Statistical summary table                                          │
│     → Output: structured markdown + optional PDF                         │
│                                                                          │
│  6. Store in episodic memory + Obsidian vault                            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    AutoResearchAgent                              │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐ │
│  │Hypothesis    │  │ExperimentDesigner │  │  SandboxExecutor   │ │
│  │Engine        │  │                  │  │                    │ │
│  │(exists)      │  │ - parse_hypo     │  │ - prepare_docker   │ │
│  │              │  │ - design_experiment│ │ - inject_script    │ │
│  │              │  │ - gen_template   │  │ - run_container    │ │
│  │              │  │ - validate_design│  │ - collect_results  │ │
│  └──────┬───────┘  └────────┬─────────┘  └─────────┬──────────┘ │
│         │                   │                       │            │
│         └───────────────────┼───────────────────────┘            │
│                             │                                     │
│  ┌──────────────────────────▼──────────────────────────────┐     │
│  │                 ResultAnalyzer                           │     │
│  │  - descriptive_stats    - normality_test                │     │
│  │  - significance_test    - effect_size                   │     │
│  │  - generate_plots       - interpret_results             │     │
│  └──────────────────────────┬──────────────────────────────┘     │
│                             │                                     │
│  ┌──────────────────────────▼──────────────────────────────┐     │
│  │                 ReportAssembler                          │     │
│  │  - assemble_report     - render_template                │     │
│  │  - embed_plots         - export_markdown                │     │
│  │  - export_pdf          - store_in_memory                │     │
│  └─────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Data Model

```python
@dataclass
class Hypothesis:
    id: str
    statement: str
    source: str                # "pattern_extraction" | "user_query" | "literature_review"
    confidence: float
    generated_at: datetime
    related_insights: list[str]

@dataclass
class ExperimentDesign:
    hypothesis_id: str
    independent_vars: dict[str, list]    # {"lora_rank": [16, 32]}
    dependent_vars: list[str]            # ["perplexity", "vram_peak"]
    controlled_vars: dict[str, Any]      # {"model": "qwen2.5:7b", "seed": 42}
    sample_size: int                     # runs per condition
    script_template: str                 # Python code template with {{placeholders}}
    resource_limits: dict                # {"cpu": 2, "ram_gb": 4, "timeout_s": 300}

@dataclass
class ExperimentResult:
    experiment_id: str
    raw_output: dict                     # per-run results keyed by condition
    metrics: dict                        # aggregated metrics
    artifacts: list[str]                 # paths to generated plots/data
    success: bool
    duration_s: float
    error: str | None

@dataclass
class AnalysisResult:
    experiment_id: str
    descriptive: dict                    # mean, std, min, max per group
    normality: dict                      # shapiro-wilk p-values per group
    significance: dict                   # test_name, test_statistic, p_value
    effect_size: dict                    # cohens_d, interpretation
    plots: list[dict]                    # {title, path, type}
    interpretation: str                  # LLM-generated summary
    raw_data_path: str

@dataclass
class ResearchReport:
    title: str
    hypothesis: Hypothesis
    methodology: str                     # generated methodology section
    results: AnalysisResult
    discussion: str                      # LLM-generated discussion
    conclusion: str
    references: list[str]
    generated_at: datetime
    report_path: str                     # path to markdown file
```

---

## 4. Component Breakdown

### 4.1 ExperimentDesigner

**File:** `core/research_engine/experiment_designer.py`

**Purpose:** Convert a Hypothesis into a structured, executable ExperimentDesign.

**Key Methods:**

```python
class ExperimentDesigner:
    def design(self, hypothesis: Hypothesis) -> ExperimentDesign:
        """Uses LLM + templates to design an experiment from a hypothesis."""

    def _identify_variables(self, hypothesis: str) -> tuple[dict, list, dict]:
        """Extract independent vars (with levels), dependent vars, controlled vars."""

    def _select_template(self, design: ExperimentDesign) -> str:
        """Choose experiment template based on domain (ML, stats, benchmarking)."""

    def _generate_script(self, design: ExperimentDesign) -> str:
        """Fill template with variables. Include seed setting, timing, resource tracking."""

    def validate_design(self, design: ExperimentDesign) -> list[str]:
        """Check: sample size >= 2, at least 1 IV and 1 DV, resource limits reasonable."""
```

**Templates:** `core/research_engine/templates/`
- `benchmark.py.j2` — Performance benchmarking (time, memory, throughput)
- `ml_train.py.j2` — ML model training comparison (accuracy, loss curves)
- `statistical_test.py.j2` — A/B testing with built-in analysis
- `ablation.py.j2` — Ablation studies (remove component → measure impact)

**LLM Prompt Pattern:**
```
Given hypothesis: "{hypothesis.statement}"
Design a controlled experiment.
Independent variable(s): what do we change?
Dependent variable(s): what do we measure?
Controlled variables: what stays fixed?
Sample size: how many runs per condition?
Resource limits: CPU, RAM, timeout.
```

### 4.2 SandboxExecutor

**File:** `core/research_engine/sandbox_executor.py`

**Purpose:** Execute experiment scripts in isolated containers with resource limits and result collection.

**Key Methods:**

```python
class SandboxExecutor:
    def __init__(self, backend: str = "docker"):  # "docker" | "nsjail" | "subprocess"

    async def run(self, design: ExperimentDesign) -> ExperimentResult:
        """Full lifecycle: prepare → execute → collect → cleanup."""

    async def _prepare_docker(self, script: str) -> str:
        """Write script to temp dir, build/pull base image, set resource limits."""

    async def _run_container(self, image: str, script_path: str, limits: dict) -> dict:
        """docker run with --cpus, --memory, --network=none, --timeout."""

    async def _collect_results(self, container_id: str) -> ExperimentResult:
        """Read stdout/stderr, extract JSON result, copy artifacts."""

    def _cleanup(self, container_id: str):
        """Remove container and temp files."""

    def _fallback_subprocess(self, script: str, limits: dict) -> dict:
        """Isolate via subprocess with resource.setrlimit if Docker unavailable."""
```

**Docker Image:** `vector-experiment-runner:latest`
- Base: `python:3.11-slim`
- Packages: numpy, scipy, torch (CPU-only), pandas, matplotlib
- No network access
- Read-only filesystem (except /tmp)
- Runs as non-root user
- Built lazily on first run

**Safety Measures:**
- CPU limit: default 2 cores
- RAM limit: default 4GB
- Timeout: default 300s (configurable)
- Network: off
- Filesystem: read-only except /tmp and /results
- No GPU access by default (opt-in via design)
- Kill on OOM or timeout
- Max disk writes: 1GB

### 4.3 ResultAnalyzer

**File:** `core/research_engine/result_analyzer.py`

**Purpose:** Statistical analysis and visualization of experiment results.

**Key Methods:**

```python
class ResultAnalyzer:
    async def analyze(self, result: ExperimentResult) -> AnalysisResult:
        """Full analysis pipeline."""

    def descriptive_stats(self, data: pd.DataFrame) -> dict:
        """Mean, std, min, max, median, quartiles per group."""

    def normality_test(self, data: pd.DataFrame) -> dict:
        """Shapiro-Wilk test per group. If n > 5000, use D'Agostino's K²."""

    def significance_test(self, data: pd.DataFrame, design: ExperimentDesign) -> dict:
        """Auto-select: t-test (parametric, 2 groups), ANOVA (parametric, 3+),
           Mann-Whitney (non-parametric, 2), Kruskal-Wallis (non-parametric, 3+).
           Also: paired vs independent based on design."""

    def effect_size(self, data: pd.DataFrame, test_type: str) -> dict:
        """Cohen's d for t-test, eta-squared for ANOVA, r for Mann-Whitney."""

    def generate_plots(self, data: pd.DataFrame, analysis: dict) -> list[dict]:
        """Generate: bar chart with error bars, violin plot, box plot, 
           scatter plot (if longitudinal), correlation heatmap (if multiple DVs).
           Returns dicts with {title, path, type, base64_thumbnail}."""

    def interpret(self, analysis: dict) -> str:
        """LLM-generated interpretation: "Rank 16 achieves 90% of rank 32's
           performance (p<0.05, d=0.8) while using 40% less VRAM.""""
```

**Statistical Test Selection Logic:**
```
if data is normal (p > 0.05):
    if groups == 2:
        use t-test (independent or paired)
    else:
        use ANOVA (one-way or repeated measures)
else:
    if groups == 2:
        use Mann-Whitney U (independent) or Wilcoxon (paired)
    else:
        use Kruskal-Wallis
always report: test_statistic, p_value, effect_size, interpretation
```

### 4.4 ReportAssembler

**File:** `core/research_engine/report_assembler.py`

**Purpose:** Compose structured research reports from analysis results.

**Key Methods:**

```python
class ReportAssembler:
    async def assemble(self, analysis: AnalysisResult, hypothesis: Hypothesis) -> ResearchReport:
        """Full report assembly."""

    def _generate_title(self, hypothesis: Hypothesis) -> str:
        """LLM: convert hypothesis into paper-style title."""

    def _generate_abstract(self, hypothesis: Hypothesis, analysis: AnalysisResult) -> str:
        """LLM: 150-250 word abstract following standard structure."""

    def _generate_introduction(self, hypothesis: Hypothesis) -> str:
        """LLM: background, motivation, hypothesis, expected contribution."""

    def _generate_methodology(self, design: ExperimentDesign) -> str:
        """Structured methodology from experiment design."""

    def _generate_results_section(self, analysis: AnalysisResult) -> str:
        """Results with embedded plots and statistical tables."""

    def _generate_discussion(self, analysis: AnalysisResult, hypothesis: Hypothesis) -> str:
        """LLM: interpretation, limitations, future work."""

    def render_markdown(self, report: ResearchReport) -> str:
        """Render report using jinja2 template."""

    async def store_report(self, report: ResearchReport):
        """Store in episodic memory and write to Obsidian vault."""
```

**Report Template Structure (jinja2):**
```markdown
# {{ title }}

**Authors:** VECTOR Autonomous Research Agent
**Date:** {{ date }}

## Abstract

{{ abstract }}

---

## 1. Introduction

{{ introduction }}

## 2. Methodology

### 2.1 Hypothesis
{{ hypothesis.statement }}

### 2.2 Experimental Design
| Variable | Type | Values |
|----------|------|--------|
{% for var, vals in design.independent_vars.items() %}
| {{ var }} | Independent | {{ vals }} |
{% endfor %}

### 2.3 Controlled Variables
{{ controlled_vars }}

### 2.4 Statistical Analysis
{{ statistical_methods }}

## 3. Results

### 3.1 Descriptive Statistics
{{ descriptive_table }}

### 3.2 Statistical Tests
| Test | Statistic | p-value | Effect Size |
|------|-----------|---------|-------------|
{% for test in tests %}
| {{ test.name }} | {{ test.statistic }} | {{ test.p_value }} | {{ test.effect_size }} |
{% endfor %}

### 3.3 Visualizations
{% for plot in plots %}
![{{ plot.title }}]({{ plot.path }})
{% endfor %}

## 4. Discussion

{{ discussion }}

## 5. Conclusion

{{ conclusion }}

---

**Report generated by VECTOR Research Lab | Experiment ID: {{ experiment_id }}**
```

### 4.5 AutoResearchAgent

**File:** `core/research_engine/auto_research_agent.py`

**Purpose:** Orchestrate the complete research cycle from trigger to stored report.

**Key Methods:**

```python
class AutoResearchAgent:
    def __init__(self):
        self.hypothesis_engine: HypothesisEngine
        self.experiment_designer: ExperimentDesigner
        self.sandbox_executor: SandboxExecutor
        self.result_analyzer: ResultAnalyzer
        self.report_assembler: ReportAssembler

    async def run_full_cycle(self, topic: str | None = None) -> ResearchReport:
        """If topic: generate specific hypothesis. Else: pick highest-confidence untested hypothesis."""

    async def run_from_hypothesis(self, hypothesis: Hypothesis) -> ResearchReport:
        """Full pipeline from an existing hypothesis."""

    async def scheduled_research(self):
        """Called by autonomous loop. Checks: are there untested hypotheses with confidence > 0.7?"""

    async def _validate_results(self, report: ResearchReport) -> bool:
        """Check: p-value reported, effect size reported, plots generated, no obvious errors."""
```

**Autonomous Loop Integration:**
```
Every 6 hours (configurable):
  1. ResearchEngine scans episodic memory for patterns
  2. HypothesisEngine generates top-3 hypotheses by confidence
  3. For each hypothesis with confidence > 0.7:
     a. Run full research cycle
     b. Store report
     c. Update hypothesis confidence based on results
  4. Summarize findings in autonomous loop log
```

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: ExperimentDesigner + SandboxExecutor

**Responsibility:** Design experiments from hypotheses and execute them safely.

**Tasks:**
1. Create `ExperimentDesign` and `ExperimentResult` dataclasses in `core/research_engine/models.py`
2. Create `core/research_engine/experiment_designer.py` with LLM-driven variable extraction and template filling
3. Create template files: `core/research_engine/templates/benchmark.py.j2`, `ml_train.py.j2`, `statistical_test.py.j2`, `ablation.py.j2`
4. Create `core/research_engine/sandbox_executor.py` with Docker backend
5. Create Dockerfile at `docker/experiment-runner/Dockerfile`
6. Implement resource limit enforcement (CPU, RAM, timeout, network=off)
7. Implement result collection (stdout, stderr, artifacts, resource usage)
8. Implement `subprocess` fallback for systems without Docker
9. Create `core/research_engine/bootstrap_sandbox.py` — build Docker image if needed
10. Write unit tests: `tests/research_engine/test_experiment_designer.py`, `tests/research_engine/test_sandbox_executor.py`

### 5.2 Agent B: ResultAnalyzer + ReportAssembler + AutoResearchAgent

**Responsibility:** Analyze results, assemble reports, and orchestrate the full cycle.

**Tasks:**
1. Create `AnalysisResult` and `ResearchReport` dataclasses in `core/research_engine/models.py`
2. Create `core/research_engine/result_analyzer.py` with descriptive stats, normality tests, significance tests, effect sizes
3. Implement auto-test-selection logic (parametric vs non-parametric based on normality)
4. Implement plot generation (bar+error, violin, box, scatter, correlation heatmap)
5. Create `core/research_engine/report_assembler.py` with LLM-driven section generation
6. Create jinja2 report template at `core/research_engine/templates/report.md.j2`
7. Implement markdown rendering and memory/Obsidian storage
8. Create `core/research_engine/auto_research_agent.py` orchestrating the full pipeline
9. Integrate with autonomous loop (scheduled research every 6h)
10. Write unit tests: `tests/research_engine/test_result_analyzer.py`, `tests/research_engine/test_report_assembler.py`, `tests/research_engine/test_auto_research_agent.py`

---

## 6. Implementation Steps

### 6.1 Phase 1: Data Models + ExperimentDesigner (Agent A)

**Step 1.1: Create data models**
- [ ] Create `core/research_engine/models.py` with Hypothesis, ExperimentDesign, ExperimentResult, AnalysisResult, ResearchReport dataclasses
- [ ] All fields typed with proper validation (pydantic or dataclass with __post_init__)
- [ ] Serialization methods (to_dict, from_dict) for memory storage

**Step 1.2: Create ExperimentDesigner**
- [ ] Create `core/research_engine/experiment_designer.py`
- [ ] LLM prompt for variable extraction from hypothesis
- [ ] Template selection logic per experiment type
- [ ] Template generation with variable substitution
- [ ] Design validation (sample size >= 2, at least 1 IV and 1 DV)
- [ ] Test with 3 sample hypotheses covering benchmark, ML, statistical domains

**Step 1.3: Create experiment templates**
- [ ] Create `core/research_engine/templates/` directory
- [ ] `benchmark.py.j2` — time, memory, throughput measurement
- [ ] `ml_train.py.j2` — model training with metric tracking
- [ ] `statistical_test.py.j2` — A/B test with built-in stats
- [ ] `ablation.py.j2` — component removal impact measurement

**Step 1.4: Test**
- [ ] `tests/research_engine/test_models.py` — dataclass creation, serialization roundtrip
- [ ] `tests/research_engine/test_experiment_designer.py` — variable extraction, template filling, validation

### 6.2 Phase 2: SandboxExecutor (Agent A)

**Step 2.1: Docker setup**
- [ ] Create `docker/experiment-runner/Dockerfile` (python:3.11-slim, deps, non-root user)
- [ ] Create `core/research_engine/bootstrap_sandbox.py` — build/pull image, verify Docker running
- [ ] Script to auto-detect Docker availability and build image

**Step 2.2: SandboxExecutor implementation**
- [ ] Create `core/research_engine/sandbox_executor.py`
- [ ] Docker backend: prepare script → docker run with limits → collect → cleanup
- [ ] Resource limit enforcement (--cpus, --memory, --network=none, timeout)
- [ ] Result collection: read stdout/stderr, extract JSON, copy artifacts
- [ ] Subprocess fallback with resource.setrlimit
- [ ] Error handling: timeout kills, OOM detection, non-zero exit

**Step 2.3: Test**
- [ ] `tests/research_engine/test_sandbox_executor.py` — execute harmless script, verify result collection
- [ ] Test resource limits: script that allocates 8GB RAM → verify OOM kill
- [ ] Test timeout: script that sleeps 10s with 5s timeout → verify kill
- [ ] Test subprocess fallback mode

### 6.3 Phase 3: ResultAnalyzer + ReportAssembler (Agent B)

**Step 3.1: ResultAnalyzer**
- [ ] Create `core/research_engine/result_analyzer.py`
- [ ] Descriptive statistics (mean, std, min, max, median, quartiles)
- [ ] Normality test (Shapiro-Wilk, auto-switch to D'Agostino for n>5000)
- [ ] Significance test with auto-selection logic
- [ ] Effect size calculation (Cohen's d, eta-squared, r)
- [ ] Plot generation (matplotlib — bar+error, violin, box, scatter, heatmap)
- [ ] Plot thumbnailing for report embedding
- [ ] LLM interpretation of statistical results

**Step 3.2: ReportAssembler**
- [ ] Create `core/research_engine/report_assembler.py`
- [ ] Create `core/research_engine/templates/report.md.j2` jinja2 template
- [ ] LLM prompts for: title, abstract, introduction, methodology, discussion, conclusion
- [ ] Results section with embedded plots (base64 inline + file refs)
- [ ] Statistical summary table generation
- [ ] Markdown rendering
- [ ] Storage: save markdown to `reports/` directory + episodic memory + Obsidian

**Step 3.3: Test**
- [ ] `tests/research_engine/test_result_analyzer.py` — known dataset, verify statistical outputs
- [ ] `tests/research_engine/test_report_assembler.py` — verify report structure, plot embedding, template rendering
- [ ] Integration test: mock ExperimentResult → analyze → assemble report

### 6.4 Phase 4: AutoResearchAgent + Integration (Agent B)

**Step 4.1: AutoResearchAgent**
- [ ] Create `core/research_engine/auto_research_agent.py`
- [ ] `run_full_cycle(topic)` — complete pipeline from hypothesis to report
- [ ] `run_from_hypothesis(hypothesis)` — partial pipeline starting at experiment
- [ ] `scheduled_research()` — check for high-confidence untested hypotheses
- [ ] Result validation (p-value, effect size, plots, no errors)
- [ ] Progress logging and error recovery

**Step 4.2: Autonomous loop integration**
- [ ] Add scheduled research to `AutonomousLoop` (every 6h, configurable)
- [ ] Add research results to autonomous loop log
- [ ] Add `max_concurrent_experiments` config (default 1 — GPU constraint)

**Step 4.3: Obsidian vault integration**
- [ ] Write research reports to `research/` folder in Obsidian vault
- [ ] Add frontmatter: title, date, experiment_id, hypothesis_id, significance
- [ ] Generate index page: `research/INDEX.md` listing all experiments

**Step 4.4: E2E test**
- [ ] End-to-end: pick hypothesis → design → execute → analyze → report → store
- [ ] Measure: total cycle time, per-step time, validation results

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `core/research_engine/models.py` | ~120 | Hypothesis, ExperimentDesign, ExperimentResult, AnalysisResult, ResearchReport dataclasses |
| `core/research_engine/experiment_designer.py` | ~250 | LLM-driven experiment design from hypothesis |
| `core/research_engine/sandbox_executor.py` | ~300 | Docker/nsjail sandboxed code execution |
| `core/research_engine/result_analyzer.py` | ~350 | Statistical analysis and plot generation |
| `core/research_engine/report_assembler.py` | ~250 | Structured report assembly + storage |
| `core/research_engine/auto_research_agent.py` | ~200 | Full pipeline orchestration |
| `core/research_engine/bootstrap_sandbox.py` | ~80 | Docker image setup and verification |
| `core/research_engine/templates/report.md.j2` | ~80 | Jinja2 report template |
| `core/research_engine/templates/benchmark.py.j2` | ~60 | Benchmark experiment template |
| `core/research_engine/templates/ml_train.py.j2` | ~80 | ML training experiment template |
| `core/research_engine/templates/statistical_test.py.j2` | ~50 | Statistical test template |
| `core/research_engine/templates/ablation.py.j2` | ~60 | Ablation study template |
| `docker/experiment-runner/Dockerfile` | ~30 | Experiment runtime container |
| `tests/research_engine/test_experiment_designer.py` | ~100 | Experiment designer unit tests |
| `tests/research_engine/test_sandbox_executor.py` | ~120 | Sandbox executor tests |
| `tests/research_engine/test_result_analyzer.py` | ~150 | Result analyzer tests |
| `tests/research_engine/test_report_assembler.py` | ~100 | Report assembler tests |
| `tests/research_engine/test_auto_research_agent.py` | ~80 | Auto-research agent tests |

### Modify:

| File | Change |
|------|--------|
| `core/research_engine/__init__.py` | Export new classes (ExperimentDesigner, SandboxExecutor, ResultAnalyzer, ReportAssembler, AutoResearchAgent) |
| `core/loop/autonomous_loop.py` | Add scheduled research task every 6h |
| `core/config.py` | Add ResearchLabConfig section (sandbox_backend, max_concurrent, schedule_interval, docker_image) |
| `districts/research/research_agent.py` | Wire AutoResearchAgent as research dispatch target |
| `districts/karpathy_lab/autoresearch_runner.py` | Refactor to use new pipeline components |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| Hypothesis → Experiment time | N/A | <30s | Time from hypothesis input to ExperimentDesign output |
| Experiment execution time (simple) | N/A | <5min | Time for a benchmark experiment (3 conditions, 3 runs each) |
| Experiment execution time (complex) | N/A | <30min | Time for an ML training experiment |
| Sandbox isolation | N/A | 100% | Verify no interference between concurrent experiments |
| Docker availability auto-detect | N/A | 100% | Bootstrap detects Docker and builds image or falls back |
| Statistical test accuracy | N/A | 100% | Known datasets with known p-values produce correct results |
| Plot generation | N/A | 5 plot types | Bar+error, violin, box, scatter, heatmap all generating correctly |
| Report structure completeness | N/A | 100% | All sections (title, abstract, intro, method, results, discussion, conclusion) present |
| Report storage in memory | N/A | 100% | Report stored as structured entry in episodic memory |
| Report storage in Obsidian | N/A | 100% | Report written to Obsidian vault research/ folder |
| Auto-research cycle success rate | N/A | >90% | Full cycle completes without error |
| Sandbox memory limit enforcement | N/A | 100% | OOM script correctly killed at 4GB limit |
| Sandbox timeout enforcement | N/A | 100% | Sleep-10s script correctly killed at 5s timeout |

### 8.2 Qualitative Criteria

1. Research reports read like genuine academic papers (structured, cited, rigorous)
2. Statistical interpretations are accurate — no claiming significance where p > 0.05
3. Plots are publication-quality (proper labels, legends, titles, colorblind-friendly)
4. Failed experiments produce useful error messages, not cryptic tracebacks
5. Auto-research finds genuinely interesting hypotheses, not trivial patterns
6. Sandbox isolation feels invisible — no manual Docker commands needed
7. Reports in Obsidian are immediately readable and linkable

### 8.3 Regression Checks

1. Existing `core/research_engine/` sub-modules still work independently
2. Karpathy Lab district still functions without the new pipeline
3. Coding assistant code execution (non-sandboxed) still works for interactive use
4. Episodic memory storage format unchanged for non-research entries
5. All existing research engine tests pass

---

## 9. Dependencies

### 9.1 External Packages

```txt
# Add to requirements.txt:
docker>=7.0.0                # Docker SDK for container management
scipy>=1.12.0                # Statistical tests (ttest, mannwhitney, shapiro, kruskal)
statsmodels>=0.14.0          # Additional statistical models and tests
matplotlib>=3.8.0            # Publication-quality plots
plotly>=5.18.0               # Interactive plots (optional, for dashboard)
jinja2>=3.1.0                # Report template rendering
pandas>=2.1.0                # Data manipulation (likely already present)
```

### 9.2 System Requirements

- Docker Desktop or Docker Engine (recommended) — for sandboxed execution
- Fallback: `resource` module (Python stdlib) for subprocess resource limits
- 2GB additional disk for Docker base image (~1.2GB)
- RTX 5070 Ti 12GB — experiments run on CPU by default, ML experiments can opt-in to GPU

### 9.3 Internal Dependencies

1. **specs-02 (Parallel Distribution):** AutoResearchAgent should eventually publish events (experiment_start, result_ready) via EventBus. Until specs-02 ships, use direct method calls.
2. **specs-06 (Obsidian Integration):** Report storage in Obsidian vault depends on vault path from config. Currently writes to `reports/` directory; Obsidian integration is an enhancement.
3. **specs-08 (Dashboard):** Research results should eventually surface on the dashboard. For now, reports are file-based.

### 9.4 Docker Setup

```bash
# Build experiment runner image (first time only):
python core/research_engine/bootstrap_sandbox.py

# Verify:
docker run --rm vector-experiment-runner:latest python -c "import numpy, scipy, pandas; print('OK')"
```

---

## 10. Rollout Plan

### Phase 1 (Week 1): Foundation
- Data models done
- ExperimentDesigner with 4 templates working
- Unit tests passing

### Phase 2 (Week 2): Sandbox Execution
- Docker sandbox working with resource limits
- Subprocess fallback working
- Experiments executing and collecting results
- Safety verified (OOM kill, timeout kill, network isolation)

### Phase 3 (Week 3): Analysis + Reports
- Statistical analysis pipeline complete
- Plot generation working
- Report assembly producing structured markdown
- Reports store in memory and file system

### Phase 4 (Week 4): Automation
- AutoResearchAgent orchestrates full cycle
- Autonomous loop integration
- Obsidian vault storage
- E2E benchmarks meet targets

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Docker not available on system | Medium | High | Subprocess fallback with resource.setrlimit; clear error message |
| Experiment script OOMs GPU | Medium | High | GPU off by default; opt-in with explicit GPU flag; memory pre-limit |
| LLM generates invalid experiment scripts | Medium | Medium | Syntax check (black/ruff) before execution; sandbox catches runtime errors |
| Statistical tests misapplied | Low | Medium | Test selection logic validated against known datasets; p-value correction for multiple comparisons (Bonferroni) |
| Report reads as AI slop | Medium | Low | Structured template forces rigor; LLM generates sections independently; human review flag |
| Long experiments block the pipeline | Low | Medium | Concurrent experiment limiting (default 1); timeout enforcement; async execution |
| Container escape vulnerability | Low | High | Non-root user, read-only FS, no network, resource limits; Docker security scanning |
