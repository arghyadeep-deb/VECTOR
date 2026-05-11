# Problem 06 - Direct Ollama Calls Can Hang

## Symptom

Several agents called `ollama.chat()` directly without a timeout. When Ollama,
the model, or routing was unavailable, tests and agent tasks could hang for
minutes before falling back.

## Why It Matters

VECTOR's loop must never get stuck behind one unavailable model. A missing local
model should degrade into a local summary, not freeze the district.

## Implemented Solution

Added `core/inference/ollama_safe.py`:

- creates an Ollama client with a timeout
- returns plain message text
- returns `""` on failure so agents use their fallback path

For research and memory curator agents, model calls now use a 2-second timeout.

Updated the slow memory/research agents:

- `ConsolidationBot`
- `PatternFinder`
- `WebScout`
- `NewsAggregator`
- `RedditMiner`

Verified after the fix:

- `tests/test_memory_curator.py`: 14 passed in 16.06s.
- `tests/test_research_district.py`: 16 passed in 13.92s.
- Full suite: 154 passed in 39.19s.

## Remaining Work

- Migrate remaining district-level `ollama.chat()` calls to the helper.
- Add tests that assert fallback returns within a few seconds when Ollama is
  unavailable.
