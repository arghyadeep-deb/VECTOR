# Task 04 — Enroll owner voiceprint

- **Depends on:** Task 03
- **Who:** OWNER (needs your mic)
- **Effort:** ~3 min

## Objective

Speaker verification stops failing open: action commands by voice are gated on
the enrolled owner voiceprint (resemblyzer is already installed).

## Implementation

```
python scripts/enroll_owner_voice.py
```

Records 3×10s of you speaking; writes
`data/voice_profiles/owner_voiceprint.npz`.

## Tests

`python core/voice/speaker_verify.py` self-test reports an enrolled profile
and verifies a fresh sample of your voice as owner.

## Demo

Say an action command in the HUD; a non-owner voice (phone recording of
someone else) gets rejected for YELLOW/RED intents.

## Acceptance

- [ ] `data/voice_profiles/owner_voiceprint.npz` exists
- [ ] Owner sample verifies True; non-owner sample False
