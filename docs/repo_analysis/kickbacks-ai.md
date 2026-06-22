# kickbacks.ai-main - VECTOR Absorption Review

**Verdict:** HARD SKIP. Do not run, copy, absorb, or imitate the advertising/injection behavior. Use only as a security caution for SkillSpector-style checks.

**Priority:** SKIP for product features; HIGH as a security pattern to detect/block

**Effort:** 0.5 session to add a future security rule/signature if SkillSpector work is active

**License:** Proprietary source-available. The license allows viewing/forking for transparency, but does not grant normal use, modification, redistribution, derivative, or competing-use rights.

**Repo size inspected:** About 185 files / 1.56 MB.

## What It Is

`kickbacks.ai` is a VS Code extension that injects sponsored wording into Claude Code / Codex / Claude CLI style thinking or spinner surfaces and tracks ad impressions/revenue.

The local checkout includes:

- VS Code extension activation code
- adapters for Codex/Claude surfaces
- auth/token-vault related code
- metrics/view tracking
- kill-switch behavior
- tests and extension packaging

## VECTOR Overlap

VECTOR should not have this product behavior. It does not improve JARVIS capability, autonomy, reasoning, voice, memory, security, or user control.

The only useful takeaway is defensive: VECTOR should be able to notice and warn about tools/extensions/skills that modify agent UI surfaces, inject sponsored content, or add hidden tracking.

## Risks

- proprietary license boundary blocks absorption
- UI injection into agent tools is hostile to trust
- telemetry/ad tracking is not aligned with a private personal assistant
- token-vault and activation behavior creates unnecessary attack surface
- copying patterns would contaminate VECTOR's security posture

## Recommendation For Sonnet

Do not implement any kickbacks-style feature.

If SkillSpector or workspace-security work is active, add a clean-room rule category:

- detect extensions/plugins that inject into Codex/Claude UI surfaces
- detect ad/sponsored-content injection strings
- detect unexpected telemetry, kill-switch, and impression-tracking code
- warn before such extensions are allowed near VECTOR sessions

## Acceptance Criteria

- No kickbacks source code or assets are copied.
- No advertising/injection feature is added.
- Any future reference is limited to security documentation or detector signatures.
- VECTOR remains user-first and non-ad-supported.

