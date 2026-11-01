"""Absorb all remaining skills from mattpocock/skills that were skipped previously."""
import shutil
from pathlib import Path

REPO = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\skills")
DEST = Path.home() / ".claude" / "skills"

copied = []

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

# in-progress — absorb all (useful for VECTOR's content + reflection districts)
copy_skill("in-progress/review")
copy_skill("in-progress/writing-beats")
copy_skill("in-progress/writing-fragments")
copy_skill("in-progress/writing-shape")

# deprecated — absorb all (still useful; keep in skills for reference)
copy_skill("deprecated/design-an-interface")
copy_skill("deprecated/qa")
copy_skill("deprecated/ubiquitous-language")
copy_skill("deprecated/request-refactor-plan")

# personal
copy_skill("personal/edit-article")

print(f"Copied {len(copied)} skills: {copied}")
