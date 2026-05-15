<!-- VECTOR-INGESTED ASSET
  Source: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\sickn33_antigravity-awesome-skills\repo\skills\database-design\migrations.md
  Personalized for VECTOR runtime — local Ollama, no paid APIs.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T01:39:49+00:00
-->

# Migration Principles

> Safe migration strategy for zero-downtime changes.

## Safe Migration Strategy

```
For zero-downtime changes:
│
├── Adding column
│   └── Add as nullable → backfill → add NOT NULL
│
├── Removing column
│   └── Stop using → deploy → remove column
│
├── Adding index
│   └── CREATE INDEX CONCURRENTLY (non-blocking)
│
└── Renaming column
    └── Add new → migrate data → deploy → drop old
```

## Migration Philosophy

- Never make breaking changes in one step
- Test migrations on data copy first
- Have rollback plan
- Run in transaction when possible

## Serverless Databases

### Neon (Serverless PostgreSQL)

| Feature | Benefit |
|---------|---------|
| Scale to zero | Cost savings |
| Instant branching | Dev/preview |
| Full PostgreSQL | Compatibility |
| Autoscaling | Traffic handling |

### Turso (Edge SQLite)

| Feature | Benefit |
|---------|---------|
| Edge locations | Ultra-low latency |
| SQLite compatible | Simple |
| Generous free tier | Cost |
| Global distribution | Performance |
