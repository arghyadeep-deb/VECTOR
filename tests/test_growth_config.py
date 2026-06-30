"""Task 1 — growth config section defaults (gated off, IG manual, 9:16)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_growth_config_defaults():
    from core.config import CONFIG
    g = CONFIG["growth"]
    assert g["enabled"] is False and g["auto_publish"] is False
    assert g["instagram_mode"] == "manual"          # human-in-loop default
    assert g["hud_viewport"] == [1080, 1920]         # 9:16
    assert g["brand_line"] and g["review_loop_max_iterations"] >= 1


if __name__ == "__main__":
    test_growth_config_defaults()
    print("OK test_growth_config")
