---
name: vector-modelfile
description: Create or update an Ollama modelfile for VECTOR, ensuring correct GPU parameters, system prompt structure, and speed expectations.
---

The user wants to create or update a VECTOR modelfile. Ensure all GPU optimization params are present.

## Usage
`/vector-modelfile <model-name>`

Example: `/vector-modelfile vector-focus`

## Required Parameters (every modelfile MUST have all of these)

```
PARAMETER num_gpu 99        # Force all layers to GPU — critical for speed
PARAMETER num_thread 8      # CPU threads for hybrid models
PARAMETER num_batch 512     # Prompt processing batch size
PARAMETER temperature <x>   # Model-specific
PARAMETER top_p <x>         # Model-specific
PARAMETER top_k <x>         # Model-specific  
PARAMETER num_ctx <x>       # Context window — see limits below
PARAMETER num_predict <x>   # Max output tokens
PARAMETER repeat_penalty <x>
```

## Context Window Guidelines (speed vs capability)

| Model | Base | Recommended ctx | Reason |
|-------|------|----------------|--------|
| vector-ambient | gemma4:e2b | 4096 | Classification only |
| vector-focus | gemma4:e4b | 16384 | Real-time; 32k is too slow |
| vector-coder | qwen3:14b | 32768 | Code needs context |
| vector-multilingual | qwen3:14b | 32768 | Translation needs context |
| vector-reasoning | qwen3:14b | 32768 | Reasoning chains |
| vector-deep | gemma4:26b | 65536 | Deep analysis — expected slow |
| vector-chairman | gemma4:31b | 32768 | Council — expected slow |

## Speed Expectations (realistic, not aspirational)

- vector-ambient: 60-80 tok/s  
- vector-focus: 45-55 tok/s  
- vector-coder/reasoning/multilingual: 18-25 tok/s  
- vector-deep: 5-8 tok/s (expected — MoE 26B)  
- vector-chairman: 3-5 tok/s (expected — dense 31B)  

## After Updating a Modelfile

Always rebuild the model:
```bash
ollama create <model-name> -f modelfiles/<model-name>.modelfile
```

Then verify speed:
```bash
ollama run <model-name> "Say hello in exactly 5 words"
```

## System Prompt Rules

Every VECTOR model system prompt must:
- State the model's role in VECTOR City clearly
- Include "OUTPUT RULES — ABSOLUTE" section forbidding "Thinking" headers, preamble, and sycophantic phrases
- Reference session hydration context if it's a conversational model
- Specify exact output format if it's a structured model (like vector-ambient's JSON schema)
