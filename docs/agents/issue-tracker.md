# Issue Tracker: GitHub

Issues and PRDs for VECTOR live as GitHub issues in the `arghyadeep-deb/VECTOR` repo. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --comments`
- **List issues**: `gh issue list --state open --json number,title,body,labels`
- **Comment**: `gh issue comment <number> --body "..."`
- **Apply labels**: `gh issue edit <number> --add-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

The repo is inferred from `git remote -v` — `gh` handles this automatically.

## VECTOR-specific conventions

- Issue titles use this format: `[District] Short description` — e.g. `[coding] GitBot fails on merge conflicts`
- PRDs are labeled `prd`
- Architecture improvement proposals are labeled `architecture`
- District-specific bugs are labeled with the district name (e.g. `district:finance`)

## When a skill says "publish to the issue tracker"

Create a GitHub issue with appropriate labels.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
