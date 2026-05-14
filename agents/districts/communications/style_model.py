"""
StyleModel — DEPRECATED. Redirects to VectorCode persona module.

VectorCode StyleModel — canonical style model (canonical VectorCode implementation).
All new code should import from:
  agents.districts.coding.vectorcode.persona.style_model import StyleModel
"""
import sys
from pathlib import Path

_VC_SRC = Path(__file__).parent.parent.parent.parent / "vectorcode" / "src"
if _VC_SRC.exists():
    sys.path.insert(0, str(_VC_SRC))

from persona.style_model import StyleModel

__all__ = ["StyleModel"]

if __name__ == "__main__":
    sm = StyleModel()
    print("communications/style_model.py (redirected to vectorcode/persona) OK")
