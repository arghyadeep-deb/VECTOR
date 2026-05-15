"""Move EVENT FEED to left:205, width:380, height:220."""
from pathlib import Path

f = Path("core/ui/dashboard/src/components/CompactEventFeed.tsx")
text = f.read_text(encoding="utf-8")

old_style = "left: 237, width: 220, height: 250, zIndex: 50, background: 'rgba(2, 12, 26, 0.85)', borderTop: '1px solid #0d3a5c', borderBottom: '1px solid #0d3a5c'"
new_style = "left: 205, width: 380, height: 220, zIndex: 50, background: 'rgba(4,12,24,0.92)', border: '1px solid rgba(79,195,247,0.08)', boxShadow: '0 0 30px rgba(79,195,247,0.03)'"

# Replace both occurrences (ticker + list mode)
count = 0
while old_style in text:
    text = text.replace(old_style, new_style)
    count += 1

if count:
    f.write_text(text, encoding="utf-8")
    print(f"Replaced {count} occurrences")
else:
    print("Pattern not found!")
    # Debug: show what's actually there
    for i, line in enumerate(text.splitlines(), 1):
        if "left: 237" in line or "left: 205" in line:
            print(f"  Line {i}: {line.strip()[:120]}")
