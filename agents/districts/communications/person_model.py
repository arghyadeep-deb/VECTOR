"""
PersonModel — DEPRECATED. Redirects to VectorCode persona module.

Hermes dependency removed. VectorCode's PersonModel is the replacement.
All new code should import from:
  agents.districts.coding.vectorcode.persona.person_model import PersonModel
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agents.districts.coding.vectorcode.persona.person_model import PersonModel

__all__ = ["PersonModel"]

if __name__ == "__main__":
    pm = PersonModel()
    print("communications/person_model.py (redirected to vectorcode/persona) OK")
