"""Fix CompactEventFeed list mode left position."""
from pathlib import Path
f = Path("core/ui/dashboard/src/components/CompactEventFeed.tsx")
text = f.read_text(encoding="utf-8")
text = text.replace("left: 12, width: 220, height: 250,", "left: 237, width: 220, height: 250,")
f.write_text(text, encoding="utf-8")
print("Fixed")
