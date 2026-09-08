# OpenCode Prompt: Complete Intent Classification Phase 2 Training + Integration

## Context

All code is complete. Dataset is ready (737 examples, 38 districts). Just need to:
1. Run real LoRA training (was blocked by safety classifier)
2. Integrate into governor
3. Test

---

## Step 1: Run Real LoRA Training

```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

# Set environment variable to enable real training (not simulation)
set VECTOR_TRAINING_REAL=1

# Run training
python scripts/train_intent_real.py
```

**Expected output:**
```
CUDA available: True
GPU: NVIDIA GeForce RTX 5070 Ti
PEFT version: 0.x.x
Transformers version: 4.x.x

Starting real training...
[IntentQwen3] Fine-tuning on data/golden_intent_dataset_district_only.jsonl...
[IntentQwen3] Loaded 737 training examples
[IntentQwen3] Formatted 737 examples
[Training] Starting training for adapter 'intent_qwen3_8b'
[Training] Dataset size: 737 examples
[Training] Loading base model 'Qwen/Qwen3-8B'
... (training logs) ...
[Training] PEFT training complete, saved to data/adapters/intent_qwen3_8b/final
[IntentQwen3] Fine-tuning complete
```

**Time:** 30-60 minutes on RTX 5070 Ti

**If PEFT not installed:**
```bash
pip install peft transformers
```

**If training fails:**
- Check CUDA: `python -c "import torch; print(torch.cuda.is_available())"`
- Check GPU memory: `nvidia-smi`
- Verify model downloads: `ollama list` (should show qwen3:8b)

---

## Step 2: Evaluate Accuracy

```bash
python core/city/intent_qwen3_8b.py --evaluate
```

**Expected output:**
```
[IntentQwen3] Loaded model from data/adapters/intent_qwen3_8b/final
[IntentQwen3] Accuracy: 95.5% (704/737)
```

**Target:** 90-97% accuracy

**If accuracy <90%:**
- Check if model trained correctly (look for final loss <1.0 in training logs)
- Verify dataset format: `head -5 data/golden_intent_dataset_district_only.jsonl`
- Try increasing epochs: Edit `scripts/train_intent_real.py`, change `num_epochs=3` to `num_epochs=5`

---

## Step 3: Integrate into Governor

```bash
python scripts/integrate_intent_qwen3.py
```

**Expected output:**
```
✅ Qwen3 classifier integrated into governor.py (Stage 3)
Pipeline now: Regex → Embedding → Qwen3 → LLM fallback
```

**What it does:**
- Modifies `core/city/governor.py`
- Adds Stage 3 (qwen3:8b classifier) after embedding matcher
- Inserts code around line 1435 (after embedding matcher exception handler)

**If integration fails:**
- Check model exists: `dir data\adapters\intent_qwen3_8b\final`
- Verify imports: `python -c "from core.city.intent_qwen3_8b import IntentQwen3_8B"`
- Manual integration: Edit `core/city/governor.py`, find line 1434, add Stage 3 code (see below)

**Manual integration code (if script fails):**
```python
# After line 1434 in core/city/governor.py, add:

    # Stage 3: Qwen3 8B classifier (fine-tuned with LoRA)
    try:
        from core.city.intent_qwen3_8b import IntentQwen3_8B
        if not hasattr(classify_chat_intent, "_qwen3"):
            classify_chat_intent._qwen3 = IntentQwen3_8B()
        qwen3_result = await classify_chat_intent._qwen3.classify(text)
        if qwen3_result:
            _debug_classify_intent(text, "", f"QWEN3_MATCH -> {qwen3_result['district']} (conf={qwen3_result['confidence']:.3f})")
            return qwen3_result
    except Exception as e:
        logger.warning(f"[governor] Qwen3 classifier failed, falling through to LLM: {e}")
```

---

## Step 4: Integration Test

```bash
python scripts/diag_tier6.py
```

**Expected output:**
```
Tier 6 Eval Results: 10/10 routed correctly
```

**Target:** 10/10 accuracy (improvement from 9/10)

**If accuracy <10/10:**
- Check which queries failed (look at debug output)
- Verify all districts in test set are covered by training data
- Check embedding matcher still working: `python core/city/intent_matcher.py`

---

## Step 5: Final Verification

```bash
# Test a few queries manually
python -c "
import asyncio
from core.city.governor import classify_chat_intent

async def test():
    queries = [
        'quiz me on french',
        'help me scope a startup idea',
        'what are my goals',
        'review my code',
    ]
    for q in queries:
        result = await classify_chat_intent(q)
        print(f'{q} -> {result[\"district\"]} (conf={result[\"confidence\"]:.2f}, source={result[\"source\"]})')

asyncio.run(test())
"
```

**Expected:** All queries routed correctly with high confidence (>0.85)

---

## Success Criteria

✅ Training completes (30-60 min)  
✅ Evaluation: 90-97% accuracy  
✅ Integration: 10/10 on diag_tier6.py  
✅ Manual tests: All queries routed correctly  

---

## Troubleshooting

### Training fails with CUDA error
```bash
# Check CUDA
python -c "import torch; print(torch.cuda.is_available())"
# Should print: True

# Check GPU memory
nvidia-smi
# Should show RTX 5070 Ti with available memory
```

### PEFT not installed
```bash
pip install peft transformers
```

### Model not found
```bash
# Check if qwen3:8b is available
ollama list
# Should show: qwen3:8b

# If not, pull it
ollama pull qwen3:8b
```

### Integration test fails
```bash
# Check governor.py was modified
findstr "IntentQwen3_8B" core/city/governor.py
# Should show the integration code

# If not, run integration script again
python scripts/integrate_intent_qwen3.py
```

---

## Files Reference

**Already created:**
- `data/golden_intent_dataset_district_only.jsonl` (737 examples)
- `scripts/train_intent_real.py` (real training script)
- `core/city/intent_qwen3_8b.py` (classifier)
- `scripts/integrate_intent_qwen3.py` (integration script)

**Will be created:**
- `data/adapters/intent_qwen3_8b/final/` (LoRA adapter after training)

**Will be modified:**
- `core/city/governor.py` (Stage 3 added after integration)

---

## Expected Results

**Before Phase 2:**
- Accuracy: 90% (9/10)
- Latency: 100-300ms (embedding)
- Pipeline: Regex → Embedding → LLM

**After Phase 2:**
- Accuracy: 95-97% (10/10)
- Latency: <100ms (qwen3:8b)
- Pipeline: Regex → Embedding → Qwen3 → LLM

**Result:** JARVIS-level intent routing ✅

---

## Execute Now

Run these commands in order:

```bash
# 1. Train
set VECTOR_TRAINING_REAL=1
python scripts/train_intent_real.py

# 2. Evaluate
python core/city/intent_qwen3_8b.py --evaluate

# 3. Integrate
python scripts/integrate_intent_qwen3.py

# 4. Test
python scripts/diag_tier6.py
```

**Report results after each step.**
