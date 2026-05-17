# Agents earn/lose HP from real outcomes; at 0 HP they die and are replaced

HP must be wired to actual task outcomes — not heuristics, not time-based decay, not manual assignment. Static agents that never evolve are explicitly rejected. Ghost memory is extracted on death (real LLM summarization, not a template dump) and injected into the next generation.

**Why**: Static agents accumulate technical debt with no pressure to improve. Evolution without knowledge loss (ghost memory inheritance) means each generation is smarter. HP also creates a natural VRAM budget: weak agents run weaker models. Every HP event is a labeled training example for the future custom LLM.
