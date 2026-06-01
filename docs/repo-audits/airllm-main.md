# airllm-main Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\airllm-main`
**License:** Apache 2.0 (MIT per setup.py classifiers; Apache 2.0 per LICENSE file)
**Version:** 2.11.0 (setup.py)
**PyPI:** `pip install airllm`

### What airllm actually does (concrete features)

1. **Layer-wise streaming inference** — splits a HuggingFace model into per-transformer-layer `.safetensors` shards on first load. During inference, each layer is loaded from disk to CPU (pinned memory), moved to GPU, run, then evicted (`layer.to("meta")`). Only one layer lives in VRAM at a time.
2. **Prefetching** — a `ThreadPoolExecutor` overlaps loading layer N+1 from disk while layer N is computing on GPU (~10% speedup).
3. **Block-wise quantization compression** — optional `compression='4bit'` or `compression='8bit'` via `bitsandbytes` NF4/blockwise; reduces disk I/O by 4x/2x (weights-only, no activation quantization).
4. **Multi-architecture support** — `AutoModel.from_pretrained()` detects architecture from HuggingFace `config.json` and routes to the appropriate class: `AirLLMLlama2`, `AirLLMQWen`, `AirLLMQWen2`, `AirLLMBaichuan`, `AirLLMChatGLM`, `AirLLMInternLM`, `AirLLMMistral`, `AirLLMMixtral`. Unknown architectures fall back to `AirLLMLlama2`.
5. **BetterTransformer / SDPA fallback chain** — attempts FlashAttention via `BetterTransformer.transform()`, falls back to `attn_implementation="sdpa"`, then vanilla.
6. **KV cache support** — optional `use_cache=True` pass-through (disabled automatically on transformers >=4.36 due to `cache_utils_installed` guard).
7. **CPU inference** — device can be set to `"cpu"` (no CUDA required; no pin_memory on CPU path).
8. **MacOS MLX backend** — `AirLLMLlamaMlx` for Apple Silicon via MLX.
9. **HuggingFace gated model support** — `hf_token` parameter passed through to all Hub calls.
10. **`delete_original` option** — removes original HF checkpoint after splitting to save disk space.
11. **Disk-space pre-check** — `check_space()` raises `NotEnoughSpaceException` before attempting a split that would fail mid-way.
12. **`split_and_save_layers()` utility** — exposed as a standalone function to pre-split a model offline.

**No UI.** Pure Python inference library. No web dashboard, no REST server, no frontend of any kind.

**Key parameters on `AutoModel.from_pretrained()`:**
- `model_local_path_or_repo_id` — HF repo ID or local path
- `device` — defaults to `"cuda:0"`
- `dtype` — defaults to `torch.float16`
- `max_seq_len` — defaults to 512
- `layer_shards_saving_path` — optional path for the split shards (defaults to model cache dir)
- `compression` — `None` / `'4bit'` / `'8bit'`
- `hf_token` — for gated models
- `prefetching` — default True (disabled automatically with compression)
- `delete_original` — default False

**Note:** `airllm.AutoModel` does NOT export `AutoTokenizer`. The tokenizer is accessed via `model.tokenizer` after `from_pretrained()`.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|-------------------|-----------------|--------|
| `airllm` in `requirements.txt` | `requirements.txt` line 31 | Present as commented-out optional: `# OPTIONAL (not installed by default): airllm>=2.10.0` | ⚠️ Listed but not installed |
| `pip install airllm` present on system | `python -c "import airllm"` | `ModuleNotFoundError: No module named 'airllm'` | ❌ Not installed |
| VECTOR wrapper file | `core/inference/airllm_runner.py` | File exists, imports correctly, `AirLLMRunner()` instantiates with `_airllm_available: False` | ⚠️ Wrapper present but library absent |
| `_airllm_chat()` in `ollama_safe.py` | `core/inference/ollama_safe.py:243-261` | Code path exists; routes 70B models through AirLLM before falling back to Ollama | ⚠️ Logic present but broken import path (see Gap 1) |
| `AirLLMConfig` in config | `core/config.py:255-258` | `models_dir`, `cache_dir`, `max_gpu_memory_gb` fields wired into `CONFIG["airllm"]` | ✅ Config present |
| `_AIRLLM_MODELS` set | `core/inference/ollama_safe.py:48-50` | `{"llama2-70b", "llama3-70b", "mixtral-8x7b", "falcon-40b", "codellama-70b"}` — gate logic correct | ✅ Gate logic present |
| Layer-streaming inference (the core feature) | `core/inference/airllm_runner.py:76-119` | `_load_with_airllm()` calls `AutoModel.from_pretrained()` correctly except for two bugs (see Gaps 1 and 2) | ⚠️ Logic correct but two API bugs |
| Fallback to Ollama when airllm absent | `core/inference/airllm_runner.py:121-146` | `_load_with_ollama()` present; `_check_airllm()` returns `False` → Ollama path taken | ✅ Fallback works |
| Async wrapper | `core/inference/airllm_runner.py` | `load_model()`, `generate()`, `batch_generate()` are all async | ✅ Correct async design |
| 70B model list | `core/inference/airllm_runner.py:313-322` | `list_supported_models()` includes llama2-70b, llama3-70b, mixtral-8x7b, falcon-40b, codellama-70b; has trailing space in `" WizardLM-70B"` (minor typo) | ⚠️ Minor typo |
| 4bit/8bit compression | Not wired in `airllm_runner.py` | `AirLLMRunner` never passes `compression=` to `AutoModel.from_pretrained()` | ❌ Compression not exposed |
| `max_seq_len` configurable | `core/inference/airllm_runner.py:96-102` | `load_model()` accepts `max_seq_len` and passes it through | ✅ Present |
| CPU inference path | Not wired | `load_model()` defaults `device="cuda"`; no CPU fallback for non-CUDA environments | ❌ Not implemented |
| `delete_original` option | Not wired | `AirLLMRunner` never passes `delete_original=True` | ❌ Not exposed (low priority — disk management) |

---

## 3. Frontend / Panel Spec

airllm has no UI whatsoever. It is a pure inference library. No dashboard panel is needed or applicable.

VECTOR's architecture correctly treats this as an optional pip dependency for overnight 70B tasks, not as a service with a monitoring panel.

---

## 4. Verdict

**INTEGRATE DIRECTLY (keep as pip dependency, fix 3 bugs)**

Reasoning: airllm is a real PyPI library (`pip install airllm`). The right integration is exactly what VECTOR has attempted: keep it as an optional pip dep, import it guarded in a wrapper, fall back to Ollama when absent. The source clone in `GitHub/airllm-main` is not needed — the canonical install is via pip.

However, the wrapper (`core/inference/airllm_runner.py`) has three bugs that would cause `_airllm_chat` to silently fail even after `pip install airllm`:

1. **Broken import path in `ollama_safe.py`** — calls `from core.inference.airllm.airllm_runner import AirLLMRunner` but the file is at `core/inference/airllm_runner.py` (no `airllm/` subdirectory). This raises `ModuleNotFoundError` at runtime, making the entire AirLLM path dead.
2. **`AutoTokenizer` does not exist in `airllm`** — `airllm_runner.py` lines 85 and 190 call `from airllm import AutoTokenizer, AutoModel`. The `airllm` package does not export `AutoTokenizer`; the tokenizer is accessed via `model.tokenizer` after `AutoModel.from_pretrained()`. This would raise `ImportError` the moment airllm IS installed and a 70B model is requested.
3. **`cache_dir` is not a valid parameter for `airllm.AutoModel.from_pretrained()`** — the correct parameter is `layer_shards_saving_path`. Passing `cache_dir=` has no effect (it gets absorbed by `**kwargs` silently), so shards would be saved to the default HF cache instead of VECTOR's configured `./data/airllm_cache`.

Gaps 1 and 2 are blocking — they guarantee failure if airllm is ever installed. Gap 3 is a silent misconfiguration.

The source clone (`GitHub/airllm-main`) can be safely deleted after `pip install airllm>=2.11.0` is added to the active requirements.

---

## 5. Gaps

| # | Issue | Location | Type | Status |
|---|-------|----------|------|--------|
| 1 | **Broken import path**: `_airllm_chat()` calls `from core.inference.airllm.airllm_runner import AirLLMRunner` but no `airllm/` subpackage exists; correct path is `from core.inference.airllm_runner import AirLLMRunner` | `core/inference/ollama_safe.py:248` | Bug — runtime `ModuleNotFoundError` | ❌ |
| 2 | **`AutoTokenizer` not exported from airllm**: both `_load_with_airllm()` and `_generate_with_airllm()` do `from airllm import AutoTokenizer, AutoModel`; `airllm` has no `AutoTokenizer` — use `model.tokenizer` instead | `core/inference/airllm_runner.py:85, 190, 195` | Bug — `ImportError` when airllm installed | ❌ |
| 3 | **`cache_dir` is not a valid `AutoModel.from_pretrained()` kwarg**: should be `layer_shards_saving_path=` per airllm API | `core/inference/airllm_runner.py:97-102` | Misconfiguration — silently ignored | ❌ |
| 4 | **`airllm` not pip-installed**: commented out in `requirements.txt`, not in active deps; VECTOR can never use it | `requirements.txt:31` | Deployment gap | ⚠️ |
| 5 | **4-bit/8-bit compression not exposed**: `AirLLMRunner.load_model()` never passes `compression=` to `AutoModel.from_pretrained()`; this is a ~4x inference speedup for overnight tasks | `core/inference/airllm_runner.py:76-119` | Missing feature | ⚠️ |
| 6 | **Trailing space in model name**: `list_supported_models()` returns `" WizardLM-70B"` with a leading space | `core/inference/airllm_runner.py:321` | Minor typo | ⚠️ |
| 7 | **Source clone not needed**: `GitHub/airllm-main` is a full source clone of the pip package; serves no purpose once `pip install airllm` is active | `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\airllm-main` | Cleanup | ⚠️ |

### Recommended Fixes

**Fix Gap 1** (`ollama_safe.py:248`):
```python
# Before:
from core.inference.airllm.airllm_runner import AirLLMRunner
# After:
from core.inference.airllm_runner import AirLLMRunner
```

**Fix Gap 2** (`airllm_runner.py:85-95` and `190-196`):
```python
# Before:
from airllm import AutoTokenizer, AutoModel
tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
model = AutoModel.from_pretrained(model_name, device=device, max_seq_len=max_seq_len, cache_dir=cache_dir)
# After:
from airllm import AutoModel
model = AutoModel.from_pretrained(
    model_name,
    device=device,
    max_seq_len=max_seq_len,
    layer_shards_saving_path=cache_dir,  # Gap 3 fixed here too
)
tokenizer = model.tokenizer  # tokenizer lives on the model object
```

**Activate** (`requirements.txt`): uncomment `airllm>=2.10.0` to add to active deps.
