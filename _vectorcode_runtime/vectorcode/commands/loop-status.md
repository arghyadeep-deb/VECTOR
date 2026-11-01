<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/loop-status.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

# Loop Status Command

Inspect active loop state, progress, and failure signals.

## Usage

`/loop-status [--watch]`

## What to Report

- active loop pattern
- current phase and last successful checkpoint
- failing checks (if any)
- estimated time/cost drift
- recommended intervention (continue/pause/stop)

## Watch Mode

When `--watch` is present, refresh status periodically and surface state changes.

## Arguments

$ARGUMENTS:
- `--watch` optional
