"""Shift VECTOR HUD palette to monotonic JARVIS blue-on-black."""
from pathlib import Path

SRC = Path("core/ui/dashboard/src/components")

REPLACEMENTS = [
    # Teal/green -> light blue
    ("#00FFD4", "#81D4FA"),
    ("#00FF88", "#4FC3F7"),
    ("#00ff88", "#4FC3F7"),
    # Purple -> blue
    ("#BF5FFF", "#64B5F6"),
    ("#bf5fff", "#64B5F6"),
    # Amber/warning -> blue
    ("#FFB300", "#42A5F5"),
    ("#ffb300", "#42A5F5"),
    ("#ffaa00", "#42A5F5"),
    # Green status dot
    ("#00FF88", "#4FC3F7"),
    # Old cyan -> JARVIS blue
    ("#00d4ff", "#4FC3F7"),
    ("#00CFFF", "#4FC3F7"),
    ("#00cf", "#4FC3F7"),
]

count = 0
for f in sorted(SRC.glob("*.tsx")):
    text = f.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        f.write_text(text, encoding="utf-8")
        count += 1
        print(f"  {f.name}")

print(f"\n{count} files updated")
