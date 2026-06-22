# evolution-api-main - VECTOR Absorption Review

**Verdict:** DO NOT ABSORB. Use as an optional external WhatsApp/messaging provider reference only.

**Priority:** MEDIUM for messaging access, LOW for code absorption

**Effort:** 1 session for a provider adapter/spec if WhatsApp becomes a daily-use channel

**License:** Apache-2.0 plus additional brand/usage-notification conditions in the local license.

**Repo size inspected:** About 323 files, excluding git/build/cache directories.

## What It Is

Evolution API is a TypeScript/Express REST API for WhatsApp and multi-channel messaging. It supports:

- Baileys-based WhatsApp Web integration
- official WhatsApp Cloud API path
- Chatwoot, Typebot, Dify, OpenAI, Flowise, N8N integrations
- Redis/cache, Prisma, PostgreSQL/MySQL
- RabbitMQ, Kafka, SQS, NATS, Pusher, Socket.io events
- S3/MinIO media storage
- API-key auth and instance tokens
- Docker deployment

## VECTOR Overlap

VECTOR already has messaging/webhook pieces:

- communication service auth tests
- Telegram/WhatsApp/Mattermost/DingTalk/SMS adapter tests
- webhook HMAC signing/delivery tests
- Cloudflare queue and Termux polling plan

Evolution API is a full external messaging backend, not a missing internal module.

## Real Value For VECTOR

Useful ideas:

- treat WhatsApp as a channel provider behind VECTOR's comms service
- event-driven inbound/outbound message normalization
- QR/session lifecycle states
- webhook signing and retry discipline
- media download/upload storage boundaries
- official Cloud API path as a safer production option than Web scraping

## Risks

- license has extra brand/notification conditions beyond plain Apache-2.0
- WhatsApp Web/Baileys path may violate platform expectations or break often
- large Node/Prisma/Redis/database service is operationally heavy
- telemetry exists and must be disabled/understood if self-hosted
- direct absorption would duplicate VECTOR comms/webhook abstractions

## Recommendation For Sonnet

Do not copy Evolution API code into VECTOR.

If WhatsApp daily control is needed, build a small provider boundary:

1. Keep VECTOR's comms API as the canonical interface.
2. Add a disabled-by-default `WhatsAppProvider` adapter with two modes: official Cloud API first, Evolution API external endpoint second.
3. Normalize inbound messages into VECTOR command queue entries.
4. Route outbound messages through PermissionGateway and rate limits.
5. Store only minimal channel/session metadata locally.

## Acceptance Criteria

- VECTOR works without Evolution API installed.
- Official WhatsApp Cloud API is preferred for production.
- Evolution API mode requires explicit endpoint/token configuration.
- All inbound commands are authenticated and audited.
- No Evolution API frontend/branding assets are copied.

