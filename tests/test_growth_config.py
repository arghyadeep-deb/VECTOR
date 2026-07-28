"""Task 1 — growth config section defaults (live since 2026-07-27, IG via
phone, auto_publish still gated, 9:16)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_growth_config_defaults():
    from core.config import CONFIG
    g = CONFIG["growth"]
    # enabled deliberately flipped False->True 2026-07-27 (owner request,
    # core/config.py:1048 comment) — growth district is live by default now.
    # auto_publish stays False regardless: never auto-post without
    # per-action approval.
    assert g["enabled"] is True and g["auto_publish"] is False
    assert g["instagram_mode"] == "phone"            # deliberately changed from "manual": VECTOR now drives the connected phone
    assert g["hud_viewport"] == [1080, 1920]         # 9:16
    assert g["brand_line"] and g["review_loop_max_iterations"] >= 1


if __name__ == "__main__":
    test_growth_config_defaults()
    print("OK test_growth_config")
