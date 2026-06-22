# Post-Training Pipeline Implementation Plan

**Goal:** Close the loop "VECTOR reasons → stores reasoning_chains → trains its own aligned LoRA adapter on them" — absorb train-llm-from-scratch's post-training half (SFT + DPO; GRPO optional/deferred) at LoRA scale for a single 12GB RTX 5070 Ti, fed from `reasoning_memory.py` and `counterfactual.py`, gated off by default and run overnight/weekly.

**Architecture:** Two new dataset-adapter functions convert VECTOR's existing memory tables into training-ready examples (no new DB writes — pure read + transform). Two new trainer wrappers (SFT, DPO) reuse the existing `AdapterConfig`/`TrainingArgs` pydantic models from `core/training/training_config.py` and follow `LoRATrainer`'s own established pattern: try the real library (`peft`+`transformers` for SFT, `trl.DPOTrainer` for DPO), fall back to a `_simulate_training`-style stub when the library is absent — never crash, never silently fake success without saying so. A single new weekly cron job (gated by a CONFIG flag, default OFF) runs the adapter-build → train → export pipeline overnight. GRPO is scoped but marked optional/deferred — it needs multi-sample group generation infra that SFT/DPO don't, and the source analysis doc itself ranks it below SFT/DPO in value.

**Owner action items this plan surfaces (not code — flag, don't silently skip):**
- `pip install peft trl` — neither is installed today. Without them, `LoRATrainer` *already* silently simulates instead of training (confirmed: `torch`+`transformers` are installed, `peft`/`trl`/`unsloth`/`bitsandbytes` are not). This plan's new DPO trainer has the same dependency.
- Decide whether to enable `CONFIG["training"]["post_training_enabled"]` (default `False`) — this plan ships it off; turning it on is a deliberate owner choice, not a silent default flip.
- The actual overnight training run itself (multi-hour, even at LoRA scale) is something the owner schedules/watches, not something this plan auto-runs during implementation.

**Key design notes (read before implementing — these are non-obvious):**
1. **`counterfactual.py`'s `decision_id` is actually `action_type`** (a generic string like `"code_review"`, `"deploy"`), not a unique per-decision ID — confirmed by reading all 3 real call sites (`autonomous_loop.py:279,952`, `permission_gateway.py:227`). There is **no clean 1:1 "this exact proposal was rejected, here's the exact alternative that was accepted instead" pairing** in the data as it exists today. DPO pairs must be **approximated**: for a given `action_type`, pair a rejected `proposal` (from `rejections`) against a same-`action_type`, high-reward (`reward > 0.7`) chain's `action_taken` (from `reasoning_chains`) as the "chosen" completion. This is a reasonable approximation (same action category, contrastive reward signal) but is **not** a strict causal pair — document this in the adapter's docstring so nobody mistakes it for ground-truth contrastive data later.
2. **`counterfactual.py` uses its own private SQLite file** (`data/counterfactual.db`, plain `sqlite3.connect()`, not `episodic.get_db_connection()`) — this is the module's existing, deliberate design (its own lock, own pragmas), not a violation to "fix." The dataset adapter reads through `CounterfactualMemory`'s own public methods (`get_all_scenarios`, or a new lightweight read method — see Task 2), never opens the file directly.
3. **Reuse `LoRATrainer`'s exact graceful-degradation convention** (`core/training/lora_trainer.py:29-43`): try `transformers`+`peft` → try `unsloth` → simulate. The new DPO trainer mirrors this with `trl.DPOTrainer` as the "real" path.
4. **`AdapterConfig`/`TrainingArgs` already exist** (`core/training/training_config.py`) and are reused as-is — no new config dataclasses for hyperparameters.
5. Recommending **`trl` over hand-rolled DPO loss** — the source repo (train-llm-from-scratch) deliberately avoids `trl`/`peft` for *pedagogical* reasons (it's a learning repo). VECTOR's own `lora_trainer.py` already uses `peft` when available; matching that house convention (real library when present, simulate when absent) is far less code and far more battle-tested than re-deriving the DPO loss by hand. If the owner specifically wants zero new deps, Task 4 documents the hand-rolled fallback path as an alternative, but the recommended default is `trl`.

**Files:**
- Create: `core/training/reasoning_chain_dataset.py` — SFT + DPO dataset adapters.
- Create: `core/training/post_training/__init__.py`
- Create: `core/training/post_training/sft_trainer.py` — thin SFT wrapper (delegates to `LoRATrainer`, adds the dataset-shape contract).
- Create: `core/training/post_training/dpo_trainer.py` — DPO trainer (trl-or-simulate).
- Create: `core/training/post_training/grpo_trainer.py` — GRPO trainer, **optional/deferred task**, scoped but not required for this plan to be "done."
- Modify: `core/config.py` — add `TrainingPostConfig` (or extend existing training config) with `post_training_enabled: bool = False`, `post_training_min_chain_reward: float = 0.7`, `post_training_min_examples: int = 50`, `post_training_base_model: str`.
- Modify: `core/loop/cron_jobs.py` — add `job_post_training_run()` + one entry in `register_default_jobs()`'s `jobs` list (Saturday 04:00, off-peak — matches the existing `weekly-*` slot convention).
- Create: `tests/test_reasoning_chain_dataset.py`
- Create: `tests/test_post_training_sft.py`
- Create: `tests/test_post_training_dpo.py`
- Create: `tests/test_post_training_cron_wiring.py`

---

### Task 1: SFT dataset adapter — reasoning_chains → instruction pairs

- [ ] Write failing test
  ```python
  # tests/test_reasoning_chain_dataset.py
  def test_chains_to_sft_examples_filters_by_reward_threshold(monkeypatch):
      from core.training.reasoning_chain_dataset import chains_to_sft_examples

      class _FakeReasoningMemory:
          def get_training_data(self, limit=1000):
              return [
                  {"situation": "deploy failing", "steps": ["check logs", "rollback"],
                   "action_taken": "rollback", "outcome": "service restored", "reward": 0.9},
                  {"situation": "low confidence task", "steps": [], "action_taken": "defer",
                   "outcome": "ok", "reward": 0.5},  # below threshold — must be excluded
              ]
      monkeypatch.setattr(
          "core.training.reasoning_chain_dataset.ReasoningMemory",
          lambda: _FakeReasoningMemory(),
      )
      examples = chains_to_sft_examples(min_reward=0.7)
      assert len(examples) == 1
      assert examples[0]["reward"] == 0.9
      assert "instruction" in examples[0] and "response" in examples[0]
  ```
- [ ] Run: `PYTHONUTF8=1 pytest tests/test_reasoning_chain_dataset.py::test_chains_to_sft_examples_filters_by_reward_threshold -v` → expect FAIL (module doesn't exist yet)
- [ ] Implement `core/training/reasoning_chain_dataset.py::chains_to_sft_examples(min_reward=0.7, limit=1000) -> list[dict]`:
  - Calls `ReasoningMemory().get_training_data(limit=limit)` — **confirmed** (`core/memory/reasoning_memory.py:142-147`) this already filters server-side to `is_training_data=1` (which is set whenever `reward > 0.7` at insert time). `chains_to_sft_examples`'s own `min_reward` kwarg is a redundant client-side safety filter on top (useful if the server-side threshold ever changes, or for a stricter cutoff in a specific training run) — apply it via `[c for c in chains if c["reward"] >= min_reward]`, don't assume it's pre-filtered to *your* exact threshold.
  - Maps each chain to `{"instruction": situation, "response": f"{action_taken}\n\nOutcome: {outcome}", "reward": reward, "chain_id": id}`.
  - Returns `[]` gracefully on any exception (log at `warning`, never raise — this is a batch job input, not a request path).
- [ ] Run the test → expect PASS
- [ ] Add a second test: empty `reasoning_chains` table → `chains_to_sft_examples()` returns `[]`, not an exception.
- [ ] Commit: `git commit -m "feat(training): SFT dataset adapter from reasoning_chains"`

### Task 2: DPO dataset adapter — counterfactual rejections + reasoning_chains → preference pairs

- [ ] Write failing test
  ```python
  def test_build_dpo_pairs_matches_rejection_to_same_action_type_high_reward_chain(monkeypatch):
      from core.training.reasoning_chain_dataset import build_dpo_pairs

      class _FakeCounterfactual:
          def get_all_scenarios(self, limit=50):
              return []
          # New lightweight method this task adds to CounterfactualMemory:
          def get_all_rejections(self, limit=200):
              return [{"decision_id": "deploy", "proposal": "deploy untested", "reason": "no tests run"}]

      class _FakeReasoningMemory:
          def get_training_data(self, limit=1000):
              return [{"situation": "deploy ready", "action_taken": "deploy after tests pass",
                        "outcome": "ok", "reward": 0.85}]

      monkeypatch.setattr("core.training.reasoning_chain_dataset.CounterfactualMemory", lambda: _FakeCounterfactual())
      monkeypatch.setattr("core.training.reasoning_chain_dataset.ReasoningMemory", lambda: _FakeReasoningMemory())

      pairs = build_dpo_pairs()
      assert len(pairs) == 1
      assert pairs[0]["rejected"] == "deploy untested"
      assert "deploy after tests pass" in pairs[0]["chosen"]
  ```
- [ ] Run → expect FAIL
- [ ] Add `CounterfactualMemory.get_all_rejections(limit=200) -> list[dict]` to `core/memory/counterfactual.py` (a plain `SELECT * FROM rejections ORDER BY created_at DESC LIMIT ?` through the existing `self._conn` — same pattern as `get_all_scenarios` at line 301; this is the one small addition to an existing file this plan needs).
  - [ ] Write its own failing test first in the *existing* counterfactual test file (find it via `grep -rl CounterfactualMemory tests/`), then implement, then pass — same TDD discipline, just inside an existing module.
- [ ] Implement `build_dpo_pairs(min_reward=0.7, action_type_match=True) -> list[dict]` in `reasoning_chain_dataset.py`:
  - Pulls rejections via `CounterfactualMemory().get_all_rejections()`.
  - Pulls high-reward chains via `ReasoningMemory().get_training_data()`.
  - For each rejection, find chains whose `action_taken` text shares the rejection's `decision_id` as a keyword (simple substring/keyword match — this is the approximation from the design notes above, not exact pairing).
  - Emits `{"prompt": <shared context if derivable, else decision_id>, "chosen": chain["action_taken"], "rejected": rejection["proposal"]}`.
  - Skips rejections with no matching high-reward chain (no pair possible) — log at `debug`, don't fabricate a chosen completion.
- [ ] Run → expect PASS
- [ ] Commit: `git commit -m "feat(training): DPO preference-pair adapter from counterfactual + reasoning_chains"`

### Task 3: SFT post-trainer wrapper

- [ ] Write failing test
  ```python
  # tests/test_post_training_sft.py
  def test_run_sft_simulates_when_peft_unavailable(monkeypatch):
      from core.training.post_training.sft_trainer import run_sft

      monkeypatch.setattr(
          "core.training.reasoning_chain_dataset.chains_to_sft_examples",
          lambda **kw: [{"instruction": "x", "response": "y", "reward": 0.9}],
      )
      result = run_sft(adapter_name="test-adapter", base_model="dummy/model")
      # LoRATrainer.train()'s real statuses (core/training/lora_trainer.py:101,112,167-185):
      # "success" for BOTH the real-PEFT path and the simulated path — they're
      # distinguished by the "method" field ("peft"/"unsloth"/"simulated"), not
      # status — or "failed". run_sft's own pre-check adds "skipped" for too little data.
      assert result["status"] in ("success", "failed", "skipped")
      assert "adapter" in result
  ```
- [ ] Run → expect FAIL
- [ ] Implement `core/training/post_training/sft_trainer.py::run_sft(adapter_name, base_model, min_reward=0.7, min_examples=50) -> dict`:
  - Calls `chains_to_sft_examples(min_reward=min_reward)`.
  - If `len(examples) < min_examples`: return `{"status": "skipped", "reason": "insufficient_data", "count": len(examples)}` — never train on too little data.
  - Maps examples to the `{"text": f"### Instruction:\n{instruction}\n\n### Response:\n{response}"}` shape `LoRATrainer.train()` already expects (confirmed in `lora_trainer.py:69`: `texts = [ex.get("text", "") for ex in dataset if ex.get("text")]`).
  - Builds `AdapterConfig(name=adapter_name, base_model=base_model, target_modules=["q_proj","v_proj"])` and a default `TrainingArgs()`.
  - Delegates to `LoRATrainer().train(adapter_config, training_args, dataset)` — **do not reimplement the PEFT loop**, `LoRATrainer` already has it.
- [ ] Run → expect PASS
- [ ] Add a `min_examples` gate test: fewer than 50 examples → `status == "skipped"`, `LoRATrainer.train` never called (assert via a monkeypatched spy).
- [ ] Commit: `git commit -m "feat(training): SFT post-trainer wrapper over LoRATrainer"`

### Task 4: DPO trainer (trl-or-simulate)

- [ ] Write failing test
  ```python
  # tests/test_post_training_dpo.py
  def test_run_dpo_simulates_when_trl_unavailable(monkeypatch):
      from core.training.post_training.dpo_trainer import run_dpo

      monkeypatch.setattr(
          "core.training.reasoning_chain_dataset.build_dpo_pairs",
          lambda **kw: [{"prompt": "p", "chosen": "c", "rejected": "r"}] * 10,
      )
      result = run_dpo(adapter_name="test-dpo", base_model="dummy/model", min_pairs=5)
      # New module — choose its own status vocabulary deliberately (it does
      # NOT delegate to LoRATrainer, so it isn't bound to "success"/"failed"):
      # "simulated" when trl is absent, "ok" when a real trl run completes,
      # "skipped" for insufficient pairs, "failed" on a real run that errors.
      assert result["status"] in ("simulated", "ok", "failed", "skipped")
  ```
- [ ] Run → expect FAIL
- [ ] Implement `core/training/post_training/dpo_trainer.py::run_dpo(adapter_name, base_model, min_pairs=20) -> dict`:
  - Calls `build_dpo_pairs()`; if `len(pairs) < min_pairs` → `{"status": "skipped", "reason": "insufficient_pairs"}`.
  - Try path: `import trl, peft` → build a `trl.DPOConfig` + `trl.DPOTrainer` using the same `AdapterConfig`/`TrainingArgs` fields for LR/epochs/rank, fit on the pairs.
  - Except `ImportError` → `_simulate_dpo(pairs, adapter_name)`: writes a `data/adapters/{adapter_name}/dpo_simulated.json` manifest (pair count, timestamp) and returns `{"status": "simulated", "pairs": len(pairs), "adapter": adapter_name}` — mirrors `LoRATrainer._simulate_training`'s contract exactly (check that method's return shape at `core/training/lora_trainer.py` and match its keys).
- [ ] Run → expect PASS
- [ ] Commit: `git commit -m "feat(training): DPO trainer (trl, simulated fallback)"`

### Task 5 (optional/deferred): GRPO trainer

- [ ] Scope only — do not implement unless Tasks 1-4 are done and there's remaining budget. GRPO needs: (a) a verifiable-reward signal per completion (VECTOR has `policy.py`'s EMA score + HP deltas — these are plausible reward signals, but mapping them to GRPO's "group of N completions, rank within group" shape needs its own dataset adapter, not a reuse of `chains_to_sft_examples`/`build_dpo_pairs`), (b) multi-sample generation at train time (sample N completions per prompt from the current policy, not just replay stored pairs). This is meaningfully more infrastructure than SFT/DPO and the source analysis doc itself doesn't rate it above "moderate value." Recommend treating this as a **separate, later plan** once SFT+DPO are running and proving value, rather than bundling it into this one.

### Task 6: Export wiring

- [ ] Write failing test
  ```python
  # add to tests/test_post_training_sft.py
  def test_run_sft_with_export_calls_ollama_exporter(monkeypatch, tmp_path):
      from core.training.post_training.sft_trainer import run_sft
      # ... monkeypatch chains_to_sft_examples to return >= min_examples,
      # monkeypatch LoRATrainer.train to return
      #   {"status": "success", "method": "peft", "save_path": str(tmp_path)},
      # monkeypatch OllamaExporter.export_model_weights as a spy,
      # assert it was called with src_path=that save_path when export=True.

  def test_run_sft_with_export_skips_export_when_simulated(monkeypatch):
      # LoRATrainer's simulated path's result dict has NO "save_path" key at all
      # (core/training/lora_trainer.py:175-185) — confirm export is skipped
      # gracefully (not a KeyError) when method == "simulated".
      ...
  ```
- [ ] Run both → expect FAIL
- [ ] Add an `export: bool = False` kwarg to `run_sft`/`run_dpo`; on `status == "success"` (SFT) / the real-trl success status (DPO) **and** `result.get("save_path")` present, call `OllamaExporter().export_model_weights(src_path=result["save_path"], model_name=adapter_name)` then `create_modelfile(...)`. When `save_path` is absent (the simulated path never sets it), skip export and note `"export": "skipped_no_save_path"` in the returned dict rather than raising `KeyError`. Reuse `core/training/openmythos/export_to_ollama.py` as-is, no modifications needed there.
- [ ] Run → expect PASS
- [ ] Commit: `git commit -m "feat(training): wire post-training export to OllamaExporter"`

### Task 7: Config flag + weekly cron job (gated off by default)

- [ ] Write failing test
  ```python
  # tests/test_post_training_cron_wiring.py
  def test_post_training_disabled_by_default():
      from core.config import CONFIG
      assert CONFIG["training"]["post_training_enabled"] is False

  async def test_job_post_training_run_skips_when_disabled(monkeypatch):
      from core.loop.cron_jobs import job_post_training_run
      from core.config import CONFIG
      monkeypatch.setitem(CONFIG["training"], "post_training_enabled", False)
      result = await job_post_training_run()
      assert result["status"] == "disabled"

  def test_post_training_job_registered_in_default_jobs():
      import inspect
      from core.loop import cron_jobs
      src = inspect.getsource(cron_jobs.register_default_jobs)
      assert "job_post_training_run" in src
  ```
- [ ] Run → expect FAIL
- [ ] Add `post_training_enabled: bool = False` (+ the 3 other fields from the Files section) to whichever pydantic config class holds training settings in `core/config.py` (check for an existing `TrainingConfig`-style class first — reuse it rather than creating a parallel one if one already exists for `core/training/`).
- [ ] Implement `core/loop/cron_jobs.py::job_post_training_run(*, _ctx=None) -> dict`:
  - If `not CONFIG["training"]["post_training_enabled"]` → `{"status": "disabled"}` immediately, no imports of torch/transformers triggered at all (cheap no-op when off).
  - Else: call `run_sft(...)` then `run_dpo(...)` with config-driven adapter names/base model, log a summary, store one `episodic.store(event_type="post_training_run", ...)` row via `core.memory.episodic.get_db_connection()` so the run shows up in the same audit trail as other scheduled jobs (matches the established convention from this session's earlier `scheduler_job_run` event pattern).
- [ ] Add `("weekly-post-training", "weekly", "0 4 * * 6", job_post_training_run)` to the `jobs` list in `register_default_jobs()` (Saturday 04:00 — off-peak, mirrors the existing weekly-* slots' timing convention).
- [ ] Run → expect PASS
- [ ] Run the full existing cron test suite to confirm no regression: `PYTHONUTF8=1 pytest tests/ -k cron -v`
- [ ] Commit: `git commit -m "feat(training): gate post-training behind config flag, wire weekly cron job"`

### Task 8: End-to-end verification

- [ ] Run all new tests together: `PYTHONUTF8=1 pytest tests/test_reasoning_chain_dataset.py tests/test_post_training_sft.py tests/test_post_training_dpo.py tests/test_post_training_cron_wiring.py -v` → all PASS
- [ ] Run `python scripts/smoke_test.py` and `python scripts/integration_check.py` → both still 38/38 and 51/51 (no regression)
- [ ] Manual check (no owner GPU time spent): with `post_training_enabled=False` (the shipped default), confirm `python run_vector.py loop` boots clean and the new job registers but never fires real training — only verify via the registered-jobs log line, do not flip the flag during this verification pass.
- [ ] Report to owner: dependency gap (`pip install peft trl` to activate real training instead of the simulated-but-real-pipeline path), the flag name to flip when ready, and the DPO-pairing approximation caveat from the design notes (so they don't mistake simulated/approximated data for ground truth when reviewing results later).

---

## Done = Tasks 1-4, 6-7 complete and Task 8's verification green. Task 5 (GRPO) is explicitly out of scope for "done" — track separately.
