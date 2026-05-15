<!-- VECTOR-INGESTED ASSET
  Source: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\sickn33_antigravity-awesome-skills\repo\skills\avalonia-zafiro-development\naming-standards.md
  Personalized for VECTOR runtime — local Ollama, no paid APIs.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T01:39:46+00:00
-->

# Naming & Coding Standards

## General Standards

- **Explicit Names**: Favor clarity over cleverness.
- **Async Suffix**: Do **NOT** use the `Async` suffix in method names, even if they return `Task`.
- **Private Fields**: Do **NOT** use the `_` prefix for private fields.
- **Static State**: Avoid static state unless explicitly justified and documented.
- **Method Design**: Keep methods small, expressive, and with low cyclomatic complexity.

## Error Handling

- **Result & Maybe**: Use types from **CSharpFunctionalExtensions** for flow control and error handling.
- **Exceptions**: Reserved strictly for truly exceptional, unrecoverable situations.
- **Boundaries**: Never allow exceptions to leak across architectural boundaries.
