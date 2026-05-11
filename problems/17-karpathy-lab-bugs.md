# Problem 17 — Karpathy Lab Bugs

**Severity: HIGH (data_prep) / MEDIUM (progress_tracker, openmythos)**
**Status: data_prep FIXED; progress_tracker FIXED; openmythos DOCUMENTED**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Part A — DataPrep Destroys Multilingual Training Data (FIXED)

### Symptom

`DataPrep.preprocess_data()` stripped ALL non-ASCII characters:

```python
line = re.sub(r'[^\x00-\x7F]+', '', line)
```

For a multilingual project training on Hindi, Bengali, Assamese, and
Japanese text, this silently removed all Devanagari (हिंदी), Bengali
(বাংলা), Assamese (অসমীয়া), and Japanese (日本語) characters from
every training file. The custom LLM pipeline would train on ASCII-only
data, producing a model with zero multilingual capability.

### Fix Applied

`agents/districts/karpathy_lab/data_prep.py`:

```python
# Before — destroys all non-ASCII (Hindi, Bengali, Assamese, Japanese gone)
line = re.sub(r'[^\x00-\x7F]+', '', line)

# After — strips only ASCII control characters, preserves all Unicode
line = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', line)
```

Strips: null bytes, backspace, vertical tab, form feed, ESC, DEL, and other
control characters. Preserves: all Unicode including the 4 VECTOR languages.

---

## Part B — progress_tracker SQL Bug + Missing run_name Filter (FIXED)

### Symptom 1

`log_step()` INSERT was missing the `run_name` column despite the schema
having it:

```sql
-- Before (broken)
INSERT INTO step_logs (step, metrics, timestamp) VALUES (?, ?, ?)
-- step_logs has run_name column but it was never set → all NULL
```

```sql
-- After (fixed)
INSERT INTO step_logs (run_name, step, metrics, timestamp) VALUES (?, ?, ?, ?)
```

### Symptom 2

`get_progress()` queried for the most recent step globally instead of for
the specific run being queried:

```sql
-- Before (wrong — returns max step across ALL runs)
WHERE step = (SELECT MAX(step) FROM step_logs)

-- After (correct — filters by run_name)
WHERE run_name = ? ORDER BY step DESC LIMIT 1
```

### Changes Applied

- Added `self._current_run: str | None` to `__init__`
- `start_run()` sets `self._current_run = run_name`
- `log_step(step, metrics, run_name=None)` — `run_name` now optional parameter
  defaulting to `self._current_run`
- `runs_dir` now reads from `CONFIG.get("karpathy", {}).get("runs_dir", ...)`
  instead of hardcoded `"./data/training_runs"`

---

## Part C — OpenMythos train.py Is Simulation Not Real Fine-Tuning (DOCUMENTED)

### Symptom

`integrations/openmythos/train.py` exists (satisfying the "verify train.py
exists" spec check) but its `train()` loop does not update model weights.
It iterates training examples, calls `client.generate()` on each, and
discards the response. No gradient updates. No LoRA. No unsloth.

### Fix Required (Month 2)

Replace with actual LoRA fine-tuning using unsloth:

```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained("unsloth/Qwen2.5-4B")
model = FastLanguageModel.get_peft_model(model, r=16, ...)
trainer = SFTTrainer(model=model, dataset=dataset, ...)
trainer.train()
model.save_pretrained("models/vector-chairman-lora")
```

Then export via `export_to_ollama.py` (already exists).

The current simulation is acceptable for Month 1 (infrastructure scaffolding)
but must be replaced before Month 2 LoRA training milestone.
