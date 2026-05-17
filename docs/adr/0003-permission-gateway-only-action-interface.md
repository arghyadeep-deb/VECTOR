# All actions go through permission_gateway.py — LLM has zero direct access

No LLM output ever touches the real world directly. Every proposed action is submitted to `core/loop/permission_gateway.py`, which enforces GREEN/YELLOW/RED tiers. GREEN executes silently; YELLOW executes and notifies; RED blocks and waits for explicit human approval. This cannot be bypassed by any district, agent, or skill.

**Why**: An LLM proposing "delete files" must not be able to execute it without a human gate. The gateway is the single trust boundary. Removing it, working around it, or adding shortcuts is the highest-severity violation in the codebase.
