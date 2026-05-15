<!-- VECTOR-INGESTED ASSET
  Source: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\sickn33_antigravity-awesome-skills\repo\skills\api-patterns\response.md
  Personalized for VECTOR runtime — local Ollama, no paid APIs.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T01:39:46+00:00
-->

# Response Format Principles

> Consistency is key - choose a format and stick to it.

## Common Patterns

```
Choose one:
├── Envelope pattern ({ success, data, error })
├── Direct data (just return the resource)
└── HAL/JSON:API (hypermedia)
```

## Error Response

```
Include:
├── Error code (for programmatic handling)
├── User message (for display)
├── Details (for debugging, field-level errors)
├── Request ID (for support)
└── NOT internal details (security!)
```

## Pagination Types

| Type | Best For | Trade-offs |
|------|----------|------------|
| **Offset** | Simple, jumpable | Performance on large datasets |
| **Cursor** | Large datasets | Can't jump to page |
| **Keyset** | Performance critical | Requires sortable key |

### Selection Questions

1. How large is the dataset?
2. Do users need to jump to specific pages?
3. Is data frequently changing?
