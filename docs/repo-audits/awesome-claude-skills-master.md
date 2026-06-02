# awesome-claude-skills-master Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\awesome-claude-skills-master`
**Total top-level items:** 33 directories + README.md + CONTRIBUTING.md + LICENSE

### Skill Inventory

**864 total SKILL.md files** across 2 tiers:

#### Tier 1 — Named Skills (30 top-level directories, excluding composio-skills)
| Skill | In Brain | Notes |
|-------|----------|-------|
| `artifacts-builder` | No | HTML artifact builder with React/Tailwind + shadcn components tarball |
| `brand-guidelines` | Yes | Anthropic brand colors/typography |
| `canvas-design` | Yes | PNG/PDF visual design; includes 9 font files (.ttf) |
| `changelog-generator` | No | Automated changelog from git history |
| `competitive-ads-extractor` | No | Facebook/LinkedIn ad library extraction + competitive analysis |
| `connect` | No | Claude.ai Connect integration |
| `connect-apps` | No | Connect apps skill |
| `connect-apps-plugin` | No | Plugin manifest only (`.claude-plugin/plugin.json`, `commands/setup.md`) — not a SKILL.md skill |
| `content-research-writer` | No | Research + write partner for blog/newsletter content with citation support |
| `developer-growth-analysis` | No | Analyzes Claude Code chat history, fetches HN resources, sends Slack DM report |
| `document-skills/docx` | Yes (brain has `docx/`) | Word document creation/editing; brain version is newer (larger SKILL.md) |
| `document-skills/pdf` | Yes (brain has `pdf/`) | PDF extraction/creation/merge/forms; brain version is newer |
| `document-skills/pptx` | Yes (brain has `pptx/`) | PowerPoint creation; brain version is newer |
| `document-skills/xlsx` | Yes (brain has `xlsx/`) | Excel spreadsheets; brain version is newer; repo includes `recalc.py` |
| `domain-name-brainstormer` | No | Domain name generation with availability checking |
| `file-organizer` | No | File system organization by type/date/project |
| `image-enhancer` | No | AI image enhancement and upscaling |
| `internal-comms` | Yes | Status reports, newsletters, FAQs |
| `invoice-organizer` | No | Invoice parsing, categorization, export |
| `langsmith-fetch` | No | LangSmith trace/dataset fetching skill |
| `lead-research-assistant` | No | Lead identification, ICP analysis, outreach strategy |
| `mcp-builder` | Yes | MCP server creation |
| `meeting-insights-analyzer` | No | Meeting transcript analysis — filler words, conflict avoidance, communication patterns |
| `raffle-winner-picker` | No | Random winner selection from lists |
| `skill-creator` | Yes | Guide for creating skills |
| `skill-share` | No | Skill sharing/publishing workflow |
| `slack-gif-creator` | Yes | Animated GIF creator for Slack |
| `tailored-resume-generator` | No | Resume tailoring against job descriptions |
| `template-skill` | No | Blank skill template |
| `theme-factory` | Yes | Style artifacts with professional themes |
| `twitter-algorithm-optimizer` | No | Twitter/X content optimization |
| `video-downloader` | No | yt-dlp wrapper; includes Python download script |
| `webapp-testing` | Yes | Playwright-based web app testing |

#### Tier 2 — Composio Skills (833 sub-skills in `composio-skills/`)
833 separate SKILL.md files, one per SaaS integration (Salesforce, HubSpot, Notion, Slack, GitHub, Stripe, Twilio, Zoom, Adobe, etc. through the alphabet). Each file teaches the agent to use Composio's managed auth + API wrapper for that specific platform.

**None of the 833 composio skills are in brain.** Brain uses direct API integration via `core/engine/oauth/` (83-provider YAML) and `vectorcode/src/channels/` adapters. Composio is a competing managed-auth middleware — these skills would route API calls through Composio's cloud, conflicting with VECTOR Rule 11 (local-first, own OAuth stack).

### Non-Markdown Files
- `canvas-design/canvas-fonts/` — 9 TTF font files + OFL license texts (legitimate assets for the canvas-design skill)
- `artifacts-builder/scripts/` — `bundle-artifact.sh`, `init-artifact.sh`, `shadcn-components.tar.gz` (~large binary)
- `document-skills/pptx/scripts/` — `html2pptx.js`
- `document-skills/xlsx/` — `recalc.py` (Python: Excel recalculation helper)
- `video-downloader/scripts/` — Python yt-dlp download script
- `connect-apps-plugin/.claude-plugin/plugin.json` — plugin manifest

**Python files found:** `document-skills/xlsx/recalc.py`, `video-downloader/scripts/*.py`

---

## 2. VECTOR Parity

**Script output (Step 2 from task spec):**
```
brain skills count: 371
awesome-claude-skills-master: 33 top-level items
```

### Already in Brain (7 top-level skills confirmed)
`brand-guidelines`, `canvas-design`, `internal-comms`, `mcp-builder`, `skill-creator`, `slack-gif-creator`, `theme-factory`, `webapp-testing`

### Document skills: Brain version is NEWER
Brain has `pdf/`, `docx/`, `pptx/`, `xlsx/` — and the brain versions have **larger SKILL.md files** (e.g., brain `pdf/SKILL.md` = 8,035 chars vs repo = 7,068 chars). Brain versions supersede this repo's document-skills. Do not overwrite brain with older versions.

### Composio Skills: Zero parity — intentionally excluded
All 833 composio-skills are absent from brain by design. VECTOR runs its own OAuth stack and direct API clients. Pulling in Composio skills would route VECTOR's actions through an external cloud middleware, violating the local-first principle.

### NOT in Brain (22 top-level non-composio skills)
| Skill | VECTOR Relevance | Priority |
|-------|-----------------|----------|
| `competitive-ads-extractor` | High — ads districts already exist | Medium |
| `content-research-writer` | High — content district (District 18) | Medium |
| `meeting-insights-analyzer` | High — comms + health district insight | High |
| `tailored-resume-generator` | Medium — interview_prep district | Medium |
| `lead-research-assistant` | Medium — agency/startups districts | Low |
| `developer-growth-analysis` | Medium — karpathy_lab / reflection | Low |
| `video-downloader` | Medium — content district uses yt-dlp already | Low (duplicate) |
| `changelog-generator` | Low — VECTOR auto-commits with its own format | Low |
| `domain-name-brainstormer` | Low — startups district use case | Low |
| `invoice-organizer` | Low — finance district | Low |
| `twitter-algorithm-optimizer` | Low — content district could use | Low |
| `image-enhancer` | Low — content/comfyui_adapter covers this | Low |
| `file-organizer` | Very Low — general utility | Skip |
| `raffle-winner-picker` | None — no VECTOR use case | Skip |
| `skill-share` | None — internal tooling for officialskills.sh | Skip |
| `template-skill` | None — brain uses its own skill template | Skip |
| `langsmith-fetch` | None — VECTOR does not use LangSmith | Skip |
| `connect` / `connect-apps` | None — Claude.ai connect platform feature | Skip |
| `connect-apps-plugin` | None — plugin manifest, not a SKILL.md | Skip |
| `artifacts-builder` | None — Claude.ai artifact builder, no terminal use | Skip |

---

## 3. Frontend: N/A

Skill collection — no application frontend.

---

## 4. Verdict

**KEEP until 3 skills are copied, then SAFE TO DELETE.**

Key findings:
1. **833 Composio skills** — zero value for VECTOR; Composio routes through external cloud, conflicts with Rule 11. Skip entirely.
2. **Document skills (pdf/docx/pptx/xlsx)** — already in brain AND brain versions are newer. Repo versions are stale copies. Do not import.
3. **7 named skills** already in brain — confirmed duplicates.
4. **3 skills worth copying** before deletion (see Gaps below).
5. **Remaining 19 skills** — either no VECTOR use case, already covered by existing districts, or too low-value to warrant the brain slot.

---

## 5. Gaps — Copy These to Brain

### Priority 1 — High VECTOR Value

**`meeting-insights-analyzer/SKILL.md`** → `brain/.claude/skills/meeting-insights-analyzer/SKILL.md`
- Analyzes meeting transcripts for communication patterns: filler words, conflict avoidance, conversation dominance, missed listening opportunities
- VECTOR use: health district (fatigue/behavior monitoring), relationships district (communication_analyst), reflection district (daily_reviewer)
- Unique angle — behavioral pattern extraction from transcripts, not available in any existing brain skill

**`competitive-ads-extractor/SKILL.md`** → `brain/.claude/skills/competitive-ads-extractor/SKILL.md`
- Facebook Ad Library + LinkedIn Ad Library extraction and competitive messaging analysis
- VECTOR use: directly extends `districts/marketing/` (ads districts already built); complements `ads-competitor` brain skill
- Contains structured process for extracting value props, pain points, CTAs, and creative patterns from competitor ads

**`content-research-writer/SKILL.md`** → `brain/.claude/skills/content-research-writer/SKILL.md`
- Research-backed writing partner: outlines, citations, hooks, iterative drafting with voice preservation
- VECTOR use: content district (`districts/content/script_generator.py`), agency district (content_strategist), karpathy_lab writing
- 14KB SKILL.md — detailed process, not a thin wrapper

### Priority 2 — Moderate Value (copy if the use case is active)

**`tailored-resume-generator/SKILL.md`** → `brain/.claude/skills/tailored-resume-generator/SKILL.md`
- Resume tailoring against specific job descriptions with ATS optimization
- VECTOR use: interview_prep district (mock_interviewer + report_generator already exist); adds resume output capability

**`developer-growth-analysis/SKILL.md`** → `brain/.claude/skills/developer-growth-analysis/SKILL.md`
- Analyzes Claude Code chat history for coding patterns, surfaces gaps, fetches HN learning resources, sends Slack DM report
- VECTOR use: reflection district (growth_analyst) + karpathy_lab progress tracking

### Do NOT Copy
- All 833 composio-skills (Composio cloud dependency, conflicts with VECTOR Rule 11)
- `document-skills/{pdf,docx,pptx,xlsx}` (brain versions are newer)
- `connect`, `connect-apps`, `connect-apps-plugin` (Claude.ai platform features, not Claude Code skills)
- `artifacts-builder` (claude.ai artifact builder, terminal-incompatible)
- `template-skill`, `skill-share`, `raffle-winner-picker`, `langsmith-fetch`, `file-organizer` (no VECTOR relevance)
