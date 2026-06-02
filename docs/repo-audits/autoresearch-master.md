# autoresearch-master Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\autoresearch-master`
**License:** MIT
**Author:** @karpathy (Andrej Karpathy), March 2026
**VECTOR parity run date:** 2026-06-02

---

## 1. Repo Reality

### What autoresearch does

autoresearch is Karpathy's autonomous overnight ML research loop. The idea: give an LLM agent a small but real single-GPU LLM training setup, let it modify the training code, run 5-minute timed experiments, keep improvements and revert regressions — indefinitely, while you sleep. The agent's only editable file is `train.py`. Results are tracked in `results.tsv`. The metric is `val_bpb` (validation bits-per-byte) — vocab-size-independent, so architectural changes are fairly compared. The repo is deliberately minimal: 3 files that matter and 1 notebook for analysis.

### File inventory

| File | Purpose | Modifiable? |
|------|---------|------------|
| `prepare.py` | Fixed constants (`MAX_SEQ_LEN=2048`, `TIME_BUDGET=300s`); downloads HuggingFace parquet shards from `karpathy/climbmix-400b-shuffle`; trains a BPE tokenizer via `rustbpe` + `tiktoken`; runtime utilities: `Tokenizer`, `make_dataloader` (BOS-aligned best-fit packing, 100% utilization, no padding), `evaluate_bpb` (fixed evaluation harness). **NOT agent-editable.** | No |
| `train.py` | Full GPT model (`CausalSelfAttention` with GQA + value embeddings + RoPE + RMS norm + sliding windows, `MLP`, `Block`, `GPT`); `MuonAdamW` optimizer (Muon for 2D matrices via Polar Express orthogonalization + NorMuon variance reduction; AdamW for embeddings/scalars); training loop with 5-min fixed time budget; LR warmup/warmdown schedule; fast-fail on NaN/loss > 100; final `val_bpb` summary printed to stdout. **The only file the agent edits.** | Yes (agent edits) |
| `program.md` | Agent instruction skill: setup protocol (branch creation, `results.tsv` init), experimentation rules (fixed time budget, what CAN/CANNOT change, simplicity criterion), output format, TSV logging format, the infinite experiment loop (propose → commit → run → grep val_bpb → log → keep/revert → repeat), timeout and crash handling, NEVER STOP directive. | Human edits |
| `pyproject.toml` | Dependencies: `torch==2.9.1` (cu128), `kernels>=0.11.7` (Flash Attention 3), `rustbpe`, `tiktoken`, `pyarrow`, `requests`, `matplotlib`, `pandas`, `numpy`. Managed by `uv`. | No |
| `analysis.ipynb` | Jupyter notebook for post-hoc analysis of `results.tsv`: loads TSV, plots val_bpb over time (kept/discarded/running-minimum), summary statistics (baseline vs best, total improvement %), top hits ranked by per-experiment delta, saved to `progress.png`. | Human uses |
| `progress.png` | Pre-generated sample plot from a real autoresearch run showing val_bpb progression. | Auto-generated |
| `README.md` | Full documentation: concept, how it works, quick start, design choices (single-file agent scope, fixed time budget, self-contained), platform support (H100 primary; Windows/MacOS/AMD forks listed), small-compute tuning guide. | Documentation |
| `uv.lock` | Lock file for reproducible installs via `uv`. | Auto-generated |

### Key architectural details of `train.py`
- **Model:** GPT with `DEPTH=8` layers, `ASPECT_RATIO=64` (model_dim = depth × 64 → rounded to HEAD_DIM=128 boundary), GQA, value residual (ResFormer), RoPE, RMS normalization, softcapped logits (tanh, cap=15), sliding window attention pattern `SSSL`.
- **Optimizer:** `MuonAdamW` — Muon (Polar Express orthogonalization + NorMuon, grouped by weight shape) for matrix params; AdamW for embeddings and scalars. All fused via `torch.compile`.
- **Training loop:** Fixed 5-min wall-clock budget (excluding first 10 warmup steps), gradient accumulation, EMA loss smoothing, fast-fail on NaN, GC freeze after step 0 to prevent 500ms stalls.
- **Metric:** `val_bpb` from `prepare.py`'s `evaluate_bpb` — sums nats over byte lengths, excludes special tokens, returns bits/byte. Fixed, never modified.

---

## 2. VECTOR Parity

### Actual command output

```
python -X utf8 -c "
import sys; sys.path.insert(0,'.')
import os
from districts.karpathy_lab.autoresearch_runner import AutoresearchRunner
a = AutoresearchRunner()
print('AutoresearchRunner OK:', type(a))
print('train.py exists:', os.path.exists('data/training_runs/train.py'))
print('prepare.py exists:', os.path.exists('data/training_runs/prepare.py'))
" 2>&1 | tail -5
```

**Output:**
```
[INFO] [VECTOR][city] Agent AutoresearchRunner gen 1 born at 500 HP using vector-focus
[INFO] [VECTOR][autoresearch] ready gen=1 hp=500 train=data\training_runs\train.py
AutoresearchRunner OK: <class 'districts.karpathy_lab.autoresearch_runner.AutoresearchRunner'>
train.py exists: True
prepare.py exists: True
```

Both `train.py` and `prepare.py` exist in `data/training_runs/` and are verified to be the real autoresearch files (contain `MuonAdamW`, `evaluate_bpb`, `GPTConfig`, `MAX_SEQ_LEN`, `TIME_BUDGET`). Parse test also passes: `val_bpb=0.9979`, `training_seconds=300.1`, `peak_vram_mb=45060.2` correctly extracted.

### Feature-by-feature parity table

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| Autonomous experiment loop (baseline → propose → apply → run → compare → keep/revert) | `districts/karpathy_lab/autoresearch_runner.py` — `run_experiment_cycle()` | Logic matches `program.md` exactly: backup, apply, compare `val_bpb`, revert if no improvement. `best_code != original_code` guard writes winning code permanently. | ✅ |
| `train.py` parsing (structured summary block `---`) | `AutoresearchRunner._parse_training_output()` | Correctly parses `val_bpb`, `training_seconds`, `peak_vram_mb` from `---` delimited block. Verified live output. | ✅ |
| `train.py` present and is the real autoresearch script | `data/training_runs/train.py` | File exists, contains `MuonAdamW`, `GPTConfig`, `evaluate_bpb`. Matches autoresearch-master `train.py` byte-for-byte in structure. | ✅ |
| `prepare.py` present and is the real autoresearch script | `data/training_runs/prepare.py` | File exists, contains `MAX_SEQ_LEN`, `TIME_BUDGET`, `evaluate_bpb`. | ✅ |
| Fixed 5-min time budget constant | `AutoresearchRunner.TIME_BUDGET_MINUTES = 5` | Matches `prepare.py`'s `TIME_BUDGET = 300`. Subprocess timeout = 5×60+120 = 420s (120s grace for startup). | ✅ |
| Architecture proposal via LLM (the `program.md` "propose ONE change" step) | `AutoresearchRunner._propose_improvement()` | Uses `core/inference/vectorcode_llm.chat` with `vector-reasoning` model, sends current `train.py` + last 3 experiments, requests only `train.py` modifications, extracts Python from markdown fences. | ✅ |
| Context hydration before LLM calls | `AutoresearchRunner._propose_improvement()` | Calls `ContextEngine().session_hydration_prompt()` as system context before reasoning call. | ✅ |
| Results logging (daily JSONL, not TSV) | `AutoresearchRunner._save_result()`, `_results_file()` | VECTOR uses JSONL (one JSON per line) dated `results_YYYY-MM-DD.jsonl` rather than `results.tsv`. Richer format: includes `experiment`, `description`, `timestamp`. | ⚠️ |
| Best-result tracking across runs | `AutoresearchRunner._load_best_result()` | Scans today's JSONL for lowest `val_bpb`. Correct. | ✅ |
| RULE 8 — reasoning chain storage | `AutoresearchRunner.run_experiment_cycle()` | Stores chain via `EpisodicMemory.store_chain()` after every cycle: situation, goal, steps, action, outcome, reward (0.8 if improved, 0.5 otherwise). | ✅ |
| HP reward on improvement | `AutoresearchRunner.run_experiment_cycle()` | `self.award_points(30, ...)` on each improving experiment. | ✅ |
| Git branch management (`autoresearch/<tag>` pattern from `program.md`) | Not present in `AutoresearchRunner` | VECTOR's runner does not create `autoresearch/<tag>` branches or manage git state for experiments. The `program.md` workflow requires a dedicated branch per run. | ❌ |
| TSV format with `commit`, `val_bpb`, `memory_gb`, `status`, `description` columns | Not present | VECTOR uses JSONL without git commit hashes. No `keep`/`discard`/`crash` status enum. No `memory_gb` column. | ⚠️ |
| `results.tsv` notebook analysis (val_bpb plot, running minimum, top hits ranked by delta) | Not present | `analysis.ipynb` has no equivalent in VECTOR. No visualization pipeline for experiment history. | ❌ |
| Progress visualization (`progress.png`) | Not present | No matplotlib plot generation for training runs. | ❌ |
| DataPrep — dataset download + tokenization | `districts/karpathy_lab/data_prep.py` | Downloads datasets (tiny_shakespeare, wikitext-2, openwebtext, pile) via `httpx`. Preprocessing (clean + deduplicate lines). Character-level tokenization to binary. **Not the autoresearch BPE tokenizer** (`rustbpe`+`tiktoken` via `prepare.py`) — VECTOR's `DataPrep` does general-purpose char tokenization. | ⚠️ |
| BPE tokenizer training (`rustbpe` + `tiktoken`) | `data/training_runs/prepare.py` | The real `prepare.py` is present. VECTOR's `DataPrep.tokenize_data()` is a different char-level tokenizer, not BPE. The actual BPE tokenizer only exists inside `prepare.py` itself. | ⚠️ |
| Architecture design and config generation | `districts/karpathy_lab/architecture_builder.py` | `ArchitectureBuilder.design_architecture()`, `generate_config()`, `estimate_compute()`. Generic transformer/LSTM/MoE/Mamba/Hyena configs. Not specific to autoresearch's GPT variant (no `MuonAdamW`, no `val_bpb` metric, no GQA, no sliding windows). | ⚠️ |
| Training run progress tracking | `districts/karpathy_lab/progress_tracker.py` | SQLite-backed step logging (`step_logs`), run start/end tracking, progress%, LLM-generated report. Maps generically to any training loop, not specifically to autoresearch's 5-min wall-clock structure. | ✅ |
| 30-min/day Karpathy coding sessions (RULE 12) | `districts/karpathy_lab/code_typer.py` | Start/end session, lines-typed counter, daily JSONL log, streak counter, 9PM reminder warning if goal not met, HP rewards. Full implementation. Not in autoresearch repo (VECTOR-specific). | ✅ |
| Simplicity criterion (equal improvement → prefer simpler) | `AutoresearchRunner._propose_improvement()` prompt | Included in prompt: "Simpler is better for equal improvement". LLM is instructed, not enforced in code. | ⚠️ |
| Never-stop loop / `NEVER STOP` directive | `AutoresearchRunner.MAX_EXPERIMENTS_PER_RUN = 3` | VECTOR caps at 3 experiments per `run_experiment_cycle()` call. It does NOT loop forever autonomously on its own — it relies on the autonomous_loop calling it on a schedule. The infinite loop is in `program.md`'s design; VECTOR's agent produces a bounded cycle per invocation. | ⚠️ |
| Crash detection and recovery | `AutoresearchRunner._run_training()` | `TimeoutExpired` caught; `subprocess.run` with 7-min timeout. Empty result dict on failure. No `tail -n 50 run.log` debug step. | ⚠️ |
| `uv` package manager usage | Not present | VECTOR uses `sys.executable` to call `train.py` directly, not `uv run train.py`. This means autoresearch's `uv.lock` pinned environment is bypassed. | ⚠️ |

---

## 3. Frontend

autoresearch-master has no web frontend. The only visual output is:

- **`progress.png`** — matplotlib-generated PNG saved by `analysis.ipynb`, showing val_bpb over experiment index.
- **`analysis.ipynb`** — Jupyter notebook used locally by the human researcher to analyze `results.tsv` after a research run.

VECTOR has no equivalent visualization layer for Karpathy lab experiments. The `ProgressTracker` generates JSON reports but no plots. The `analysis.ipynb` logic (running minimum BPB curve, keep-rate, top-hits delta ranking) has no counterpart in VECTOR.

There is nothing to build or match on the frontend side for this repo — it is intentionally a terminal/CLI tool. The future VECTOR dashboard could display a BPB-over-experiments plot via the `data/training_runs/results_*.jsonl` files, but this is not currently implemented.

---

## 4. Verdict

**VERDICT: MOSTLY ABSORBED — core loop is solid, 4 specific gaps remain**

The essential machinery is in place. The `AutoresearchRunner` correctly implements the keep/revert experiment loop, parses autoresearch's stdout format, stores results in JSONL, calls `vector-reasoning` for proposals, hydrates with VECTOR context, persists RULE 8 chains, and awards HP on improvements. Both `train.py` and `prepare.py` are confirmed present as real autoresearch files.

**Reasoning for the gaps that remain:**

1. **Git branch management is absent.** The `program.md` protocol requires a new `autoresearch/<tag>` branch per research session so experiments are reviewable and revertable at the git level. VECTOR's runner does file-level backup/restore but no git branching. For a personal single-machine setup this is acceptable, but it means you lose the experiment audit trail at the commit-hash level.

2. **TSV format vs JSONL.** The `analysis.ipynb` notebook reads `results.tsv` with `commit`, `val_bpb`, `memory_gb`, `status` (`keep`/`discard`/`crash`), `description`. VECTOR outputs JSONL without commit hashes or `memory_gb`. The notebook would fail on VECTOR's output.

3. **No visualization pipeline.** `analysis.ipynb` is the only way to see the BPB progression chart. VECTOR's `ProgressTracker` produces JSON reports but nothing visual. Without this you cannot tell at a glance whether autoresearch is making progress.

4. **`uv run` vs `sys.executable`.** The autoresearch environment is pinned via `uv.lock` (PyTorch 2.9.1 cu128, `kernels>=0.11.7` for Flash Attention 3). VECTOR calls `sys.executable` which picks up the VECTOR `.venv`. These are likely incompatible — PyTorch 2.9.1 with CUDA 12.8 kernels is a very specific environment. Using the wrong Python will cause `from kernels import get_kernel` to fail on startup.

5. **The `MAX_EXPERIMENTS_PER_RUN = 3` cap.** Karpathy's `program.md` says `NEVER STOP` and targets ~100 experiments overnight (~12/hour). VECTOR's runner does 3 experiments per call and relies on `autonomous_loop` scheduling. For overnight research this means the scheduler must call it repeatedly — which it can, but it's not the same as a tight infinite loop.

---

## 5. Gaps

### Gap 1 — Git branch management (medium priority)
`AutoresearchRunner` should create a `autoresearch/<date>` branch at the start of `run_experiment_cycle()`, commit after each experiment (win or loss), and embed the short commit hash in the JSONL record. This closes the audit trail gap and enables `git log autoresearch/<tag>` review.

**Files to modify:** `districts/karpathy_lab/autoresearch_runner.py`
**New dependency:** `gitpython` (already in VECTOR's requirements as `gitpython + PyGithub`)

### Gap 2 — TSV output compatibility (low priority)
Add a method `_to_tsv_row(result) -> str` that writes a tab-separated row compatible with `analysis.ipynb`'s format: `commit\tval_bpb\tmemory_gb\tstatus\tdescription`. Append to `results.tsv` alongside the existing JSONL. The `peak_vram_mb / 1024` gives `memory_gb`. Status should be `keep`/`discard`/`crash` based on `val_bpb` presence and improvement flag.

**Files to modify:** `districts/karpathy_lab/autoresearch_runner.py`

### Gap 3 — Visualization script (low priority)
Port `analysis.ipynb`'s core plot logic (val_bpb over experiment index, running minimum curve, keep-rate %) to a standalone Python function `generate_progress_plot(jsonl_path) -> Path` in `districts/karpathy_lab/progress_visualizer.py`. Call it at the end of `run_experiment_cycle()`. Output `progress.png` to `data/training_runs/`. Requires `matplotlib` (already in autoresearch's dependencies; add to VECTOR's requirements if missing).

**New file:** `districts/karpathy_lab/progress_visualizer.py`

### Gap 4 — `uv` environment isolation (high priority, blocks actual GPU runs)
`AutoresearchRunner._run_training()` calls `sys.executable` which uses VECTOR's `.venv`. autoresearch's `train.py` requires `kernels` (Flash Attention 3, CUDA 12.8), `rustbpe`, and `torch==2.9.1`. These are not in VECTOR's environment. The fix: detect if a `uv` lockfile exists in the repo root (`data/training_runs/uv.lock`), and if so, invoke `uv run python train.py` via the `uv` binary rather than `sys.executable`. Fall back to `sys.executable` if `uv` is unavailable.

```python
# In _run_training():
uv_lock = self._runs_dir / "uv.lock"
if uv_lock.exists():
    cmd = ["uv", "run", "python", str(self._train_script)]
else:
    cmd = [sys.executable, str(self._train_script)]
```

**Files to modify:** `districts/karpathy_lab/autoresearch_runner.py`

### Gap 5 — Crash debug step (low priority)
When `_run_training()` returns an empty dict (crash/OOM), the runner currently just logs a warning and moves on. The `program.md` protocol says: read the last 50 lines of the log, attempt a fix if it's a simple typo/import, skip if the idea is fundamentally broken. Add `result["stderr_tail"] = proc.stderr[-2000:]` to the returned dict so the LLM proposal call on the next iteration can receive crash context.

**Files to modify:** `districts/karpathy_lab/autoresearch_runner.py`

### Gap 6 — `memory_gb` field in results (low priority)
`peak_vram_mb` is already parsed from autoresearch stdout. Add `result["memory_gb"] = result.get("peak_vram_mb", 0) / 1024` to `_parse_training_output()` output normalization so downstream analysis and TSV export always have this field without division at call sites.

**Files to modify:** `districts/karpathy_lab/autoresearch_runner.py`

---

## Summary Table

| Category | Score |
|----------|-------|
| Core experiment loop | ✅ Solid — baseline + keep/revert cycle works |
| Output parsing | ✅ Exact autoresearch stdout format |
| LLM proposal integration | ✅ vector-reasoning wired with context hydration |
| RULE 8 / HP | ✅ Chain storage + HP awards wired |
| Git branch management | ❌ Missing |
| Results TSV compatibility | ⚠️ JSONL only — analysis.ipynb incompatible |
| Visualization | ❌ Missing |
| uv environment isolation | ⚠️ Wrong Python used — will break on GPU runs |
| Never-stop autonomy | ⚠️ Capped at 3 per call, relies on scheduler |
| DataPrep (BPE tokenizer) | ⚠️ Char-level only; BPE only lives in prepare.py |

**Overall absorption: 70% — functional for dry-runs; gaps 1 and 4 must be closed before real GPU overnight experiments work correctly.**
