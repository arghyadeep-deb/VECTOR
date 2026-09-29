# VECTOR's skills system — investigation, a real bug fix, and SkillBuilder

Owner request, 2026-09-30: "build a skills section for VECTOR which claude has in it
for claude's use as well as a skill builder according to a use of repeated task."

## What was found before anything was built

VECTOR does not lack a skills system. It has **five separate, non-unified ones**,
built at different times by different absorptions, none of which talk to each other:

1. `core/coding_assistant/core/skills/` — a full, real, Claude-Code-compatible
   `SkillManager`/`SkillMetadata`/`SkillInfo`/parser (from the OpenJarvis "VectorAgent
   SDK" absorption). Discovers `SKILL.md` files with the exact same frontmatter shape
   Claude Code itself uses (`name`, `description`, `license`, `compatibility`,
   `allowed-tools`, `user-invocable`). Requires a `VectorCAConfig` and an explicitly
   initialized `HarnessFilesManager` singleton to construct — infrastructure VECTOR's
   own runtime never sets up.
2. `vectorcode/src/skills/` — its own independent `load_skill()`/loader, with its own
   tests (`tests/test_skill_scanner_failclosed.py`).
3. `districts/marketing/_skill_loader.py` — the marketing district's own loader, used
   directly by 10+ agents (`seo_agent`, `growth_hacker`, `content_creator`,
   `google_ads_agent`, ...). Real, working, load-bearing.
4. `districts/investment/vector_backtest/` — a fully self-contained sub-application
   with its own agent/tool framework, including `src/tools/skill_writer_tool.py`: a
   real, working `save_skill`/`patch_skill`/`delete_skill`/`skill_file` CRUD toolset.
   This is the closest existing thing to a "skill builder," but it is **manual**: an
   LLM operating that sub-tool decides to call `save_skill` with hand-written content.
   It does not detect repetition on its own.
5. `districts/intelligence/vectorintel_agent.py` — its own single-purpose
   `_load_skill()`.

None of these were touched or unified in this pass — that would be a much larger,
riskier refactor than what was asked, and several (marketing's, investment's) are
already load-bearing and working. This pass fixed the one broken, governor-wired path
and added the one genuinely missing piece: a builder that reacts to real repetition.

## A real, three-layer bug found and fixed

`districts/coding/coding_tools.py::load_skill()` is wired through the governor as a
real dispatchable action (`"load_skill": "coding"` in `core/city/governor.py`,
`"load_skill"` in `core/config.py`'s GREEN tier) — but it had never worked:

1. `from core.coding_assistant.core.paths import GLOBAL_SKILLS_DIR` — that module does
   not exist (the real path utilities live at `core/coding_assistant/core/utils/paths.py`,
   which has no `GLOBAL_SKILLS_DIR`).
2. `SkillManager(skills_dirs=[GLOBAL_SKILLS_DIR])` — the real constructor is
   `SkillManager(config_getter: Callable[[], VectorCAConfig])`. This call would raise
   `TypeError` even if (1) were fixed.
3. `skill.content` — `SkillInfo` has never had a `content` field; the real field is
   `prompt`.
4. Even a fully corrected constructor call would then hit
   `SkillManager.__init__` → `_compute_search_paths()` →
   `get_harness_files_manager()`, which raises
   `RuntimeError("HarnessFilesManager not initialized — call
   init_harness_files_manager() first")` — VECTOR's runtime never calls that
   initializer.

All four were silently swallowed by one broad `except Exception: return None`, logged
only as a warning. **`load_skill()` has returned `None` on every call since it was
wired in.** Verified by direct import/construction attempts before writing the fix
(not asserted from reading alone).

### The fix

Rather than force VECTOR's runtime to also stand up `VectorCAConfig` +
`HarnessFilesManager` just to satisfy one function, `load_skill()` (and a new
`list_skills()`) now use only the lightweight, dependency-free pieces directly:
`core.coding_assistant.core.skills.parser.parse_skill_markdown` and
`.models.SkillMetadata`/`SkillInfo`. These are pure functions/pydantic models with no
config or harness dependency — real, already-correct code, just never reachable
through the broken `SkillManager` call path for VECTOR's use case.

Both functions now read from `data/vector_skills/` (via `core.runtime_paths.data_path`)
— VECTOR's own directory, distinct from every other district's skill loader above and
from Claude's own `.claude/skills/`. This was an explicit owner choice (offered
alongside "write into Claude's global skills dir" and "write into the project's own
`.claude/skills/`, which Claude Code auto-discovers"): VECTOR's own accumulated
procedural knowledge, in the same format, not auto-wired into Claude's own skill menu.
Verified end-to-end against a real written `SKILL.md` before wiring anything further.

## SkillBuilder — the "repeated task" builder

The repetition-detection half of the request was **already built and already live**:
`vectorcode/src/reasoning_bank.py`'s `PatternLearner` (constructed inside
`core/loop/decision_engine.py`, so it runs on every real decision VECTOR's autonomous
loop makes) already tracks `usage_count` per task pattern via cosine-similarity
merging, and marks a pattern `stable` once it crosses `PatternConfig.min_usages_for_stable`
(3, by default) repeats with `reward >= PatternConfig.quality_threshold` (0.5). Nothing
new needed to be built for "detect a repeated task" — building a second, parallel
tracker would have duplicated real, working infrastructure.

What was missing: nothing converted a `stable` `Pattern` into an actual, loadable
`SKILL.md`. `PatternLearner` had no public accessor for the full stable set either
(`stats()` returns aggregates only, `get_best_strategies()` returns strategy text
only) — added `PatternLearner.stable_patterns(task_type=None) -> list[Pattern]`, a
small, additive, safe method (returns `Pattern` objects sorted by quality, using the
class's existing `Pattern.to_dict()` for serialization — no new schema).

`districts/personal_growth/skill_builder.py::SkillBuilder` (manifest entry
`skill_builder`, capabilities `learned_pattern_brief`/`learned_pattern_build`) follows
the same evidence-gated `<x>_brief`/`<x>_check` pattern used throughout the self-dev
program this whole session:

- **Never calls an LLM to judge eligibility.** A pattern becomes a skill only if the
  caller-supplied record re-passes deterministic threshold checks (`stable is True`,
  `usage_count >= min_usages`, `quality_score >= min_quality`, non-trivial strategy
  text) — the same thresholds `PatternLearner` already applied, re-checked here rather
  than trusted blindly, and overridable per-call via `min_usages`/`min_quality`
  evidence fields.
- **Deterministic rendering.** The generated `SKILL.md`'s frontmatter/body is built
  entirely from the pattern's own real fields (`task_type`, `strategy`,
  `usage_count`, `quality_score`) plus a timestamp — no generative step.
- **Stays evidence-gated, not self-reaching.** The agent's own `run()`/`build_from_patterns()`
  only ever sees what a caller hands it as `evidence.patterns` — it never imports
  `decision_engine` or reaches into a live `PatternLearner` itself. The bridge from
  real pattern data to agent evidence is a separate module-level function,
  `collect_stable_patterns()`, which a periodic job (e.g. a reflect-time task) calls
  to fetch real patterns and hand them to the agent — keeping the same separation of
  concerns (deterministic worker vs. orchestration) used across the whole program.
- Writes are scoped to one new, dedicated subdirectory per skill
  (`data/vector_skills/<slug>/SKILL.md`, slug bounded to `a-z0-9-`, no path
  traversal possible) — classified GREEN, the same tier already given to
  `ZKSteward`'s `zettelkasten`/`zk` actions, which write real files into the owner's
  own vault (a strictly more invasive precedent than writing into a new, isolated
  directory).

### A real word-overlap collision caught before finalizing action names

Same discipline this whole session established: before adding any new
`DISTRICT_TASK_MAP` key, checked it against `_canonical_district_from_task_type()`
directly in Python. `skill_pattern_brief`/`skill_pattern_build` (the first names
tried) resolved through the fallback matcher to `self_dev`'s existing
`skill_review_brief` (2-of-3 words overlap: `skill`, `brief`) — self_dev already owns
six `skill_*` actions (`skill_review_brief`, `skill_structure_check`,
`skill_analysis_brief/check`, `skill_comparison_brief/check`,
`skill_grading_brief`, `skill_grade_check`), so *any* name combining `skill` with
`brief`/`check` risked the same collision. Separately, a standalone `list_skills`
action name collided with `investment`'s `vt_skills` (`skills` alone was enough to
win uniquely). Renamed to `learned_pattern_brief`/`learned_pattern_build` (clean) and
dropped `list_skills` from the governor's routing table entirely — it stays a plain,
directly-importable Python helper in `coding_tools.py`, not a dispatchable action, so
it never needed to clear this bar at all. The `status_check_report` fail-closed
fixture was re-verified to still resolve `None` throughout.

## Verification

- `load_skill()`/`list_skills()`: 7 new tests
  (`tests/test_coding_tools_skills.py`) against real written `SKILL.md` files
  (valid, missing, malformed frontmatter, missing directory), plus one asserting
  the real default directory is `data/vector_skills/`.
- `PatternLearner.stable_patterns()`: covered in `vectorcode/src/reasoning_bank.py`'s
  own `__main__` self-test — a task repeated 3x above `quality_threshold` produces a
  retrievable stable pattern; a one-off low-reward task does not; `task_type`
  filtering and a no-match case are both checked.
- `SkillBuilder`: 7 new tests (`tests/test_skill_builder.py`) — manifest/tier/route
  exactness, brief evidence-presence reporting, a real file genuinely written and
  read back with correct frontmatter/body, every ineligibility reason individually
  triggered and asserted (not stable / too few uses / low quality / short strategy /
  malformed), idempotent re-run behavior under caller-supplied thresholds, the
  `collect_stable_patterns()` bridge proven against a real `PatternLearner` instance
  (not mocked), and an AST-based dangerous-primitive check
  (no `subprocess`/`eval`/`exec`/`system`/`popen`/`socket`).
- Manifest integrity: 41 districts, 274 agents, zero duplicate keys.
- Broader regression: 62 tests pass across
  `test_skill_builder.py`, `test_coding_tools_skills.py`, `test_governor.py`,
  `test_owner_routing_closure_f1.py`, `test_v1_trust_t2_action_identity.py`,
  `test_self_dev_specialists.py`; a further 42 tests pass across
  `decision_engine`/`reasoning_bank`-adjacent suites
  (`test_decision_engine.py`, `test_e1_persistent_learning.py`,
  `test_r11_learning_integration.py`, `test_vectorcode_agent_loop.py`) to confirm
  the additive `stable_patterns()` method disturbed nothing already relying on
  `PatternLearner`.

## What this does not do (by design, not oversight)

- Does not unify the other four skill-loading mechanisms. They keep working exactly
  as they already do; unifying them would be a separate, much larger, higher-risk
  task this request did not ask for.
- Does not automatically run `collect_stable_patterns()` → `SkillBuilder` on any
  schedule yet. The bridge function exists and is tested; wiring it into a periodic
  job (e.g. the 2AM reflect cycle) is a one-line follow-up the owner can request
  once they want it running unattended, not assumed here.
- Does not write into Claude's own `.claude/skills/` (global or project-local) —
  an explicit owner choice, not a technical limitation. Claude can still read
  `data/vector_skills/*/SKILL.md` directly on request; it is simply not
  auto-discovered as a slash-command skill.
