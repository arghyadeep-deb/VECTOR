# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
Its own README describes its `agent/` component as "Async agent loop with LiteLLM."
The README describes a queue-based asynchronous system with an agent loop, sessions, handlers, and tools.
It also contains a separate FastAPI backend for authentication, sessions, and quotas.
VECTOR does not call that separate backend.
VECTOR uses selected agent utilities including dataset inspection, GitHub examples, Hugging Face jobs, and planning tools.
The integration isolates the vendored `agent` namespace while loading those utilities.
Vendored as-is; VECTOR's own code calls into: `districts/coding/mlops_agent.py`.
