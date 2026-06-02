# obsidian-skills-main Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\obsidian-skills-main`

| Metric | Count |
|--------|-------|
| Total SKILL.md files | 5 |
| Python files | 0 |
| Other files | `LICENSE`, `README.md`, `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, reference docs |

**All 5 skills:**

| Skill | Description |
|-------|-------------|
| `obsidian-cli` | Interact with running Obsidian via CLI: read, create, search notes, manage tasks, properties; also supports plugin dev (reload plugins, run JS, capture errors, screenshot DOM) |
| `obsidian-markdown` | Create/edit Obsidian Flavored Markdown — wikilinks, embeds, callouts, frontmatter properties, tags; covers Obsidian-specific extensions beyond CommonMark |
| `obsidian-bases` | Create/edit Obsidian Bases (`.base` files) — database-like views of notes with filters, formulas, table/card/list/map views |
| `defuddle` | Extract clean Markdown from any web URL via `defuddle` CLI — removes nav/ads/clutter, reduces token usage vs raw WebFetch |
| `json-canvas` | Create/edit JSON Canvas (`.canvas`) files — nodes, edges, groups, visual mind maps and flowcharts in Obsidian |

**Reference docs included:**
- `obsidian-markdown/references/`: `CALLOUTS.md`, `EMBEDS.md`, `PROPERTIES.md`
- `obsidian-bases/references/`: `FUNCTIONS_REFERENCE.md`
- `json-canvas/references/`: `EXAMPLES.md`

## 2. VECTOR Parity

| Skill | Installed in `~/.claude/skills`? | Overlap with existing skills |
|-------|----------------------------------|------------------------------|
| `obsidian-cli` | ❌ NOT INSTALLED | Partial: `obsidian-vault` covers basic file ops but not CLI commands |
| `obsidian-markdown` | ❌ NOT INSTALLED | Partial: `obsidian-vault` knows basic wikilink syntax |
| `obsidian-bases` | ❌ NOT INSTALLED | None |
| `defuddle` | ❌ NOT INSTALLED | None — WebFetch is used currently |
| `json-canvas` | ❌ NOT INSTALLED | None |

**Existing coverage (`obsidian-vault` skill — installed):**
The installed `obsidian-vault` skill covers: vault path, naming conventions, wikilink syntax, note creation workflow, basic search with find/grep. It does NOT cover: the `obsidian` CLI tool, Obsidian Flavored Markdown extensions (callouts, embeds, properties), Bases (`.base` files), or Canvas files.

**VECTOR Obsidian writes:** `districts/reflection/journal_writer.py` and `districts/memory_curator/` both write to the vault. They currently use raw Python file writes — they would benefit from `obsidian-markdown` for correct frontmatter/callout/embed syntax, and `obsidian-cli` for operations on a live Obsidian instance.

**`defuddle` for VECTOR:**
VECTOR's research district (`districts/research/web_scout.py`, `paper_reader.py`) uses raw `httpx` fetches and Playwright for web content. `defuddle` CLI (Node.js, `npm install -g defuddle`) would give any VECTOR agent a one-command clean Markdown extraction from any URL — directly reducing token overhead in research tasks. This is the highest-value skill in this repo for day-to-day VECTOR operation.

**Parity score:** ❌ 0/5 skills installed. All 5 are unique gaps.

## 3. Frontend

N/A — no frontend code in this repo.

## 4. Verdict

**Install all 5. Small repo, high relevance, zero risk.**

VECTOR writes to the Obsidian vault constantly (reflection, journal, memory). Three of the five skills (`obsidian-cli`, `obsidian-markdown`, `obsidian-bases`) directly improve vault output quality. `defuddle` is a universal research utility that reduces token usage on every URL fetch. `json-canvas` enables VECTOR to generate visual knowledge maps (useful for `districts/research/` and `graphify` output visualization).

The existing `obsidian-vault` skill is complementary — it handles VECTOR's specific vault path and naming conventions. These 5 skills provide the Obsidian platform knowledge on top of it.

**Overall:** ❌ Not installed (install all 5 — no conflicts, all additive)

## 5. Gaps — What to Install

**Install all 5 skills:**
```bash
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/obsidian-skills-main/skills/obsidian-cli" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/obsidian-skills-main/skills/obsidian-markdown" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/obsidian-skills-main/skills/obsidian-bases" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/obsidian-skills-main/skills/defuddle" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/obsidian-skills-main/skills/json-canvas" "C:/Users/Arghyadeep/.claude/skills/"
```

**Install `defuddle` CLI (prerequisite for the `defuddle` skill):**
```bash
npm install -g defuddle
# Verify:
defuddle --version
```

**Usage after install:**
- When VECTOR agents fetch web content: `/defuddle <url>` instead of raw WebFetch
- When writing vault notes: `/obsidian-markdown` for correct syntax
- When Obsidian is open and running: `/obsidian-cli` for live vault operations
- When generating knowledge visualizations: `/json-canvas` for `.canvas` output

**No Python absorption needed.** All 5 skills are pure SKILL.md prompt files with reference docs. The entire value is behavioral — they teach Claude Code the correct syntax and CLI commands for Obsidian tooling.
