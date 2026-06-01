# obsidian-mind-main Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\obsidian-mind-main`
**Audit date:** 2026-06-01
**Auditor:** Claude Sonnet 4.6
**Memory log claim:** "obsidian-mind: brain vault hooks" (absorbed 2026-05-19)

---

## 1. Repo Reality

obsidian-mind (MIT, by Brenno Ferrari) is a Claude Code-native Obsidian vault template
that gives AI coding agents persistent cross-session memory. It is NOT an Obsidian plugin
and has zero Python code — it is entirely TypeScript hook scripts + Markdown command/agent
definitions + a structured vault layout.

### Concrete features

**5 lifecycle hooks (TypeScript, Node 22+):**
- `SessionStart` — on startup: QMD re-index (fire-and-forget), inject ~2K tokens of context
  (date, North Star excerpt, brain-topics index, git log last 48h, open tasks, active work,
  full vault file listing). Reads `brain/North Star.md`, `work/active/`, `vault-manifest.json`.
- `UserPromptSubmit` — every message: classify prompt type (decision / incident / win / 1:1 /
  architecture / person / project update) and inject routing hints (~100 tokens).
- `PostToolUse` (Write|Edit) — after every markdown write: validate frontmatter fields
  (`date`, `tags`, `description`) and check for `[[wikilinks]]`.
- `PreCompact` — before context compaction: back up session transcript to `thinking/session-logs/`.
- `Stop` — end of session: checklist (archive completed, update indexes, check orphans).

**18 slash commands** (Markdown agent instructions, no code):
`/om-standup`, `/om-dump`, `/om-wrap-up`, `/om-humanize`, `/om-weekly`,
`/om-capture-1on1`, `/om-incident-capture`, `/om-slack-scan`, `/om-peer-scan`,
`/om-review-brief`, `/om-self-review`, `/om-review-peer`, `/om-vault-audit`,
`/om-vault-upgrade`, `/om-prep-1on1`, `/om-meeting`, `/om-intake`, `/om-project-archive`

**9 subagents** (Markdown Claude Code agents, no code):
`brag-spotter`, `context-loader`, `cross-linker`, `people-profiler`,
`review-prep`, `review-fact-checker`, `slack-archaeologist`, `vault-librarian`,
`vault-migrator`

**Vault structure:**
- `work/` — active projects, archive, incidents, 1:1 notes, meetings inbox
- `org/` — people notes, team notes (`People & Context.md` MOC)
- `perf/` — Brag Doc, quarterly brag notes, competency notes, review evidence, cycles
- `brain/` — North Star, Memories index, Key Decisions, Patterns, Gotchas, Skills
- `bases/` — 7 Obsidian Bases (database views): Work Dashboard, Incidents, People
  Directory, 1:1 History, Review Evidence, Competency Map, Templates
- `templates/` — 6 YAML-frontmatter templates: Work Note, Decision Record, Thinking,
  Competency, 1:1, Incident
- `reference/` — codebase knowledge, architecture maps
- `thinking/` — scratchpad (promote findings, then delete)

**QMD integration (optional):** Semantic search via `qmd` CLI / MCP server. Named index
per vault via `vault-manifest.json`. Registered in `.mcp.json` as MCP tools.

**ShardMind installer (npm):** Template package manager with wizard, optional modules, and
three-way-merge upgrades. Additive — vault works without it.

---

## 2. VECTOR Parity

The memory log claim "brain vault hooks" is **accurate but incomplete**. The hook scripts
were ported, but several high-value features were left unabsorbed.

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| SessionStart hook (TypeScript) | `core/brain_hooks/scripts/session-start.ts` | Module imports OK; `vault_stats()` returns 44 commands, 38 agents, 361 skills, 1503 MD files | ✅ real |
| UserPromptSubmit classifier | `core/brain_hooks/scripts/classify-message.ts` | File present, mirrors obsidian-mind source | ✅ real |
| PostToolUse frontmatter validator | `core/brain_hooks/scripts/validate-write.ts` | File present | ✅ real |
| PreCompact session backup | `core/brain_hooks/scripts/pre-compact.ts` | File present | ✅ real |
| Stop checklist hook | `core/brain_hooks/scripts/stop-checklist.ts` | File present | ✅ real |
| QMD refresh hook | `core/brain_hooks/scripts/qmd-refresh.ts` | File present | ✅ real |
| `core/brain_hooks/__init__.py` Python wrapper | `core/brain_hooks/__init__.py` | `vault_stats()` runs, `run_hook()` callable | ✅ real |
| Hook scripts wired to Brain vault | Brain vault `.claude/settings.json` | **NOT FOUND** — no `settings.json` in Brain `.claude/`; hook scripts exist in codebase but are not installed as hooks in the live vault | ⚠️ stub |
| 18 slash commands (om- prefix) | Brain vault `.claude/commands/` | 6 of 18 renamed present: `standup.md`, `wrap-up.md`, `weekly.md`, `review-brief.md`, `vault-audit.md`, `vault-upgrade.md` — **12 missing** (`om-dump`, `om-humanize`, `om-capture-1on1`, `om-incident-capture`, `om-slack-scan`, `om-peer-scan`, `om-self-review`, `om-review-peer`, `om-prep-1on1`, `om-meeting`, `om-intake`, `om-project-archive`) | ⚠️ partial |
| 9 subagents | Brain vault `.claude/agents/` | All 9 present: `brag-spotter.md`, `context-loader.md`, `cross-linker.md`, `people-profiler.md`, `review-prep.md`, `review-fact-checker.md`, `slack-archaeologist.md`, `vault-librarian.md`, `vault-migrator.md` | ✅ real |
| Vault structure (work/org/perf/brain) | Brain vault root | `work/` (active, archive, incidents, 1-1, meetings), `org/` (people, teams), `perf/` (brag, competencies, evidence), `brain/` all present | ✅ real |
| Bases (7 database views) | Brain vault `bases/` | 7 `.base` files present: Work Dashboard, Incidents, People Directory, 1-1 History, Review Evidence, Competency Map, Templates | ✅ real |
| QMD semantic search wiring | Brain vault `vault-manifest.json` | File present with `qmd_index: "vector-brain"` | ✅ real |
| ConsolidationBot (episodic → semantic) | `districts/memory_curator/consolidation_bot.py` | **BROKEN** — `AttributeError: 'ConsolidationBot' object has no attribute 'subscribe_to'`; `AgentBase` has no `subscribe_to` method | ⚠️ broken |
| PatternFinder | `districts/memory_curator/pattern_finder.py` | Instantiates OK: `PatternFinder hp=500` | ✅ real |
| JournalWriter | `districts/reflection/journal_writer.py` | Instantiates OK: `JournalWriter` | ✅ real |
| ZKSteward (Zettelkasten) | `districts/personal_growth/zk_steward.py` | Instantiates OK; `scan_vault_notes()`, `extract_concepts()`, `insert_backlinks()`, `generate_index_note()` all present | ✅ real |
| ObsidianSync write_note | `core/memory/obsidian_sync.py` | Instantiates OK; vault path = `V.E.C.T.O.R. Brain`; methods: `write_note`, `append_to_note`, `write_note_via_gateway`, `query`, `ingest_existing`, `start_watching` | ✅ real |
| Performance graph (competency backlinks, brag doc, review brief) | Brain vault `perf/` structure | Structure present; automated tracking relies on commands — 6/18 commands present | ⚠️ partial |
| Vault migration (`/om-vault-upgrade`) | Brain vault `vault-upgrade.md` command | Command file present (6/18 set) | ✅ real |
| Obsidian Skills (obsidian-markdown, obsidian-cli, obsidian-bases, json-canvas, defuddle, qmd) | Brain vault `.claude/skills/` | `vault_stats()` reports 361 skills directories — includes these | ✅ real |
| ZKSteward vault path points to correct Brain | `zk_steward.py` line 32 | **WRONG PATH** — reads `C:\Users\Arghyadeep\V.E.C.T.O.R Brain` (missing `Desktop\V.E.C.T.O.R\` prefix); vault is at `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain` | ⚠️ broken |

---

## 3. Frontend / Panel spec

obsidian-mind is vault-based, not a web UI. Its "dashboard" is Obsidian itself:

**Home.md** — vault entry point, embeds all 7 Base views via Obsidian's Bases core plugin.

**7 Base views** (`.base` files, Obsidian-native database views — not web panels):
| Base | Filters | Grouping |
|------|---------|---------|
| Work Dashboard | Active projects, current quarter | Grouped by status |
| Incidents | All incidents | Sorted by severity + date |
| People Directory | `org/people/` | Role, team columns |
| 1:1 History | `work/1-1/` | Sortable by person + date |
| Review Evidence | `perf/evidence/` | Grouped by person + cycle |
| Competency Map | `perf/competencies/` | Evidence count from backlinks |
| Templates | `templates/` | Quick access |

**HUD potential:** These Base views could be scraped by VECTOR's reflection/intelligence
districts to surface: blocked projects, overdue 1:1s, competency coverage gaps, and
uncaptured wins — without needing a web dashboard. The data already exists in the vault;
it's a read-path integration.

**No web dashboard.** There is no HTML/CSS/JS. The only "UI" is Obsidian's desktop app.

---

## 4. Verdict

**Absorption claim: PARTIAL — 70% complete.**

What was done well:
- All 5 TypeScript hook scripts ported into `core/brain_hooks/scripts/` with a Python
  wrapper module
- All 9 obsidian-mind subagents installed in Brain vault `.claude/agents/`
- Full vault structure (work/org/perf/brain/bases) installed in Brain vault
- All 7 Obsidian Base views installed
- ZKSteward, PatternFinder, JournalWriter, ObsidianSync all real Python agents
- QMD integration wired via `vault-manifest.json`

What was missed or broken:
1. **Hooks not live:** Brain vault has no `.claude/settings.json` — the 5 TypeScript
   hook scripts sit in the codebase but are not actually wired as hooks in the vault
   where Claude Code runs. They will never fire automatically.
2. **12 of 18 commands missing** from Brain vault: all capture/intake/review/prep commands
   absent. Only the 6 core daily workflow commands are present.
3. **ConsolidationBot broken:** `AttributeError: 'ConsolidationBot' object has no attribute
   'subscribe_to'` — `AgentBase` was refactored but `consolidation_bot.py` still calls
   the removed `subscribe_to()` method at line 49.
4. **ZKSteward wrong vault path:** hardcoded `C:\Users\Arghyadeep\V.E.C.T.O.R Brain`
   (typo — missing `Desktop\V.E.C.T.O.R\`) means `scan_vault_notes()` always returns 0
   notes on this machine.

---

## 5. Gaps

| # | Issue | Location | Type | Status |
|---|-------|----------|------|--------|
| G1 | Brain vault missing `.claude/settings.json` — all 5 hook scripts are never wired; SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop hooks do not fire | `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\.claude\` | Bug (activation gap) | ❌ not fixed |
| G2 | ConsolidationBot crashes at init: `AgentBase` has no `subscribe_to()` method | `districts/memory_curator/consolidation_bot.py:49-50` | Bug (broken) | ❌ not fixed |
| G3 | ZKSteward vault path wrong — `C:\Users\Arghyadeep\V.E.C.T.O.R Brain` vs actual `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain` — `scan_vault_notes()` silently returns 0 every run | `districts/personal_growth/zk_steward.py:32` | Bug (wrong path) | ❌ not fixed |
| G4 | 12 of 18 obsidian-mind slash commands missing from Brain vault: `dump`, `humanize`, `capture-1on1`, `incident-capture`, `slack-scan`, `peer-scan`, `self-review`, `review-peer`, `prep-1on1`, `meeting`, `intake`, `project-archive` | `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\.claude\commands\` | Missing absorption | ❌ not fixed |
| G5 | Hook scripts in `core/brain_hooks/scripts/` are a codebase copy, not the source of truth. If obsidian-mind releases a new version, Brain vault would need manual sync. No auto-update mechanism exists. | `core/brain_hooks/scripts/` | Architecture gap | ⚠️ deferred |
| G6 | `context_compressor.py` in `memory_curator/` exists but has no counterpart in obsidian-mind (was it a VECTOR original or from another source?) — not a gap but worth verifying in next audit | `districts/memory_curator/context_compressor.py` | Low priority | N/A |
| G7 | ZKSteward uses `CONFIG.get("paths", {}).get("obsidian_vault", ...)` but config key path may not match what `obsidian_sync.py` uses (`CONFIG["vault_path"]`) — two different config lookups for the same vault path | `districts/personal_growth/zk_steward.py:32` vs `core/memory/obsidian_sync.py:30` | Config inconsistency | ⚠️ minor |

### Fix priority

**Immediate (blocks autonomous operation):**
- G2 — ConsolidationBot crashes on every VECTOR startup that routes to memory_curator
- G3 — ZKSteward silently does nothing on every run
- G1 — Without `settings.json`, VECTOR never gets automatic session context injection

**Short-term (completes absorption):**
- G4 — Install remaining 12 commands to Brain vault `.claude/commands/`

**Low priority:**
- G5, G7 — architectural housekeeping, does not block operation
