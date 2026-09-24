# OLLAMA_MAX_LOADED_MODELS=1 is a hard constraint, not a preference

Only one Ollama model may be loaded into VRAM at a time. `vector-focus` (gemma4:e4b; `vector-ambient` is the gemma4:e2b one) stays permanently loaded for real-time voice and ambient tasks. Every other model loads on-demand and is unloaded after use. No feature may load a second model concurrently.

**Why**: 12GB VRAM + KV cache overhead = OOM crash if two models are resident simultaneously. This is a physical hardware constraint on the RTX 5070 Ti. Any design that requires concurrent model loading is invalid for this machine.
