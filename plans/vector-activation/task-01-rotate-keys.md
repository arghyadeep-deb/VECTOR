# Task 01 — Rotate all API keys

- **Depends on:** none — DO FIRST
- **Who:** OWNER
- **Effort:** ~30 min

## Objective

Every credential that ever lived in `.env` is revoked at its provider and
replaced. The old values sat in ~3000 commits of git history that were pushed
to GitHub, and one OpenAI key is additionally leaked as a literal FILENAME at
`Desktop/Grove/specs/sk-proj-….txt` (delete that file too).

## Implementation

1. Open `.env`, list the key names (don't paste values anywhere).
2. At each provider dashboard (OpenAI, Anthropic, ElevenLabs, Gemini, Groq,
   DeepSeek, OpenRouter, Telegram bot token, Supabase, Cloudflare, …):
   revoke old key → create new → paste into `.env`.
3. Delete `Desktop/Grove/specs/sk-proj-*.txt` and check
   `Authorize javascript origins.txt` next to it for other secrets.
4. `python run_vector.py doctor` to confirm nothing required broke.

## Demo

`python run_vector.py smoke` → status ok with new keys.

## Acceptance

- [ ] Every key in `.env` is newly issued (old ones revoked, not just replaced)
- [ ] The Grove key-filename file is deleted
- [ ] smoke passes
