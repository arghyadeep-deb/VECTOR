# Vectorcode (vectorcode/src/) is the sole multi-platform communications layer

VECTOR Agent is fully absorbed and replaced. All cross-platform messaging, channel adapters, skill scaffolding, swarm coordination, and neural routing live in `vectorcode/src/`. The 30+ channel adapters are in `vectorcode/src/channels/`. New platforms are added there — never by editing the Governor or building a parallel comms layer.

**Why**: VECTOR was a separate repo with overlapping scope. Merging into vectorcode eliminated the dual-maintenance problem, gave all adapters access to the GNN router and neural layers, and made the codebase self-contained. Re-introducing VECTOR patterns defeats this consolidation.
