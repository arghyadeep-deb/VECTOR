"""Fix remaining jarvis references in the Twitter bot prompt template."""
from pathlib import Path

f = Path("vectorcode/src/recipes/data/operators/vector_twitter_bot_prompt.md")
text = f.read_text(encoding="utf-8")

replacements = [
    ("`jarvis init`", "`vector init`"),
    ("`jarvis ask", "`vector ask"),
    ("`jarvis doctor`", "`vector doctor`"),
    ("`jarvis add slack`", "`vector channel add slack`"),
    ("`jarvis channel list`", "`vector channel list`"),
    ("`jarvis bench`", "`vector bench`"),
    ("`jarvis optimize`", "`vector optimize`"),
    ("`jarvis add memory`", "`vector memory add`"),
    ("`jarvis research`", "`vector research`"),
    ("`jarvis add channel`", "`vector channel add`"),
    ('"`jarvis init`', '"`vector init`'),
    ("`jarvis ask` works", "`vector ask` works"),
]

for old, new in replacements:
    text = text.replace(old, new)

f.write_text(text, encoding="utf-8")

# Verify
lines = f.read_text(encoding="utf-8").splitlines()
remaining = [(i+1, l) for i, l in enumerate(lines) if "jarvis" in l.lower()]
if remaining:
    print(f"Still has jarvis on lines: {[(ln, l[:60]) for ln, l in remaining]}")
else:
    print("Zero jarvis remaining in prompt template")
