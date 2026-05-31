# Repo Audit — `system_prompts_leaks-main`

> Audited: 2026-05-31 · Repo: `asgeirtj/system_prompts_leaks` · License: **CC0 1.0 (public domain)**
> Verdict: **PATCH VECTOR** — vendor the corpus as a read-only reference library + tiny wiring into the prompt-optimizer / persona system.

---

## Section 1 — Repo Reality

**It is pure DATA.** A curated, frequently-updated collection of leaked/extracted **system prompts** from commercial AI products. There is **zero runnable code** — no Python, no scripts, no package. Just markdown.

**Verified contents** (`find . -type f` → 220 files):

| Extension | Count |
|-----------|-------|
| `.md` | 214 |
| `.json` | 1 (`Google/gemini-3.5-flash-tools.json` — tool schema) |
| `.xml` | 1 (Claude 3.7 tools dump) |
| `.txt` | 1 (old 4o-mini) |
| `.yml` | 2 (`.github` workflows — traffic badges only) |
| LICENSE / README / CONTRIBUTING | 3 |

Total corpus ≈ **6.5 MB**. Files range from short persona snippets (~30 lines) to full harness dumps (e.g. `claude-code-opus-4.8.md` = 953 lines incl. tool definitions, system-reminders, memory/context-management sections).

**Per-vendor file counts (verified):**

| Vendor folder | Files | What's inside |
|---------------|-------|---------------|
| `OpenAI/` | 83 | GPT-5.5/5.4/5.3 (thinking/instant/api/pro), full **Codex CLI** prompts + plan_mode + auto-review, **8 GPT-5.1 personalities** (default/friendly/professional/candid/cynical/efficient/nerdy/quirky), GPT-5 personalities, GPT-4o/4.1/4.5, o3/o4-mini (API high/med/low), **tool prompts** (web-search, deep-research, python, canvas, image-gen, memory, file-search), image-safety policies |
| `Anthropic/` | 66 | Claude Opus 4.8/4.7/4.6, Sonnet 4.6, **Claude Code (Opus 4.8)**, Cowork, Desktop, Mobile, In-Chrome, for-Excel/Word/PPT, `default-styles.md`, `anthropic_reminders.md`, `research_instructions.md`, 24 dated **Official** `claude_behavior` prompts, raw/no-tools variants |
| `Misc/` | 29 | Cursor, Amp, Zed, Warp, **VS Code Copilot Agent**, Copilot CLI, OpenCode, Notion AI, Meta AI, Le Chat, Qwen 3.6, Kagi, Raycast, Docker Gordon, ElevenLabs voice agent, Hermes, Character AI, etc. |
| `Google/` | 23 | Gemini 3.5 Flash / 3.1 Pro / 3 / 2.5 / 2.0, **Gemini CLI**, **Antigravity CLI**, Jules, NotebookLM, AI Studio Build, Search AI Mode |
| `xAI/` | 11 | Grok 4.3/4.2/4.1/4/3, Grok Build (CLI agent), Grok Expert, personas, safety instructions |
| `Perplexity/` | 3 | Perplexity Computer, Comet browser, Voice assistant |

**Why it matters for VECTOR specifically:** the corpus contains the *actual production prompts* of the exact agentic coding harnesses VECTOR competes with / imitates — **Claude Code, Codex CLI, Cursor, Gemini CLI, Antigravity CLI, Grok Build, Warp, Zed**. These are working examples of tool-use scaffolding, plan-mode design, and persona/tone calibration. It also has **9+ personality variants per vendor** (candid, pragmatic, nerdy, cynical, professional…) — directly relevant to VECTOR's persona/tone system.

---

## Section 2 — VECTOR Parity (verified by reading real files)

**Key question: does VECTOR have a curated collection of *reference* system prompts to learn from? → NO.** It has its own persona string and a prompt-optimizer that matches *internal* components only. Verified paths:

| Capability | VECTOR has it? | Evidence (real path) | Verdict |
|------------|----------------|----------------------|---------|
| Own VECTOR persona / system prompt | Yes | `modelfiles/vector-focus.modelfile` (full `SYSTEM """..."""` — "Paul Bettany JARVIS tone"), `core/personality/characters/vector.json` (traits, speech_patterns, rules, knowledge_boundaries) | ✅ |
| Persona injection into LLM calls | Yes | `core/persona/persona_manager.py:48 inject_persona()`, `core/persona/identity.py`, `core/personality/middleware.py`, `core/personality/tone_adapter.py` | ✅ |
| 10 Ollama modelfiles each with a SYSTEM prompt | Yes | `modelfiles/` — 10 `.modelfile` (focus, coder, deep, chairman, reasoning, r1, dev, fast, ambient, multilingual) | ✅ |
| Prompt-optimizer | Yes — but **internal-only** | `.claude/skills/prompt-optimizer/SKILL.md` — 6-phase pipeline matches prompts to **ECC ecosystem components** (skills/commands/agents/hooks). `grep "corpus\|reference\|few-shot"` → only self-referential "Reference files/conventions". **No real-world prompt examples.** | ⚠️ |
| Curated **reference library of real product system prompts** (Claude Code, Codex, Cursor, GPT personalities…) | **No** | `grep -ril "system_prompts_leaks\|prompt_library\|reference_prompts\|leaked"` across `core/` → **0 matches**. VECTOR has only its *own* persona string; nothing to compare/learn from. | ❌ |
| Few-shot examples for persona/tone design | No | `core/personality/characters/` holds only `vector.json`. No library of alternative persona templates (the repo has 20+). | ❌ |
| Reference for agentic-harness prompt design (tool scaffolding, plan-mode) | No | VECTOR's harness prompts are hand-written in modelfiles; no corpus of how Claude Code / Codex / Cursor structure theirs. | ❌ |

**Bottom line:** VECTOR is *good* at carrying and injecting its own persona, and at optimizing prompts against its own component catalog. It has **no external reference corpus** — exactly the gap this repo fills.

---

## Section 3 — Value to VECTOR

This is a reference corpus, so "value" = does giving VECTOR access to it make its prompt-engineering / persona work measurably better? **Yes, modestly but concretely.** Three real uses:

1. **Few-shot fuel for the prompt-optimizer.** The `prompt-optimizer` skill currently critiques prompts against VECTOR's own ECC components with *no examples of excellent real-world prompts*. Loading 5–10 relevant leaked prompts (e.g. Codex `personality_pragmatic.md`, Claude Code harness, Cursor) as few-shot context would let the optimizer say "here's how a shipping product structures tool-use / plan-mode / persona" instead of reasoning in a vacuum.

2. **Persona/tone template library.** VECTOR's persona system has exactly **one** character (`vector.json`). The repo ships 20+ production-tuned personas (GPT-5.1 candid/professional/cynical/nerdy, Codex friendly/pragmatic, Grok personas). These are concrete, battle-tested tone-calibration templates VECTOR's `tone_adapter` / persona designer can draw on when tuning `vector-focus` or future district-specific personas (coder vs council vs comms).

3. **Agentic-harness design reference.** VECTOR is itself a Claude-Code-style harness. Having the *real* Claude Code, Codex CLI, Gemini CLI, Antigravity, Grok Build prompts on-device is a direct design reference for how to structure tool definitions, system-reminders, memory/context-management blocks, and permission language — useful when VECTOR refines its own modelfiles or its MCP tool descriptions.

**Concrete shape of the integration (small):**
- Vendor the `.md` corpus read-only into `brain/reference/system_prompts/` (or `data/reference_prompts/`) — it's CC0, 6.5 MB, no code, no dependency, no security surface.
- Build a 1-file index/loader (`core/knowledge/prompt_library.py`): walk the folder, parse vendor/model/variant from path, expose `search(query)` and `get(vendor, model)`. Reuse the existing `core/knowledge/` seam (DomainExtractor/WikiParser already live there).
- Wire one optional phase into `prompt-optimizer` SKILL ("pull 2–3 nearest reference prompts as few-shot") and expose one MCP tool (`prompt_library_search`) so VECTOR's own agents can retrieve examples.

**Honest caveats:**
- This is **reference data, not a capability** — it doesn't make VECTOR *do* anything new; it makes its existing prompt/persona tooling better-informed.
- Leaked prompts go **stale fast** (GPT-5.5, Opus 4.8 — versions churn monthly). A vendored snapshot is a point-in-time reference, not a live source. Re-pull periodically or it rots.
- Value is **advisory/design-time**, not runtime. VECTOR will not call these at inference; they're for *you* and the optimizer to learn from.

---

## Section 4 — Verdict: **PATCH VECTOR**

**Reasoning:**

- **Not SAFE TO DELETE.** VECTOR genuinely lacks a reference corpus of real product system prompts. It has its own persona and an internal-only optimizer — there is a real, identifiable gap, and this repo is a high-quality, CC0, exactly-on-target fill (it literally contains the prompts of the harnesses VECTOR imitates).
- **Not INTEGRATE-DIRECTLY-as-a-skill.** Per VECTOR's repo-absorption rule, a data/reference repo is **not** an external skill — it's a corpus. There's no code to absorb and no foreign code to reimplement. "Integrate the whole thing" would just mean dumping 6.5 MB of churning, stale-prone text into the live tree with no loader.
- **PATCH is the right size.** Vendor the corpus into a read-only reference folder + write one small Python loader + one optional optimizer phase + one MCP tool. Low effort, low risk (CC0, no exec, no deps), real upside for the prompt-optimizer and persona systems.

**If you don't care about prompt-engineering polish:** DELETE is defensible — VECTOR already ships and functions with its own persona; this corpus is a *nice-to-have* design reference, not a blocker. It earns PATCH only because it's free, zero-risk, and directly feeds two existing-but-underfed systems (prompt-optimizer + persona library).

**Recommended action:** PATCH — vendor `→ brain/reference/system_prompts/`, add `core/knowledge/prompt_library.py` loader, wire one few-shot phase into `.claude/skills/prompt-optimizer/SKILL.md`, expose `prompt_library_search` MCP tool. ~1 small session. Re-pull the corpus quarterly to avoid rot.
