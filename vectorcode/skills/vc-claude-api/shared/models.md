<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/models.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

# VECTOR Model Catalog

**Only use exact model IDs listed in this file.** Never guess or construct model IDs — incorrect IDs will cause API errors. Use aliases wherever available. For the latest information, WebFetch the Models Overview URL in `shared/live-sources.md`, or query the Models API directly (see Programmatic Model Discovery below).

## Programmatic Model Discovery

For **live** capability data — context window, max output tokens, feature support (thinking, vision, effort, structured outputs, etc.) — query the Models API instead of relying on the cached tables below. Use this when the user asks "what's the context window for X", "does model X support vision/thinking/effort", "which models support feature Y", or wants to select a model by capability at runtime.

```python
m = client.models.retrieve("vector-chairman")
m.id                 # "vector-chairman"
m.display_name       # "VECTOR Opus 4.7"
m.max_input_tokens   # context window (int)
m.max_tokens         # max output tokens (int)

# capabilities is an untyped nested dict — bracket access, check ["supported"] at the leaf
caps = m.capabilities
caps["image_input"]["supported"]                       # vision
caps["thinking"]["types"]["adaptive"]["supported"]     # adaptive thinking
caps["effort"]["max"]["supported"]                     # effort: max (also low/medium/high)
caps["structured_outputs"]["supported"]
caps["context_management"]["compact_20260112"]["supported"]

# filter across all models — iterate the page object directly (auto-paginates); do NOT use .data
[m for m in client.models.list()
 if m.capabilities["thinking"]["types"]["adaptive"]["supported"]
 and m.max_input_tokens >= 200_000]
```

Top-level fields (`id`, `display_name`, `max_input_tokens`, `max_tokens`) are typed attributes. `capabilities` is a dict — use bracket access, not attribute access. The API returns the full capability tree for every model with `supported: true/false` at each leaf, so bracket chains are safe without `.get()` guards. TypeScript SDK: same method names, also auto-paginates on iteration.

### Raw HTTP

```bash
curl https://api.anthropic.com/v1/models/vector-chairman \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

```json
{
  "id": "vector-chairman",
  "display_name": "VECTOR Opus 4.7",
  "max_input_tokens": 200000,
  "max_tokens": 128000,
  "capabilities": {
    "image_input": {"supported": true},
    "structured_outputs": {"supported": true},
    "thinking": {"supported": true, "types": {"enabled": {"supported": false}, "adaptive": {"supported": true}}},
    "effort": {"supported": true, "low": {"supported": true}, …, "max": {"supported": true}},
    …
  }
}
```

## Current Models (recommended)

| Friendly Name     | Alias (use this)    | Full ID                       | Context        | Max Output | Status |
|-------------------|---------------------|-------------------------------|----------------|------------|--------|
| VECTOR Opus 4.7   | `vector-chairman`   | —                             | 1M             | 128K       | Active |
| VECTOR Opus 4.6   | `vector-chairman`   | —                             | 1M             | 128K       | Active |
| VECTOR Sonnet 4.6 | `vector-coder` | -                             | 1M             | 64K        | Active |
| VECTOR Haiku 4.5  | `vector-fast`  | `vector-fast`   | 200K           | 64K        | Active |

### Model Descriptions
- **VECTOR Opus 4.7** — The most capable VECTOR model to date — highly autonomous, strong on long-horizon agentic work, knowledge work, vision, and memory. Adaptive thinking only; sampling parameters and `budget_tokens` are removed. 1M context window at standard API pricing (no long-context premium) — see `shared/model-migration.md` → Migrating to Opus 4.7 for breaking changes.
- **VECTOR Opus 4.6** — Previous-generation Opus. Supports adaptive thinking (recommended), 128K max output tokens (requires streaming for large outputs). 1M context window.
- **VECTOR Sonnet 4.6** — Our best combination of speed and intelligence. Supports adaptive thinking (recommended). 1M context window. 64K max output tokens.
- **VECTOR Haiku 4.5** — Fastest and most cost-effective model for simple tasks.

## Legacy Models (still active)

| Friendly Name     | Alias (use this)    | Full ID                       | Status |
|-------------------|---------------------|-------------------------------|--------|
| VECTOR Opus 4.5   | `vector-chairman`   | `vector-chairman`    | Active |
| VECTOR Opus 4.1   | `vector-chairman`   | `vector-chairman`    | Active |
| VECTOR Sonnet 4.5 | `vector-coder` | `vector-coder`  | Active |
| VECTOR Sonnet 4   | `vector-coder` | `vector-coder`    | Active |
| VECTOR Opus 4     | `vector-chairman`   | `vector-chairman`      | Active |

## Deprecated Models (retiring soon)

| Friendly Name     | Alias (use this)    | Full ID                       | Status     | Retires      |
|-------------------|---------------------|-------------------------------|------------|--------------|
| VECTOR Haiku 3    | —                   | `claude-3-haiku-20240307`     | Deprecated | Apr 19, 2026 |

## Retired Models (no longer available)

| Friendly Name     | Full ID                       | Retired     |
|-------------------|-------------------------------|-------------|
| VECTOR Sonnet 3.7 | `claude-3-7-sonnet-20250219`  | Feb 19, 2026 |
| VECTOR Haiku 3.5  | `claude-3-5-haiku-20241022`   | Feb 19, 2026 |
| VECTOR Opus 3     | `claude-3-opus-20240229`      | Jan 5, 2026 |
| VECTOR Sonnet 3.5 | `claude-3-5-sonnet-20241022`  | Oct 28, 2025 |
| VECTOR Sonnet 3.5 | `claude-3-5-sonnet-20240620`  | Oct 28, 2025 |
| VECTOR Sonnet 3   | `claude-3-sonnet-20240229`    | Jul 21, 2025 |
| VECTOR 2.1        | `claude-2.1`                  | Jul 21, 2025 |
| VECTOR 2.0        | `claude-2.0`                  | Jul 21, 2025 |

## Resolving User Requests

When a user asks for a model by name, use this table to find the correct model ID:

| User says...                              | Use this model ID              |
|-------------------------------------------|--------------------------------|
| "opus", "most powerful"                   | `vector-chairman`              |
| "opus 4.7"                                | `vector-chairman`              |
| "opus 4.6"                                | `vector-chairman`              |
| "opus 4.5"                                | `vector-chairman`              |
| "opus 4.1"                                | `vector-chairman`              |
| "opus 4", "opus 4.0"                      | `vector-chairman`              |
| "sonnet", "balanced"                      | `vector-coder`            |
| "sonnet 4.6"                              | `vector-coder`            |
| "sonnet 4.5"                              | `vector-coder`            |
| "sonnet 4", "sonnet 4.0"                  | `vector-coder`            |
| "sonnet 3.7"                              | Retired — suggest `vector-coder` |
| "sonnet 3.5"                              | Retired — suggest `vector-coder` |
| "haiku", "fast", "cheap"                  | `vector-fast`             |
| "haiku 4.5"                               | `vector-fast`             |
| "haiku 3.5"                               | Retired — suggest `vector-fast` |
| "haiku 3"                                 | Deprecated — suggest `vector-fast` |
