# Triage Labels

Maps the five canonical skill triage roles to VECTOR's actual GitHub label strings.

| Label in mattpocock/skills | Label in VECTOR's tracker | Meaning                                     |
|----------------------------|---------------------------|---------------------------------------------|
| `needs-triage`             | `needs-triage`            | Needs owner evaluation                      |
| `needs-info`               | `needs-info`              | Waiting on Arghyadeep for clarification     |
| `ready-for-agent`          | `ready-for-agent`         | Fully specified — an agent can pick it up   |
| `ready-for-human`          | `ready-for-human`         | Requires Arghyadeep's implementation        |
| `wontfix`                  | `wontfix`                 | Intentional design decision, won't change   |

## VECTOR-specific extra labels

- `district:<name>` — which district the issue belongs to (e.g. `district:coding`)
- `rule-violation` — breaks one of the 12 critical rules
- `prd` — product requirements document
- `architecture` — ADR candidate
- `cloud` — affects Cloudflare/Fly.io deployment
- `voice` — affects the voice pipeline (STT/TTS/wake word)
