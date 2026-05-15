# Wave 9 — Absorbing Claude Code's `.claude/` ecosystem

**Status:** Complete  
**Owner:** Arghyadeep Deb  
**Date:** 2026-05-15

## Goal

Ingest the entire `.claude/` configuration ecosystem (skills, agents, slash commands, hooks, rules) into VectorCode as personalized, VECTOR-branded, locally-hosted assets. After this absorption VectorCode is a strict superset of Claude Code's surface area, with all references redirected to local Ollama models and VECTOR identity.

## What was absorbed

| Source folder | Items | Destination | Notes |
|---|---:|---|---|
| `.claude/skills/`   | 272 | `vectorcode/skills/`   | Top-level `*.md` get `vc-` prefix; folder-form skills retain folder name (containing `SKILL.md`); `claude-*` folders renamed to `vc-claude-*` |
| `.claude/agents/`   |  38 | `vectorcode/agents/`   | All renamed to `vector-*` if not already; model refs (`opus`, `sonnet`, `haiku`) rewritten to `vector-chairman/coder/fast` |
| `.claude/commands/` |  30 | `vectorcode/commands/` | Slash commands kept with original names so user invocation is unchanged |
| `.claude/hooks/`    |   8 | `vectorcode/hooks/`    | Python hooks moved verbatim with VECTOR header marker |
| `.claude/rules/`    |  12 | `vectorcode/rules/`    | Project-wide rules ported as-is |
| **Total**           | **360** | — | — |

## Personalization rules applied (in order)

1. **Branding rewrites** — `Claude Code` → `VectorCode`, `Claude API` → `VectorCode API (local Ollama)`, bare `Claude` → `VECTOR`, `Anthropic` → `VECTOR Labs` or removed in attribution context.
2. **Model rewrites** — hard-coded `claude-sonnet-*` / `claude-opus-*` / `claude-haiku-*` re-pointed to `vector-coder` / `vector-chairman` / `vector-fast` (resolved through `core/inference/ollama_safe.py`).
3. **Path rewrites** — `.claude/...` paths in prose rewritten to `vectorcode/...`.
4. **Provenance header** — every `.md` file prepended with a VECTOR-INGESTED comment block recording original source path and ingest timestamp.
5. **No paid APIs** — outbound Anthropic SDK references re-labeled as Ollama SDK; runtime impact = zero (these are documentation strings).

## Tooling

Three reproducible scripts live in `scripts/`:

- `scripts/ingest_claude_assets.py` — main copy + branding pass.
- `scripts/cleanup_ingested_skills.py` — folder/file naming hygiene (skill folders keep `SKILL.md` filename; folder name carries the identity).
- `scripts/polish_ingested_assets.py` — fixes compound-replacement artifacts produced by stage 1.

Idempotent: re-running with `--apply` is safe; identical files are skipped.

## Manifest

`vectorcode/INGESTION_MANIFEST.json` captures every source → destination mapping with file size, kind, and ingestion timestamp. Used as audit trail.

## Verification

Final counts after cleanup pass:

```
skills folders:           94  (each containing a single SKILL.md)
skills .md (top-level):  153  (all vc-* prefixed)
agents:                   38  (all vector-* / vc-* prefixed)
commands:                 30
hooks:                     8
rules:                    12
SKILL.md count:           94  (correct — one per skill folder)
vc-SKILL.md leftover:      0  (cleaned up)
```

Spot-check confirmed:
- VECTOR-INGESTED headers present
- `Claude` → `VECTOR` in prose
- `model: opus` → `model: vector-chairman` in agent frontmatter
- Skill folder identity preserved (`vc-claude-api/SKILL.md` rather than `claude-api/vc-SKILL.md`)

## What is NOT modified

- `.claude/` itself is untouched. Claude Code can still use its own configuration.
- Existing `vectorcode/skills/vc-*.md` files (200+ pre-existing skills) untouched — only newly ingested files carry the VECTOR-INGESTED header.

## Follow-up work (future waves)

- Wire `vectorcode/agents/*.md` into `vectorcode/src/agents/loader.py` so the agent registry can dispatch to them.
- Wire `vectorcode/commands/*.md` into the slash-command parser in `vectorcode/src/vector_cli/`.
- Wire `vectorcode/hooks/*.py` into the hook registry at `vectorcode/src/hooks/registry.py`.
- Strip the duplicated heritage between `vc-claude-api/` and existing `vc-` skills (target: deduplicate after coverage diff).
