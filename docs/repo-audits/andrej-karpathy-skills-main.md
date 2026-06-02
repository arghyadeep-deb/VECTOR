# andrej-karpathy-skills-main Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\andrej-karpathy-skills-main`

| Metric | Count |
|--------|-------|
| Total SKILL.md files | 1 |
| Python files | 0 |
| Other files | `CLAUDE.md`, `CURSOR.md`, `EXAMPLES.md`, `README.md`, `README.zh.md`, `.claude-plugin/marketplace.json`, `.cursor/rules/karpathy-guidelines.mdc` |

**Single skill:** `skills/karpathy-guidelines/SKILL.md`

This is a minimal plugin repo — one skill, no code, no tooling. The skill encodes Andrej Karpathy's behavioral guidelines for reducing common LLM coding mistakes. It is a **behavioral prompt injection** that fires every time the trigger matches, enforcing:

1. **Think Before Coding** — surface assumptions, reject silent choices
2. **Simplicity First** — minimum code, no speculative features
3. **Surgical Changes** — touch only what the task requires
4. **Goal-Driven Execution** — define verifiable success criteria before implementing
5. **Verification Loop** — measure against criteria, iterate until done

The skill is matched by trigger phrases: "write", "implement", "create", "add", "fix", "refactor", "build", "edit", "update", "change", "delete", "remove", "debug", "review" — i.e., virtually every coding task.

## 2. VECTOR Parity

| Skill | Installed in `~/.claude/skills`? | Installed in `brain/.claude/skills`? |
|-------|----------------------------------|--------------------------------------|
| `karpathy-guidelines` | ❌ NOT INSTALLED | ❌ NOT INSTALLED |

**However:** VECTOR's `CLAUDE.md` (global) already references the `karpathy` skill via the system-reminder list (`karpathy-guidelines` appears in available skills). The `.cursor/rules/karpathy-guidelines.mdc` in the repo is the Cursor variant of the same guideline.

**Overlap check:** The `verification-before-completion` skill (installed) covers part of the verification loop from Guideline 5. The `brainstorming` + `writing-plans` mandatory workflow (CLAUDE.md Rule 1) covers Guideline 4's plan-before-code intent. However, `karpathy-guidelines` is more surgical — it triggers on every edit-level task (not just new features), enforcing simplicity and minimal-change discipline that none of the installed skills provide at that granularity.

**Parity score:** ❌ 0/1 unique skills installed. This skill adds net-new behavioral enforcement not covered by existing superpowers.

## 3. Frontend

N/A — no frontend code in this repo.

## 4. Verdict

**Install immediately. Zero cost, high behavioral leverage.**

This is the single most actionable install in this audit batch. One SKILL.md file that enforces Karpathy's coding discipline on every write/fix/refactor task. VECTOR's codebase has 133 agent files and growing — surgical-change discipline prevents cascading diff noise during autonomous coding sessions.

**Overall:** ❌ Not installed (critical gap — 1 skill, install now)

## 5. Gaps — What to Install

```bash
# Install karpathy-guidelines
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/andrej-karpathy-skills-main/skills/karpathy-guidelines" "C:/Users/Arghyadeep/.claude/skills/"
```

**Verify installation:**
```bash
ls "C:/Users/Arghyadeep/.claude/skills/karpathy-guidelines/"
# Should show: SKILL.md
```

**No Python absorption needed.** The entire value is the SKILL.md prompt — no code to migrate. The `.cursor/rules/karpathy-guidelines.mdc` file is Cursor-only and irrelevant for Claude Code.
