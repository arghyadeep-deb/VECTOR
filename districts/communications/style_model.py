"""
StyleModel — thin redirect to VectorCode persona module.
Canonical source: vectorcode/src/persona/style_model.py
"""
from pathlib import Path

_VC_SRC = Path(__file__).parent.parent.parent.parent / "vectorcode" / "src"
if _VC_SRC.exists():
    import sys
    sys.path.insert(0, str(_VC_SRC))

from persona.style_model import StyleModel

__all__ = ["StyleModel"]

if __name__ == "__main__":
    sm = StyleModel()
    print("communications/style_model.py (redirected to vectorcode/persona) OK")
