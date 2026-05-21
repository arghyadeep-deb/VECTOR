# SPEC-13: Codebase Consolidation — 30% File Reduction with Zero Regression

**Status:** Draft  
**Author:** Arghyadeep Deb  
**Project:** VECTOR (Virtual Entity for Cognitive Tasks & Operational Reasoning)  
**Phase:** 1 of 3 — Infrastructure & Core  
**Target Reduction:** 30% (55k → 38.5k files)  
**Timeline:** 4 days / 3 agent sessions  
**Risk Level:** High (import graph surgery on 7,926 .py files)

---

## 1. Problem Statement

The VECTOR codebase grew organically without architectural oversight. What started as an 8-district design ballooned to 55k+ files — 7,926 .py, 19,282 .md. Every new agent session compounds the problem.

### 1.1 Core Problems

**District Explosion:** 49 folder entries under `districts/` from an original 8. Semantic duplicates abound:
- `testing/` and `qa/` overlap ~60%
- `paid_media/` and `marketing/` share ~40% agent templates
- `specialized/` duplicates `skills/`
- `game_development/` belongs in `content/`
- `spatial_computing/` is a 3-file micro-district for `engineering/`
- `academic/` overlaps `research/`
- `sales/` overlaps `agency/`

**Flat Core:** 42 flat modules in `core/`. No package hierarchy. `loop.py`, `brain.py`, `city.py`, `memory.py`, `inference.py`, `voice.py`, `api.py`, `security.py`, `sensing.py`, `engine.py`, `scraper.py`, `research_engine.py`, `coding_assistant.py`, `mcp_server.py` all at the same level. Imports are fragile, refactoring impossible.

**Markdown Graveyard:** 19,282 `.md` files — mostly stale notes in `vectorcode/src/` (19k). A separate 4,444-file brain vault at `C:\Users\Arghyadeep\V.E.C.T.O.R Brain` adds confusion.

**No Dead Code Detection:** Zero automated orphan detection. Files accumulate because deletion is scary.

**Signal-to-Noise Ratio:** Every Claude Code session loads thousands of irrelevant files. Context window fills with dead code.

### 1.2 Why Now

Codebase grows ~200 files/week. Each new module creates cross-imports that compound consolidation difficulty. Phase 2 (cloud API, orchestration) will add 15+ modules. Import rewrites are cheapest in Phase 1 with only 27 tests.

---

## 2. Current State Assessment

### 2.1 File Count by Category

```
Category             | Count       | % Total | Notes
---------------------|-------------|---------|------------------------
Python files (.py)   | 7,926       | 14.4%   | Majority in districts/
Markdown files (.md) | 19,282      | 35.1%   | Mostly vectorcode/src/
JSON/YAML/TOML       | 4,203       | 7.6%    | Configs, logs, data
Other text           | 8,114       | 14.8%   | .txt, .csv, .env*
Binary/images        | 15,475      | 28.1%   | .png, .jpg, .wav, .mp3
---------------------|-------------|---------|------------------------
Total                | 55,000      | 100%    | Approximate
```

### 2.2 District Overlap Analysis

| Pair | Overlap | Action |
|---|---|---|
| `testing/` ↔ `qa/` | ~60% | Merge → `qa/` |
| `paid_media/` ↔ `marketing/` | ~40% | Merge → `marketing/` |
| `specialized/` ↔ `skills/` | ~55% | Merge → `skills/specialties/` |
| `game_development/` ↔ `content/` | ~70% | Merge → `content/games/` |
| `spatial_computing/` ↔ `engineering/` | ~30% | Merge → `engineering/spatial/` |
| `academic/` ↔ `research/` | ~50% | Merge → `research/` |
| `sales/` ↔ `agency/` | ~45% | Merge → `agency/sales/` |

### 2.3 Core Module Analysis

```
core/
├── __init__.py, __main__.py
├── loop.py, brain.py, city.py, memory.py, inference.py
├── voice.py, api.py, security.py, sensing.py, engine.py
├── scraper.py, research_engine.py, coding_assistant.py
├── mcp_server.py, config.py, logger.py, utils.py
├── constants.py, models.py, exceptions.py, database.py
├── cache.py, registry.py, scheduler.py, task_queue.py
├── embeddings.py, vector_store.py, document_parser.py
├── session_manager.py, token_optimizer.py, prompt_builder.py
├── tool_registry.py, plugin_system.py, health_check.py
├── metrics.py, tracing.py, audit.py, backup.py, recovery.py
├── lifecycle.py, version.py
└── total: 42 flat modules
```

### 2.4 Markdown Age Analysis

| Age | Count | Action |
|---|---|---|
| < 30 days | 1,200 | Keep |
| 30-90 days | 3,500 | Keep, review |
| 90-180 days | 7,000 | Archive candidate |
| 180+ days | 7,582 | Strong archive candidate |

### 2.5 Orphan Estimate

~15-20% of .py files have zero incoming project imports. Estimated 800-1,200 orphan files.

### 2.6 Test Baseline

27 tests, pytest, <1% coverage. All must pass after every commit. SPEC-14 handles test coverage.

---

## 3. Target State

### 3.1 Target Directory Tree

```
V.E.C.T.O.R. Codebase/
├── core/
│   ├── __init__.py, __main__.py, config.py, logger.py
│   ├── utils.py, constants.py, exceptions.py, models.py, version.py
│   ├── loop/          {__init__.py, engine.py, scheduler.py, task_queue.py, lifecycle.py}
│   ├── brain/         {__init__.py, cortex.py, registry.py, prompt_builder.py}
│   ├── city/          {__init__.py, config.py, health.py}
│   ├── memory/        {__init__.py, store.py, embeddings.py, vector_store.py, cache.py}
│   ├── inference/     {__init__.py, engine.py, token_optimizer.py, models.py}
│   ├── voice/         {__init__.py, pipeline.py}
│   ├── api/           {__init__.py, routes.py, session_manager.py, health_check.py}
│   ├── security/      {__init__.py, audit.py, backup.py, recovery.py}
│   ├── sensing/       {__init__.py, scraper.py, document_parser.py}
│   ├── engine/        {__init__.py, research.py, coding_assistant.py}
│   ├── research_engine/ {__init__.py, tools.py, metrics.py}
│   └── mcp/           {__init__.py, server.py, tool_registry.py, plugin_system.py, tracing.py}
├── districts/
│   ├── __init__.py, qa/, marketing/, skills/, content/
│   ├── engineering/, research/, agency/ (merged) + remaining originals
├── brain/             (canonical only)
├── docs/              (adr/, agents/, specs/)
├── vectorcode/src/    (not touched in this SPEC)
├── tests/             (27 tests, preserved)
├── .claude/           (unchanged)
├── scripts/           (scanner.py, orphan_detector.py, merger_rules.py, migration_script.py)
├── reports/           (duplicates.json, orphans.json, stale_markdown.json)
└── _archive/          (stale file quarantine)
```

### 3.2 Target Metrics

| Metric | Current | Target | Δ |
|---|---|---|---|
| Python files | 7,926 | ~5,550 | -30% |
| Markdown files | 19,282 | ~13,500 | -30% |
| Total files | 55,000 | ~38,500 | -30% |
| Core flat modules | 42 | 10 packages | -76% |
| District folders | 49 | ~30 | -38% |
| Orphan rate | ~15% | <3% | -80% |

### 3.3 Design Principles

1. **Zero breaking changes** — compatibility stubs at every old import path
2. **Git bisect-safe** — each restructure = exactly one commit
3. **No behavior changes** — purely structural, no logic modified
4. **Archive don't delete** — `_archive/` 30-day quarantine before permanent removal
5. **Semantic package boundaries** — files that change together stay together

---

## 4. Component Breakdown

### 4.1 ScannerAgent — Duplicate Detection

Walks all `.py` files, computes SHA-256 of normalized content, groups by hash for exact duplicates. For district files only, computes Jaccard token-set similarity for fuzzy matches (>0.7 threshold). Outputs `reports/duplicates.json`.

```python
@dataclass
class DuplicateGroup:
    hash: str
    size_bytes: int
    paths: list[str]
    keep: str  # canonical path to retain

@dataclass
class FuzzyMatch:
    path_a: str
    path_b: str
    jaccard: float
    lines_common: int
    lines_total_a: int
    lines_total_b: int
```

Output schema (`duplicates.json`):
```json
{
  "exact_duplicates": [{"hash": "...", "size_bytes": 1234, "paths": ["districts/testing/agent.py", "districts/qa/agent.py"], "keep": "districts/qa/agent.py"}],
  "fuzzy_matches": [{"path_a": "...", "path_b": "...", "jaccard": 0.85, "lines_common": 120, "lines_total_a": 150, "lines_total_b": 140}],
  "summary": {"files_scanned": 7926, "exact_duplicates_found": 450, "fuzzy_matches_found": 320}
}
```

### 4.2 OrphanDetector — Dead Code Detection

Parses all `.py` files with `ast.parse()`, extracts import statements, builds directed graph. Classifies:
- **Type A:** zero incoming edges (never imported)
- **Type B:** zero incoming + zero outgoing (completely disconnected)
- **Type C:** unreachable from entry points via BFS

Outputs `reports/orphans.json`:

```json
{
  "type_a_no_importers": [{"path": "districts/obsolete/x.py", "size_bytes": 2500, "imports_from_project": ["core.utils"]}],
  "type_b_completely_disconnected": [{"path": "districts/old/scratch.py", "size_bytes": 800}],
  "type_c_unreachable": [{"path": "core/experimental/x.py", "size_bytes": 4500}],
  "summary": {"files_analyzed": 7926, "type_a": 450, "type_b": 200, "type_c": 350}
}
```

### 4.3 StaleMarkdownArchiver — Markdown Cleanup

Classifies all `.md` files by mtime and reference count (cross-referenced against .py imports, wiki-links, and git commit history). **Stale:** >180 days, zero references, <3 git commits → archive candidate. Outputs `reports/stale_markdown.json`.

```json
{
  "active": [{"path": "docs/adr/001.md", "mtime": "2026-04-15", "references": 12}],
  "dormant": [{"path": "notes/old.md", "mtime": "2025-11-01", "references": 0}],
  "stale": [{"path": "vectorcode/src/old.md", "mtime": "2025-03-10", "size_bytes": 2500}],
  "summary": {"total_md_files": 19282, "active": 4700, "dormant": 7000, "stale": 7582}
}
```

### 4.4 DistrictMerger — District Consolidation

Executes 7 merge operations with the following conflict protocol:
1. File identical in target → `git rm` source
2. File different in target → `git mv` source → `target/_archive/source/`
3. `__init__.py` conflict → merge exports, keep target's non-export code
4. Unique subdirectory → move as sub-package under target

| Source | Target | Strategy |
|---|---|---|
| `testing/` | `qa/` | Move all, merge __init__ exports |
| `paid_media/` | `marketing/` | Move all, merge __init__ exports |
| `specialized/` | `skills/specialties/` | Nest as sub-package |
| `game_development/` | `content/games/` | Move with game_ prefix |
| `spatial_computing/` | `engineering/spatial/` | Move intact |
| `academic/` | `research/` | Merge paper lists |
| `sales/` | `agency/sales/` | Move, prefix sales files |

### 4.5 CoreRestructurer — Core Package Refactoring

Converts 42 flat modules into 10 bounded sub-packages. Each old module becomes a compatibility stub that re-exports from the new package.

| Old Module(s) | New Package | New Files |
|---|---|---|
| `loop.py` | `core/loop/` | `__init__.py`, `engine.py`, `scheduler.py`, `task_queue.py`, `lifecycle.py` |
| `brain.py` | `core/brain/` | `__init__.py`, `cortex.py`, `registry.py`, `prompt_builder.py` |
| `city.py` | `core/city/` | `__init__.py`, `config.py`, `health.py` |
| `memory.py`, `embeddings.py`, `vector_store.py`, `cache.py` | `core/memory/` | `__init__.py`, `store.py`, `embeddings.py`, `vector_store.py`, `cache.py` |
| `inference.py`, `token_optimizer.py` | `core/inference/` | `__init__.py`, `engine.py`, `token_optimizer.py`, `models.py` |
| `voice.py` | `core/voice/` | `__init__.py`, `pipeline.py` |
| `api.py`, `session_manager.py`, `health_check.py` | `core/api/` | `__init__.py`, `routes.py`, `session_manager.py`, `health_check.py` |
| `security.py`, `audit.py`, `backup.py`, `recovery.py` | `core/security/` | `__init__.py`, `audit.py`, `backup.py`, `recovery.py` |
| `sensing.py`, `scraper.py`, `document_parser.py` | `core/sensing/` | `__init__.py`, `scraper.py`, `document_parser.py` |
| `engine.py`, `research_engine.py`, `coding_assistant.py` | `core/engine/` | `__init__.py`, `research.py`, `coding_assistant.py` |
| `mcp_server.py`, `tracing.py`, `metrics.py` | `core/mcp/` | `__init__.py`, `server.py`, `tool_registry.py`, `plugin_system.py`, `tracing.py` |

Stub pattern (old location forwards to new):
```python
# core/loop.py — compatibility stub, NOT deleted
from core.loop.engine import *  # noqa: F401, F403
```

### 4.6 MigrationScriptWriter — Automated Import Rewriting

Uses AST-based rewriting (not regex) to update all import statements across the codebase. Core dataclasses:

```python
@dataclass
class ImportRewrite:
    old_path: str          # "core.loop"
    new_path: str          # "core.loop.engine"
    old_symbols: list[str]
    new_symbols: list[str]

def build_import_map(file_moves: list[FileMove]) -> ImportMap:
    """Reverse-map every file move to import rewrites.
    district.old_path → district.new_path for each rename."""
    # returns ImportMap {rewrites: [ImportRewrite, ...]}

def rewrite_file(path: Path, import_map: ImportMap) -> int:
    """AST-based import rewriting. Returns count of changes.
    Handles: import X, from X import Y, from X import Y as Z, import X as Y.
    Does NOT handle: __import__, importlib.import_module (flagged for manual review)."""
```

Generated rewrite map and PowerShell script for execution. Dry-run mode produces `reports/dry_run_report.json` for review before applying.

---

## 5. Agent Dispatch Plan

### 5.1 Agent A — Analysis (1 day)

**Branch:** `spec-13-analysis` — pure read-only, no file mutations.

| Task | Tool | Output |
|---|---|---|
| Run ScannerAgent | `scripts/scanner.py` | `reports/duplicates.json` |
| Run OrphanDetector | `scripts/orphan_detector.py` | `reports/orphans.json` |
| Run StaleMarkdownArchiver | `scripts/scanner.py --md` | `reports/stale_markdown.json` |
| Build import graph | `orphan_detector.py --graph` | `reports/import_graph.dot` |
| Analyze overlaps | `scripts/analyze_overlaps.py` | `reports/merger_rules.json` |
| Summary report | manual | `reports/analysis_summary.md` |

**Verification:** All 4 JSON files exist and parse. Zero file moves or deletions.

### 5.2 Agent B — Consolidation (2 days)

**Branch:** `spec-13-consolidation` (base: `spec-13-analysis`)

| Commit | Action | Files |
|---|---|---|
| 1 | Merge `testing/` → `qa/` | ~40 |
| 2 | Merge `paid_media/` → `marketing/` | ~25 |
| 3 | Merge `specialized/` → `skills/` | ~30 |
| 4 | Merge `game_development/` → `content/` | ~15 |
| 5 | Merge `spatial_computing/` → `engineering/` | ~3 |
| 6 | Merge `academic/` → `research/` | ~20 |
| 7 | Merge `sales/` → `agency/` | ~15 |
| 8 | Create `core/loop/` | 5 modules + 1 stub |
| 9 | Create `core/brain/` | 4 modules + 1 stub |
| 10 | Create `core/memory/` | 5 modules + 1 stub |
| 11 | Create `core/inference/` | 4 modules + 1 stub |
| 12 | Create `core/voice/`, `core/api/`, `core/security/` | 10 modules + 3 stubs |
| 13 | Create `core/sensing/`, `core/engine/`, `core/research_engine/` | 7 modules + 3 stubs |
| 14 | Create `core/mcp/` | 5 modules + 1 stub |
| 15 | Update `core/__init__.py`, `districts/__init__.py` | 2 files |

**Verification:** `python -c "import core"` succeeds after every commit.

### 5.3 Agent C — Cleanup (1 day)

**Branch:** `spec-13-cleanup` (base: `spec-13-consolidation`)

| Commit | Action |
|---|---|
| 1 | Rewrite all imports — run `scripts/rewrite_imports.ps1` |
| 2 | Archive stale markdown — move ~7,500 files to `_archive/` |
| 3 | Delete Type-B orphans — ~200 files |
| 4 | Delete exact duplicates — ~450 files |
| 5 | Run all 27 tests — `python -m pytest tests/` |
| 6 | Full smoke test — `python -c "import core; import districts;"` |
| 7 | Final audit — compare before/after metrics |

**Verification:** All 27 tests pass. File count shows 30% reduction.

---

## 6. Implementation Steps

### 6.1 Phase 1: Analysis (Agent A — Day 1)

**Step 1 — Set up tools.** Create `scripts/__init__.py`. Write `scanner.py` (ScannerAgent + StaleMarkdownArchiver), `orphan_detector.py` (OrphanDetector + import graph), `merger_rules.py` (DistrictMerger + CoreRestructurer rules), `analyze_overlaps.py`.

**Step 2 — Run ScannerAgent.** `python scripts/scanner.py --output reports/duplicates.json`. Scans 7,926 files in ~5-10 min.

**Step 3 — Run OrphanDetector.** `python scripts/orphan_detector.py --output reports/orphans.json`. Parses all .py with ast, ~10-15 min.

**Step 4 — Run StaleMarkdownArchiver.** `python scripts/scanner.py --md --output reports/stale_markdown.json`.

**Step 5 — Run overlap analysis.** `python scripts/analyze_overlaps.py --output reports/merger_rules.json`.

### 6.2 Phase 2: District Mergers (Agent B — Days 2-3)

**Step 6 — Merge testing/ → qa/.** For each file in `districts/testing/`: if byte-identical to `districts/qa/` → `git rm`, else `git mv` to `districts/qa/from_testing_*`. Update `qa/__init__.py`. Create compat stub `testing/__init__.py` → `from districts.qa import *`. Commit: `consolidate(testing): merge testing/ into qa/`.

**Step 7 — Merge paid_media/ → marketing/.** Same pattern. Campaign files prefixed with `paid_`. Commit: `consolidate(paid_media): merge paid_media/ into marketing/`.

**Step 8 — Merge specialized/ → skills/.** Create `skills/specialties/`. `git mv specialized/* skills/specialties/`. Commit: `consolidate(specialized): merge specialized/ into skills/specialties/`.

**Step 9 — Merge game_development/ → content/.** Create `content/games/`. `git mv game_development/*.py content/games/`. Commit: `consolidate(game_dev): merge game_development/ into content/games/`.

**Step 10 — Merge spatial_computing/ → engineering/.** Move to `engineering/spatial/`. Commit: `consolidate(spatial): merge spatial_computing/ into engineering/spatial/`.

**Step 11 — Merge academic/ → research/.** Move files, resolve duplicate paper lists (keep research's). Commit: `consolidate(academic): merge academic/ into research/`.

**Step 12 — Merge sales/ → agency/.** Create `agency/sales/`. Commit: `consolidate(sales): merge sales/ into agency/sales/`.

### 6.3 Phase 3: Core Restructure (Agent B — Days 2-3, continued)

**Step 13 — Create core/loop/ package.** Split `loop.py` into `core/loop/__init__.py`, `engine.py` (Loop class), `scheduler.py` (Scheduler), `task_queue.py` (TaskQueue), `lifecycle.py` (Lifecycle). Stub `core/loop.py` → `from core.loop.engine import *`. Commit: `refactor(core): create core/loop/ package`.

**Step 14 — Create core/brain/ package.** Split `brain.py` into cortex, registry, prompt_builder. Stub. Commit: `refactor(core): create core/brain/ package`.

**Step 15 — Create core/memory/ package.** Merge `memory.py`, `embeddings.py`, `vector_store.py`, `cache.py` into `core/memory/`. Stubs at all 4 old paths. Commit: `refactor(core): create core/memory/ package`.

**Step 16 — Create core/inference/ package.** Split `inference.py` + `token_optimizer.py` into `core/inference/`. Commit: `refactor(core): create core/inference/ package`.

**Step 17 — Create voice/, api/, security/ packages.** Split `voice.py`, `api.py`, `security.py` into respective subdirs. Stubs. Commit: `refactor(core): create voice/, api/, security/ packages`.

**Step 18 — Create sensing/, engine/, research_engine/ packages.** Split sensing/scraper/document_parser, engine/research/coding_assistant, research_engine into packages. Stubs. Commit: `refactor(core): create sensing/, engine/, research_engine/ packages`.

**Step 19 — Create core/mcp/ package.** Split `mcp_server.py` + `tracing.py` + `metrics.py` into `core/mcp/`. Commit: `refactor(core): create core/mcp/ package`.

**Step 20 — Update core/__init__.py.** Rewrite all 42 re-exports to point at sub-packages. Flat modules (config, logger, utils, constants, exceptions, models, version) stay as direct imports.

**Step 21 — Update districts/__init__.py.** Remove merged-district re-exports, add target-district re-exports.

**Overlap analysis cross-check:** Before executing any merge, Agent B must cross-reference `reports/duplicates.json` (exact+ fuzzy duplicates) with `reports/merger_rules.json` (intended merges). If a fuzzy match has jaccard >0.85, the merge is mandatory. If jaccard <0.4, reconsider whether the districts should merge at all.

**Git workflow for Agent B:** Each commit must be signed (`git commit -S`) with message format `type(scope): description` matching existing VECTOR conventions. After every 3 commits, run `python -c "import core; import districts"` as a canary check. If it fails, the last 3 commits must be investigated before proceeding.

### 6.4 Phase 4: Import Rewriting + Verification (Agent C — Day 4)

**Step 22 — Generate rewrite map.** `python scripts/migration_script.py --generate-map` → `scripts/import_rewrite_map.json`.

**Step 23 — Dry-run.** `python scripts/migration_script.py --dry-run` → `reports/dry_run_report.json`. Review for dangerous rewrites.

**Step 24 — Execute rewrites.** `python scripts/migration_script.py --execute`. Rewrites all import statements across ~5,500 .py files. Leaves stubs intact. Commit: `fix(imports): rewrite all import paths for new layout`.

**Step 25 — Archive stale markdown.** Create `_archive/`. `git mv` each stale entry from `reports/stale_markdown.json`. Exclude `.claude/`, `docs/adr/`, `CLAUDE.md`, `CONTEXT.md`. Commit: `cleanup(archive): move stale markdown files to _archive/`.

**Step 26 — Delete Type-B orphans.** `git rm` for each file in `orphans.json` with type_b. ~200 files. Commit: `cleanup(orphans): remove Type-B orphan files`.

**Step 27 — Delete exact duplicates.** For each group in `duplicates.json`, keep canonical, delete rest. ~450 files. Commit: `cleanup(duplicates): remove exact duplicate files`.

**Step 28 — Run all 27 tests.** `python -m pytest tests/ -v`. Fix any import-related failures immediately.

**Step 29 — Full smoke test.** Verify `import core`, `import districts`, `from core.loop import Loop`, `from core.mcp import MCPServer`, `from districts.qa import QAAgent` all resolve.

**Step 30 — Final audit.** Count remaining files, confirm 30% reduction. Write `reports/consolidation_summary.md`. Commit: `docs(reports): add consolidation summary`.

---

## 7. Files to Create/Modify

### 7.1 Files to Create

| Path | Purpose | Agent |
|---|---|---|
| `scripts/__init__.py` | Package init | A |
| `scripts/scanner.py` | ScannerAgent + StaleMarkdownArchiver | A |
| `scripts/orphan_detector.py` | OrphanDetector + import graph | A |
| `scripts/merger_rules.py` | DistrictMerger + CoreRestructurer rules | A |
| `scripts/analyze_overlaps.py` | Fuzzy overlap analysis | A |
| `scripts/migration_script.py` | Import rewriting engine | B |
| `scripts/rewrite_imports.ps1` | Generated rewrite script | C |
| `scripts/import_rewrite_map.json` | Import path mapping | B |
| `reports/duplicates.json` | ScannerAgent output | A |
| `reports/orphans.json` | OrphanDetector output | A |
| `reports/stale_markdown.json` | Archiver output | A |
| `reports/merger_rules.json` | Merge rules | A |
| `reports/analysis_summary.md` | Analysis summary | A |
| `reports/dry_run_report.json` | Dry-run report | C |
| `reports/consolidation_summary.md` | Final summary | C |
| `_archive/` | Stale file quarantine dir | C |

### 7.2 Files to Create (~70 core package files)

| Package | Files |
|---|---|
| `core/loop/` | `__init__.py`, `engine.py`, `scheduler.py`, `task_queue.py`, `lifecycle.py` |
| `core/brain/` | `__init__.py`, `cortex.py`, `registry.py`, `prompt_builder.py` |
| `core/memory/` | `__init__.py`, `store.py`, `embeddings.py`, `vector_store.py`, `cache.py` |
| `core/inference/` | `__init__.py`, `engine.py`, `token_optimizer.py`, `models.py` |
| `core/voice/`, `core/api/`, `core/security/` | 9 files + 3 `__init__.py` |
| `core/sensing/`, `core/engine/`, `core/research_engine/` | 7 files + 3 `__init__.py` |
| `core/mcp/` | `__init__.py`, `server.py`, `tool_registry.py`, `plugin_system.py`, `tracing.py` |

### 7.3 Files to Modify

| Path | Risk | Change |
|---|---|---|
| `core/__init__.py` | High | Rewrite all 42 re-exports for new packages |
| `districts/__init__.py` | High | Remove merged-district exports |
| All remaining .py (~5,500) | High | Import path rewrites |
| `tests/*.py` | Medium | Fix test import paths |
| `.claude/rules/brain_index.md`, `CONTEXT.md`, `CLAUDE.md` | Low | Update directory references |

### 7.4 Files to Delete (NOT compatibility stubs — stubs are preserved)

| Category | Count | Condition |
|---|---|---|
| Type-B orphan .py | ~200 | Zero incoming + zero outgoing import edges |
| Exact duplicate .py | ~450 | Byte-identical, confirmed by SHA-256 |
| Stale .md → `_archive/` | ~7,500 | >180 days, zero references, <3 commits |

Compatibility stubs (e.g., `core/loop.py` as a forwarding module) are NOT deleted. They remain until SPEC-14.

---

## 8. Success Criteria

### 8.1 Mandatory Gates

| # | Criterion | Verification |
|---|---|---|
| 1 | File reduction ≥ 30% | `(55k - final) / 55k * 100 ≥ 30` |
| 2 | Zero import errors | `python -c "import core; import districts"` → exit 0 |
| 3 | All 27 tests pass | `python -m pytest tests/ -v` → all green |
| 4 | Deep imports resolve | `from core.loop import Loop; from core.mcp import MCPServer` |
| 5 | Merged district imports resolve | `from districts.qa import QAAgent` |
| 6 | Old import paths still work via stubs | `from core.loop import Loop` (triggers stub) |
| 7 | Git bisect-safe | Each restructure = exactly 1 commit |
| 8 | No new linter warnings | `ruff check core/ districts/` |
| 9 | Security scan passes | `.claude/` → no new injection risks |

### 8.2 Quality Gates

| # | Criterion |
|---|---|
| 1 | Import graph depth ≤ 3 packages |
| 2 | No `_*` private names in package exports |
| 3 | No circular imports (`import core` doesn't chain-ImportError) |
| 4 | Archive reversible: `git checkout main -- _archive/` restores all files |

### 8.3 Regression Prevention

Every symbol defined in an old flat file must be re-exported from the new package's `__init__.py`. Every `git mv`'d file must have internal self-imports updated. Old paths get one-line stubs:

```python
# compatibility stub
from core.loop.engine import *  # noqa: F401, F403
```

### 8.4 Rollback Plan

`git checkout main` → full rollback to 55k files, original imports, unarchived markdown. Rollback threshold: if >5% of files fail import rewriting, abort and re-plan with conservative merge rules.

---

## 9. Dependencies

### 9.1 Required Tools

| Tool | Purpose |
|---|---|
| Python 3.11+ | All scripts |
| `ast` (stdlib) | Import parsing |
| `hashlib` (stdlib) | SHA-256 hashing |
| `json`, `pathlib` (stdlib) | Report serialization, paths |
| `networkx` (optional) | Import graph visualization |
| Git 2.40+ | File moves, commits |
| PowerShell 5.1+ | Rewrite script execution |
| pytest 7.0+ | Test runner |

### 9.2 External Packages — NONE

Core logic uses only Python stdlib: `ast`, `hashlib`, `pathlib`, `json`. Optional `networkx` for DOT graph export.

### 9.3 System Resources

5 GB free disk, 8 GB RAM, ~4 hours CPU time (I/O bound).

### 9.4 Performance Budget

Each script execution has a maximum time budget:
- `scanner.py` (hash scan): 10 minutes for 7,926 files
- `orphan_detector.py` (AST parse + graph build): 15 minutes
- `stale_markdown_archiver.py` (mtime + reference scan): 8 minutes
- `analyze_overlaps.py`: 5 minutes
- `migration_script.py --execute`: 10 minutes
- `python -m pytest tests/`: 30 seconds

If any script exceeds its budget by 2x, investigate for infinite loops or I/O bottlenecks before retrying.

### 9.5 Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Import rewrite misses edge case | Medium | Compatibility stubs at every old path |
| Circular import from package split | Low | Test after each commit, plan boundaries carefully |
| Large file count slows git | Low | ~50 files per commit, manageable |
| OrphanDetector false positives | Medium | Only auto-delete Type-B (no edges at all). Type-A/C require human review. |
| Stale markdown referenced by string | Medium | Cross-reference scanner checks .py for markdown path strings |

---

## Appendix A: Import Category Handling Matrix

| Pattern | Example | Rewrite | Risk |
|---|---|---|---|
| Direct | `import core.loop` | `import core.loop.engine` | Low |
| From-specific | `from core.loop import Loop` | `from core.loop.engine import Loop` | Low |
| From-star | `from core.loop import *` | `from core.loop.engine import *` | Low |
| Relative | `from .loop import Loop` | `from .loop.engine import Loop` | Medium |
| Dynamic | `importlib.import_module("core.loop")` | Flag for manual review | High |
| String | `__import__("core.loop")` | Flag for manual review | High |
| Re-export | `from .loop import Loop` in `__init__.py` | Must re-export from new location | High |

Dynamic/string imports are <1% of codebase and handled via manual review reports.

## Appendix B: Core Package Splitting Rationale

**`core/loop/`** — `loop.py` has 4 responsibilities (Loop orchestration, Scheduler, TaskQueue, Lifecycle hooks) used by different clients. `core/__main__.py` uses only Loop; `city.py` uses only Scheduler; districts use Lifecycle hooks. Splitting eliminates unnecessary transitive imports.

**`core/brain/`** — Brain has 3 responsibilities (Cortex reasoning, AgentRegistry at startup, PromptBuilder used by every district). Splitting breaks the dependency chain so district files importing PromptBuilder don't transitively import Cortex.

**`core/memory/`** — Memory, embeddings, vector_store, and cache are always imported together (any file using one usually uses all four). Merging into a single package reduces flat-file clutter without changing import granularity.

**`core/mcp/`** — MCP server, tool registry, plugin system, and tracing form a natural dependency unit. All are used by the MCP subsystem and rarely imported individually.

## Appendix C: Verification Script

Run this after all 30 steps to confirm zero regression:

```powershell
Write-Host "=== SPEC-13 Final Verification ==="

# 1. Import check
python -c "import core; import districts; print('PASS: import core, districts')"
python -c "from core.loop import Loop, Scheduler; from core.brain import Cortex; from core.memory import MemoryStore; from core.mcp import MCPServer; print('PASS: deep imports')"
python -c "from districts.qa import QAAgent; from districts.marketing import CampaignManager; from districts.skills import SkillRegistry; from districts.content import ContentGenerator; from districts.engineering import SpatialProcessor; from districts.research import PaperIndexer; from districts.agency import SalesPipeline; print('PASS: merged district imports')"

# 2. Old compat stubs still work
python -c "from core.loop import Loop; print('PASS: compat stub core.loop')"

# 3. All tests pass
python -m pytest tests/ -v --tb=short

# 4. File count reduction
$before = 55000
$after = (Get-ChildItem -Recurse -File | Measure-Object).Count
$reduction = [math]::Round(($before - $after) / $before * 100, 1)
Write-Host "Reduction: ${reduction}% (${before} → ${after})"
if ($reduction -ge 30) { Write-Host "PASS: 30% reduction target met" }
else { Write-Host "FAIL: reduction target not met"; exit 1 }

Write-Host "=== VERIFICATION COMPLETE ==="
```

---

**End of SPEC-13**  
*Target: 30% file reduction (55k → 38.5k) — 4 days / 3 agents — zero regression guaranteed by compatibility stubs*
