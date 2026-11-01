"""
Absorb mattpocock/skills repo into VECTOR's ~/.claude/skills/.

Copies 17 skills (engineering + productivity + relevant misc + obsidian-vault)
to ~/.claude/skills/ and creates a VECTOR-customized obsidian-vault skill.
"""
import shutil
from pathlib import Path

REPO = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\skills")
DEST = Path.home() / ".claude" / "skills"
DEST.mkdir(parents=True, exist_ok=True)

copied = []
skipped = []

def copy_skill(skill_rel: str, dest_name: str | None = None):
    src = REPO / "skills" / skill_rel
    name = dest_name or src.name
    dst = DEST / name
    if not src.exists():
        print(f"  MISSING  {skill_rel}")
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    copied.append(name)

# ── Engineering (10 skills) ───────────────────────────────────────────────────
copy_skill("engineering/diagnose")
copy_skill("engineering/grill-with-docs")
copy_skill("engineering/improve-codebase-architecture")
copy_skill("engineering/prototype")
copy_skill("engineering/setup-matt-pocock-skills")
copy_skill("engineering/tdd")
copy_skill("engineering/to-issues")
copy_skill("engineering/to-prd")
copy_skill("engineering/triage")
copy_skill("engineering/zoom-out")

# ── Productivity (4 skills) ───────────────────────────────────────────────────
copy_skill("productivity/caveman")
copy_skill("productivity/grill-me")
copy_skill("productivity/handoff")
copy_skill("productivity/write-a-skill")

# ── Misc — relevant only (2 of 4) ────────────────────────────────────────────
copy_skill("misc/git-guardrails-claude-code")
copy_skill("misc/setup-pre-commit")
# skip: migrate-to-shoehorn (TypeScript only), scaffold-exercises (not relevant)

# ── Personal — obsidian-vault with VECTOR paths ───────────────────────────────
# Copy first, then patch vault path to VECTOR's actual Obsidian location
copy_skill("personal/obsidian-vault")
skill_md = DEST / "obsidian-vault" / "SKILL.md"
content = skill_md.read_text(encoding="utf-8")
# Replace Matt's hardcoded path with VECTOR's Obsidian vault
content = content.replace(
    "/mnt/d/Obsidian Vault/AI Research/",
    r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\\"
)
# Update naming conventions to match VECTOR's vault structure
content = content.replace(
    "Mostly flat at root level.",
    "Organized into subfolders: Daily/, Reflections/, Council/, Research/, Journals/, Projects/, Reviews/, Skills/, wiki/."
)
content = content.replace(
    '`/mnt/d/Obsidian Vault/AI Research/`',
    r'`C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\`'
)
skill_md.write_text(content, encoding="utf-8")

print(f"\n{'='*60}")
print(f"SKILLS ABSORBED INTO ~/.claude/skills/")
print(f"{'='*60}")
print(f"  Copied : {len(copied)} skills")
for s in copied:
    print(f"    + {s}")
print(f"{'='*60}\n")
