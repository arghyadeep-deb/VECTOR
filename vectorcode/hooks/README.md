# vectorcode/hooks/ — dormant historical snapshot, NOT live

**This directory is not executed by this repository's Claude Code session.**
Every hook `.claude/settings.json` actually registers points at
`$CLAUDE_PROJECT_DIR/.claude/hooks/*.py` — confirmed by direct inspection
(2026-10-07) and enforced by `tests/test_claude_settings_hooks_point_at_live_dir.py`,
which fails the suite if that ever changes.

This copy exists because `vectorcode/docs/absorption/09-wave-9-claude-ecosystem.md`
records that VECTOR's own self-archiving process copied `.claude/hooks/`
"verbatim" into this location at some earlier point. It is a historical
snapshot, not a second live installation — no code in this repository
imports or executes these files (confirmed via repo-wide grep, 2026-10-07;
the only references found were unrelated generic skill-template
documentation describing how a *different*, reusable skill installs hooks
into *other* projects' `vectorcode/hooks/`, not this repo's own wiring).

If you are fixing a bug in a Claude Code hook: **fix it in `.claude/hooks/`.**
This directory should be treated as read-only reference material. If it
ever needs to be brought back in sync after `.claude/hooks/` changes, that
is a deliberate re-snapshot, not an independent fix target.
