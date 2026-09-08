# Intent Classification System — Complete Architecture Guide

**Last Updated:** 2026-08-12  
**Status:** Phase 1 ✅ Working (90%) | Phase 2 ⏳ Training (95-97% expected)  
**Owner:** Arghyadeep Deb  
**Maintainer:** VECTOR Governance District

---

## Executive Summary

VECTOR's intent classification system routes user queries to the appropriate district (38 total) using a 4-stage pipeline:

```
Regex (35 patterns) → Embedding Similarity → Qwen3 8B (LoRA) → LLM Fallback
```

**Performance Targets:**
- Phase 1 (Embedding): 90% accuracy, 100-300ms latency ✅
- Phase 2 (Qwen3): 95-97% accuracy, <100ms latency ⏳ Training
- **Goal:** JARVIS-level intent routing (Opus/Fable performance)

---

## Architecture Overview

### 4-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ User Query: "quiz me on french"                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Regex Pre-Classifier                               │
│ - 35 high-confidence patterns                               │
│ - Confidence: 0.95                                          │
│ - Latency: <1ms                                             │
│ - Examples: "quiz me on *", "track my sleep"                │
└─────────────────────────────────────────────────────────────┘
                            ↓ (if no match)
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Embedding Similarity (Phase 1)                     │
│ - Model: nomic-embed-text (768-dim)                         │
│ - Index: FAISS HNSW                                         │
│ - Examples: 590+ (8+ per district)                          │
│ - Confidence: 0.85 threshold                                │
│ - Latency: 100-300ms                                        │
│ - Accuracy: 90%                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓ (if similarity < 0.85)
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Qwen3 8B Classifier (Phase 2)                      │
│ - Base: Qwen/Qwen3-8B                                       │
│ - Fine-tuned: LoRA (rank=16, alpha=32)                      │
│ - Training: 737 examples, 38 classes                        │
│ - Confidence: 0.7 threshold                                 │
│ - Latency: <100ms                                           │
│ - Accuracy: 95-97% (expected)                               │
└─────────────────────────────────────────────────────────────┘
                            ↓ (if confidence < 0.7)
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: LLM Fallback                                       │
│ - Model: vector-focus (gemma4:e4b)                          │
│ - Flexible, handles novel queries                           │
│ - Latency: 3-12s                                            │
│ - Accuracy: Variable                                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Result: {"district": "languages", "type": "quiz_vocabulary",│
│          "confidence": 0.95, "source": "embedding"}         │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Embedding Matcher (Phase 1)

**File:** `core/city/intent_matcher.py`

**Purpose:** Fast semantic similarity matching using pre-computed embeddings.

**How it works:**
1. Load 590+ examples from `data/intent_examples.json`
2. Compute embeddings using `nomic-embed-text` (768-dim)
3. Build FAISS HNSW index for fast similarity search
4. For each query: compute embedding → search index → return best match

**Key parameters:**
- `threshold`: 0.85 (minimum cosine similarity)
- `model`: nomic-embed-text (Ollama)
- `index_type`: FAISS HNSW (Hierarchical Navigable Small World)

**Performance:**
- Latency: 100-300ms
- Accuracy: 90% (9/10 on test set)
- Memory: ~50MB (embeddings + index)

**Maintenance:**
- Add examples: Edit `data/intent_examples.json`
- Rebuild index: `python core/city/intent_matcher.py --rebuild`
- Calibrate threshold: `python scripts/calibrate_intent_threshold.py`

---

### 2. Qwen3 8B Classifier (Phase 2)

**File:** `core/city/intent_qwen3_8b.py`

**Purpose:** Fine-tuned classifier for high-accuracy intent prediction.

**How it works:**
1. Load base model: `Qwen/Qwen3-8B`
2. Load LoRA adapter: `data/adapters/intent_qwen3_8b/final`
3. Format prompt: `"Classify this query: {text} → District: "`
4. Generate completion: Model predicts district name
5. Parse output: Extract district from generated text

**Training details:**
- Base model: Qwen3 8B (8B parameters, ~5.2GB)
- Fine-tuning: LoRA (rank=16, alpha=32)
- Dataset: 737 examples, 38 districts
- Training time: 30-60 minutes (RTX 5070 Ti)
- Expected accuracy: 95-97%

**Performance:**
- Latency: <100ms (generative, fast)
- Accuracy: 95-97% (expected)
- Memory: ~6GB (model + adapter)

**Training:**
```bash
# Enable real training
$env:VECTOR_TRAINING_REAL="1"

# Train
python scripts/train_intent_real.py

# Evaluate
python core/city/intent_qwen3_8b.py --evaluate
```

**Maintenance:**
- Retrain: `python scripts/auto_retrain_intent.py`
- Monitor accuracy: `python core/city/intent_monitor.py`
- Export misclassified: `data/misclassified_for_retraining.jsonl`

---

### 3. Intent Monitor

**File:** `core/city/intent_monitor.py`

**Purpose:** Track classification accuracy over time, detect degradation.

**How it works:**
1. Log every classification: `monitor.log_classification(text, predicted, actual, confidence)`
2. Track accuracy history
3. Collect misclassified examples
4. Detect degradation (accuracy < threshold)
5. Export examples for retraining

**Key metrics:**
- Total classifications
- Accuracy (correct / total)
- Accuracy history (last 1000 entries)
- Misclassified examples (last 1000)
- District distribution

**Usage:**
```python
from core.city.intent_monitor import IntentMonitor

monitor = IntentMonitor()

# Log classification
monitor.log_classification(
    text="quiz me on french",
    predicted_district="languages",
    actual_district="languages",  # if known
    confidence=0.95,
    source="embedding"
)

# Get stats
stats = monitor.get_stats()
print(f"Accuracy: {stats['accuracy']:.2%}")

# Check degradation
needs_retrain = monitor.check_degradation(threshold=0.90)
```

**Maintenance:**
- Stats file: `data/intent_classification_stats.json`
- Reset: `monitor.reset()`
- Export for retraining: `monitor.export_for_retraining()`

---

### 4. Automated Retraining Pipeline

**File:** `scripts/auto_retrain_intent.py`

**Purpose:** Automatically retrain model when accuracy degrades.

**Workflow:**
1. Check current accuracy
2. If accuracy < threshold (default 0.90):
   - Export misclassified examples
   - Merge with original dataset
   - Retrain LoRA adapter
   - Reset monitor stats
3. Evaluate new model
4. Verify improvement

**Usage:**
```bash
# Check accuracy only
python scripts/auto_retrain_intent.py --check-only

# Retrain if needed (threshold 0.90)
python scripts/auto_retrain_intent.py

# Force retraining
python scripts/auto_retrain_intent.py --force-retrain

# Custom threshold
python scripts/auto_retrain_intent.py --threshold 0.95
```

**Schedule:**
- Run weekly: `0 2 * * 0` (Sunday 2 AM)
- Or on-demand: When accuracy drops

**Maintenance:**
- Dataset: `data/golden_intent_dataset_combined.jsonl`
- Adapter: `data/adapters/intent_qwen3_8b/final`
- Monitor: `data/intent_classification_stats.json`

---

## Data Files

### Training Datasets

| File | Purpose | Size |
|------|---------|------|
| `data/intent_examples.json` | Phase 1 embedding examples | 590+ examples |
| `data/golden_intent_dataset.jsonl` | Original dataset (district + task_type) | 737 examples |
| `data/golden_intent_dataset_district_only.jsonl` | Simplified dataset (district only) | 737 examples |
| `data/golden_intent_dataset_combined.jsonl` | Combined (original + misclassified) | Variable |
| `data/misclassified_for_retraining.jsonl` | Misclassified examples | Variable |

### Model Artifacts

| File | Purpose | Size |
|------|---------|------|
| `data/adapters/intent_qwen3_8b/final/` | LoRA adapter | ~50MB |
| `data/intent_classification_stats.json` | Monitor stats | ~1MB |

### Format

**intent_examples.json:**
```json
[
  {"text": "quiz me on french", "district": "languages", "task_type": "quiz_vocabulary"},
  ...
]
```

**golden_intent_dataset_district_only.jsonl:**
```json
{"text": "quiz me on french", "district": "languages"}
{"text": "track my sleep", "district": "health"}
...
```

---

## Governor Integration

**File:** `core/city/governor.py`

**Function:** `classify_chat_intent(text: str) -> dict`

**Pipeline order:**
1. Regex pre-classifier (Stage 1)
2. Embedding matcher (Stage 2)
3. Qwen3 classifier (Stage 3) — Phase 2
4. LLM fallback (Stage 4)

**Integration code:**
```python
# After line 1434 in governor.py (Phase 2 integration)

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

**Return format:**
```python
{
    "type": "quiz_vocabulary",      # task_type (from DISTRICT_TASK_MAP)
    "district": "languages",         # predicted district
    "confidence": 0.95,              # confidence score
    "source": "qwen3_8b_classifier"  # classification source
}
```

---

## Testing

### Unit Tests

**File:** `tests/test_intent_matcher.py`

```bash
pytest tests/test_intent_matcher.py -v
```

### Integration Test

**File:** `scripts/diag_tier6.py`

```bash
python scripts/diag_tier6.py
```

**Expected:** 10/10 accuracy (Phase 2)

### Manual Test

```python
import asyncio
from core.city.governor import classify_chat_intent

async def test():
    queries = [
        "quiz me on french",
        "help me scope a startup idea",
        "what are my goals",
        "review my code",
        "track my sleep",
    ]
    for q in queries:
        result = await classify_chat_intent(q)
        print(f"{q} -> {result['district']} (conf={result['confidence']:.2f}, source={result['source']})")

asyncio.run(test())
```

---

## Troubleshooting

### Phase 1: Embedding Matcher Issues

**Problem:** Low accuracy (<90%)

**Solutions:**
1. Add more examples to `data/intent_examples.json`
2. Calibrate threshold: `python scripts/calibrate_intent_threshold.py`
3. Check embedding model: `ollama list | grep nomic-embed-text`
4. Rebuild index: `python core/city/intent_matcher.py --rebuild`

**Problem:** High latency (>300ms)

**Solutions:**
1. Check GPU: `nvidia-smi`
2. Reduce index size: Remove duplicate examples
3. Optimize FAISS: Use IVF instead of HNSW (trade accuracy for speed)

---

### Phase 2: Qwen3 Classifier Issues

**Problem:** Training fails

**Solutions:**
1. Check CUDA: `python -c "import torch; print(torch.cuda.is_available())"`
2. Check VRAM: `nvidia-smi` (need 6GB free)
3. Install PEFT: `pip install peft transformers`
4. Check dataset: `head -5 data/golden_intent_dataset_district_only.jsonl`

**Problem:** Low accuracy (<90%)

**Solutions:**
1. Increase training epochs: Edit `scripts/train_intent_real.py`, change `num_epochs=3` → `num_epochs=5`
2. Add more examples: Augment dataset
3. Check LoRA config: Verify rank=16, alpha=32
4. Retrain with combined dataset: `python scripts/auto_retrain_intent.py --force-retrain`

**Problem:** High latency (>100ms)

**Solutions:**
1. Check GPU: `nvidia-smi`
2. Optimize model: Use quantization (4-bit)
3. Reduce max_tokens: Edit `intent_qwen3_8b.py`, change `max_new_tokens=50` → `max_new_tokens=20`

---

### Monitor Issues

**Problem:** Stats not updating

**Solutions:**
1. Check file permissions: `data/intent_classification_stats.json`
2. Check logging: `logger.info("[IntentMonitor] ...")`
3. Reset monitor: `monitor.reset()`

**Problem:** No misclassified examples

**Solutions:**
1. Wait for more classifications (need at least 100)
2. Check logging: Ensure `actual_district` is provided
3. Manual logging: Add test classifications

---

## Performance Metrics

### Current Performance (Phase 1)

| Metric | Value | Target |
|--------|-------|--------|
| Accuracy | 90% (9/10) | 90% ✅ |
| Latency | 100-300ms | <300ms ✅ |
| Memory | ~50MB | <100MB ✅ |
| Examples | 590+ | 500+ ✅ |

### Expected Performance (Phase 2)

| Metric | Value | Target |
|--------|-------|--------|
| Accuracy | 95-97% | 95%+ ⏳ |
| Latency | <100ms | <100ms ⏳ |
| Memory | ~6GB | <8GB ⏳ |
| Training time | 30-60min | <60min ⏳ |

---

## Maintenance Schedule

### Daily
- Monitor accuracy: `python scripts/auto_retrain_intent.py --check-only`
- Review misclassified examples: `data/misclassified_for_retraining.jsonl`

### Weekly
- Run retraining pipeline: `python scripts/auto_retrain_intent.py`
- Update embedding examples: Add 10-20 new examples
- Review accuracy history: `data/intent_classification_stats.json`

### Monthly
- Full evaluation: `python core/city/intent_qwen3_8b.py --evaluate`
- Integration test: `python scripts/diag_tier6.py`
- Dataset audit: Remove duplicates, add edge cases
- Performance optimization: Tune thresholds, LoRA config

---

## Future Improvements

### Short-term (Q3 2026)
1. ✅ Add performance monitor
2. ✅ Automated retraining pipeline
3. ✅ Enhanced embedding examples (590+)
4. ⏳ Integrate Qwen3 classifier into governor
5. ⏳ Achieve 95-97% accuracy

### Medium-term (Q4 2026)
1. Add more districts (expand to 50+)
2. Multi-label classification (predict multiple districts)
3. Confidence calibration (temperature scaling)
4. Active learning (prioritize uncertain examples)

### Long-term (2027)
1. Custom LLM (OpenMythos RDT) for intent classification
2. Multi-modal intent (text + voice + context)
3. Real-time adaptation (online learning)
4. Federated learning (privacy-preserving)

---

## References

### Internal Documentation
- `CONTEXT.md` — Full VECTOR architecture
- `VECTOR_RULEBOOK.md` — Operational guide
- `docs/intent_classification_implementation.md` — Implementation details

### External Resources
- [FAISS Documentation](https://faiss.ai/)
- [PEFT Library](https://github.com/huggingface/peft)
- [Qwen3 Model Card](https://huggingface.co/Qwen/Qwen3-8B)
- [nomic-embed-text](https://ollama.com/library/nomic-embed-text)

### Related Files
- `core/city/governor.py` — Governor routing
- `core/city/intent_matcher.py` — Phase 1 embedding matcher
- `core/city/intent_qwen3_8b.py` — Phase 2 Qwen3 classifier
- `core/city/intent_monitor.py` — Performance monitor
- `scripts/auto_retrain_intent.py` — Retraining pipeline

---

## Contact

**Questions?** Reach out to:
- Arghyadeep Deb (owner)
- VECTOR Governance District (maintainer)
- `#vector-support` channel

**Issues?** File at:
- GitHub: `VECTOR/issues`
- Internal: `districts/governance/issue_tracker.py`

---

**Last reviewed:** 2026-08-12  
**Next review:** 2026-08-19 (weekly)
