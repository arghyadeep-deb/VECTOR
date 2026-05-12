"""
StyleModel — DEPRECATED. Redirects to VectorCode persona module.

Hermes dependency removed. VectorCode's StyleModel is the replacement.
All new code should import from:
  agents.districts.coding.vectorcode.persona.style_model import StyleModel
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agents.districts.coding.vectorcode.persona.style_model import StyleModel

__all__ = ["StyleModel"]

if __name__ == "__main__":
    sm = StyleModel()
    print("communications/style_model.py (redirected to vectorcode/persona) OK")
