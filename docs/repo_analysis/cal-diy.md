# cal.diy-main - VECTOR Absorption Review

**Verdict:** DO NOT ABSORB. Use clean-room scheduling/booking concepts only.

**Priority:** LOW-MEDIUM

**Effort:** 1-2 sessions for a small VECTOR booking/availability adapter if needed

**License:** MIT

**Repo size inspected:** About 7260 files, excluding git/build/cache directories.

## What It Is

Cal.diy is a community-maintained, fully open-source scheduling platform forked from Cal.com with enterprise features removed. It is a large Next.js/tRPC/React/Tailwind/Prisma/PostgreSQL monorepo for self-hosted booking pages and calendar scheduling.

It includes:

- booking pages and event types
- calendar integrations
- app-store/integration architecture
- embeds
- auth/user flows
- Prisma schema/migrations
- many tests and deployment scripts

## VECTOR Overlap

VECTOR already has:

- time/calendar district
- chief-of-staff scheduling/routine logic
- KIIT schedule scraping
- scheduler/cron systems
- content scheduling

VECTOR does not need a full public scheduling SaaS inside the JARVIS runtime.

## Real Value For VECTOR

Useful clean-room ideas:

- availability windows and event-type schema
- booking link concept for owner availability
- conflict detection between calendars/tasks
- reschedule/cancel lifecycle
- calendar integration boundary
- embedable booking surface if VECTOR later needs public appointment booking

## Risks

- very large monorepo and operational footprint
- PostgreSQL/Prisma/Next.js stack does not match VECTOR's local-first SQLite runtime
- self-hosting warning explicitly says personal/non-production use and advanced admin required
- direct absorption would duplicate scheduling concepts and UI
- many env vars/secrets/integrations to secure

## Recommendation For Sonnet

Do not copy or run Cal.diy as part of VECTOR.

If booking is needed, implement a small VECTOR-native layer:

1. Define `AvailabilityWindow`, `BookingRequest`, and `CalendarEvent` schemas.
2. Add conflict checks against VECTOR's existing scheduler/time-calendar data.
3. Use Google/Outlook calendar APIs only through explicit provider adapters.
4. Require owner approval before accepting external bookings.
5. Keep any public booking frontend separate from the core runtime.

## Acceptance Criteria

- VECTOR does not depend on Cal.diy or its database stack.
- Calendar secrets stay in normal secret handling.
- External booking requests are permission-gated.
- Local scheduler remains source of truth for owner commitments.
- No Cal.diy UI/routes are copied wholesale.

