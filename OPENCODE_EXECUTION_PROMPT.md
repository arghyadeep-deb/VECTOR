# OpenCode Prompt: Execute Intent Classification Verification + Phase 2 Training

## Context

I've implemented a 2-phase intent classification system for VECTOR's governor:
- **Phase 1** (embedding similarity) — code complete, needs verification
- **Phase 2** (BERT classifier) — code complete, needs training

All files are created. You need to run verification, then train Phase 2.

---

## Step 1: Verify Phase 1 Works

Run these commands in order and report results:

```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

# 1.1 Test intent matcher standalone
python core/city/intent_matcher.py

# Expected: Should load 304 examples, embed 5 test queries, show matches
# If it fails: Check Ollama is running (ollama list should show nomic-embed-text)

# 1.2 Run calibration
python scripts/calibrate_intent_threshold.py

# Expected: Should show accuracy at different thresholds (0.80-0.90)
# Goal: 90-95% accuracy at threshold 0.85
# Report: What accuracy did we get? Which threshold is best?

# 1.3 Run unit tests
pytest tests/test_intent_matcher.py -v

# Expected: All 8 tests pass
# If failures: Report which tests failed and why

# 1.4 Integration test (verify no regression)
python scripts/diag_tier6.py

# Expected: 9/10 or better (same as before Phase 1)
# Report: Did accuracy improve, stay same, or regress?
```

**Report back:**
- Did Phase 1 verification pass?
- What accuracy did we get?
- Any errors or issues?

---

## Step 2: Build Golden Dataset (Phase 2)

If Phase 1 verification passes, proceed:

```bash
# 2.1 Build golden dataset
python scripts/build_golden_dataset.py

# Expected: Should create data/golden_intent_dataset.jsonl with 500+ examples
# Report: How many examples were created? How many districts covered?
```

**If build_golden_dataset.py fails:**
- Check if deepeval_report.json exists in repo root
- Check if data/intent_examples.json exists (should be there from Phase 1)
- Check if core/brain/goal_system.py exists and has PRESEEDED_GOALS
- Report the error

---

## Step 3: Train BERT Classifier (Phase 2)

If golden dataset builds successfully:

```bash
# 3.1 Train BERT model
python core/city/intent_bert.py --train --dataset data/golden_intent_dataset.jsonl

# Expected:
# - Loads 500+ examples
# - Shows 150+ unique labels
# - Trains for 3 epochs (1-2 hours on RTX 5070 Ti)
# - Saves model to models/intent_bert.pt
# Report: Training time, final loss, model size
```

**If training fails:**
- Check PyTorch is installed (python -c "import torch; print(torch.cuda.is_available())")
- Check transformers is installed (pip list | grep transformers)
- Check GPU memory (nvidia-smi)
- Report the error

---

## Step 4: Evaluate BERT Model

After training completes:

```bash
# 4.1 Evaluate accuracy
python core/city/intent_bert.py --evaluate --dataset data/golden_intent_dataset.jsonl

# Expected: 95-96% accuracy
# Report: What accuracy did we get?
```

**If evaluation fails:**
- Check if models/intent_bert.pt exists
- Report the error

---

## Step 5: Integrate BERT into Governor (Optional)

If BERT achieves 95%+ accuracy, integrate it:

**Edit `core/city/governor.py`**, find the embedding matcher section (around line 1430), and add after it:

```python
# Stage 3: BERT classifier (after embedding similarity, before LLM)
try:
    from core.city.intent_bert import IntentBERT
    if not hasattr(classify_chat_intent, "_bert"):
        classify_chat_intent._bert = IntentBERT("models/intent_bert.pt")
    bert_result = await classify_chat_intent._bert.classify(text)
    if bert_result and bert_result["confidence"] > 0.7:
        _debug_classify_intent(text, "", f"BERT_MATCH -> {bert_result['district']}/{bert_result['type']} (conf={bert_result['confidence']:.3f})")
        return bert_result
except Exception as e:
    logger.warning(f"[governor] BERT classifier failed, falling through to LLM: {e}")
```

Then test integration:
```bash
python scripts/diag_tier6.py

# Expected: 10/10 (improvement from 9/10)
# Report: Did accuracy improve?
```

---

## Step 6: Final Report

Provide a summary:

```
=== INTENT CLASSIFICATION EXECUTION REPORT ===

Phase 1 (Embedding Similarity):
- Intent matcher test: PASS/FAIL
- Calibration accuracy: X%
- Unit tests: X/8 passed
- Integration test: X/10 correct

Phase 2 (BERT Classifier):
- Golden dataset: X examples, Y districts covered
- Training time: X hours
- Final loss: X.XXXX
- Evaluation accuracy: X%
- Integration test (if done): X/10 correct

Overall:
- Before: 93% accuracy (14/15), 3-12s latency
- After Phase 1: X% accuracy, 100-300ms latency
- After Phase 2: X% accuracy, <50ms latency

Status: SUCCESS/PARTIAL/FAILED
Issues: (list any problems encountered)
```

---

## Troubleshooting

**If Ollama embedding fails:**
```bash
# Check Ollama is running
ollama list

# Check nomic-embed-text is installed
ollama pull nomic-embed-text

# Test embedding manually
curl http://127.0.0.1:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"test"}'
```

**If PyTorch/CUDA issues:**
```bash
# Check CUDA availability
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# Check GPU memory
nvidia-smi
```

**If transformers not installed:**
```bash
pip install transformers
```

---

## Files Reference

**Phase 1 files:**
- `data/intent_examples.json` (304 examples)
- `core/city/intent_matcher.py` (embedding matcher)
- `core/city/governor.py` (modified, lines 1422-1433)
- `core/config.py` (modified, lines 1152-1158)
- `tests/test_intent_matcher.py` (unit tests)
- `scripts/calibrate_intent_threshold.py` (calibration)

**Phase 2 files:**
- `scripts/build_golden_dataset.py` (dataset builder)
- `core/city/intent_bert.py` (BERT classifier)

**Documentation:**
- `INTENT_CLASSIFICATION_COMPLETE.md` (full checklist)
- `docs/intent_classification_implementation.md` (architecture guide)

---

## Success Criteria

**Phase 1 Success:**
- ✅ Intent matcher loads 304 examples
- ✅ Calibration shows 90-95% accuracy
- ✅ Unit tests pass (8/8)
- ✅ Integration test: 9/10 or better

**Phase 2 Success:**
- ✅ Golden dataset: 500+ examples
- ✅ BERT training completes (1-2 hours)
- ✅ Evaluation: 95-96% accuracy
- ✅ (Optional) Integration: 10/10

**Overall Success:**
- VECTOR governor now uses 3-stage pipeline: regex → embedding → BERT → LLM
- Accuracy improved from 93% to 95-96%
- Latency reduced from 3-12s to <50ms

---

## Execute Now

Start with Step 1 and work through sequentially. Report results after each step. If anything fails, troubleshoot and report the error. Don't skip steps.

**Begin execution.**
