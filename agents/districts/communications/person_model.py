"""
PersonModel — DEPRECATED. Redirects to VectorCode persona module.

VectorCode PersonModel — canonical person model (canonical VectorCode implementation).
All new code should import from:
  agents.districts.coding.vectorcode.persona.person_model import PersonModel
"""
import sys
from pathlib import Path

_VC_SRC = Path(__file__).parent.parent.parent.parent / "vectorcode" / "src"
if _VC_SRC.exists():
    sys.path.insert(0, str(_VC_SRC))

from persona.person_model import PersonModel

__all__ = ["PersonModel"]

if __name__ == "__main__":
    pm = PersonModel()
    print("communications/person_model.py (redirected to vectorcode/persona) OK")
