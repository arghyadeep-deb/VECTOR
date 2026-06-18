#!/usr/bin/env python3
"""
VECTOR Auto-Screenshot Hook — PostToolUse on Edit|Write|MultiEdit
Fires only when VECTOR dashboard or HTML/CSS files are edited.
Captures the screen so Claude can see its own UI bugs.
Requires Pillow: pip install Pillow
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    sys.exit(0)

file_path = (
    data.get("file_path")
    or data.get("tool_input", {}).get("file_path")
    or ""
)

# Only fire for UI files
UI_PATTERNS = [
    r"dashboard[/\\]",
    r"[/\\]static[/\\]",
    r"[/\\]templates[/\\]",
    r"[/\\]frontend[/\\]",
    r"[/\\]components[/\\]",
    r"\.html$",
    r"\.css$",
    r"\.tsx?$",
    r"\.jsx?$",
]

if not any(re.search(p, file_path, re.IGNORECASE) for p in UI_PATTERNS):
    sys.exit(0)

try:
    from PIL import ImageGrab

    screenshots_dir = Path(".claude/screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    img_path = screenshots_dir / f"ui-{ts}.png"

    img = ImageGrab.grab()
    img.save(str(img_path))
    print(f"[VECTOR SCREENSHOT] {img_path.name} — Claude can now review the UI.")

except ImportError:
    print("[VECTOR SCREENSHOT] skipped: Pillow not installed", file=sys.stderr)
except Exception:
    print("[VECTOR SCREENSHOT] skipped: screenshot capture failed", file=sys.stderr)

sys.exit(0)
