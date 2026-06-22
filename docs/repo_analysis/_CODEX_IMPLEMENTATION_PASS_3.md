# Codex Repo-Analysis Implementation Pass 3

Date: 2026-06-22

This pass completes the remaining actionable `.md` work as clean-room VECTOR boundaries.
Items marked hard-skip or do-not-absorb in the analysis were not copied or activated.

## Implemented Boundaries

### Cal.diy

- Added `districts/time_calendar/booking.py`
- Provides `AvailabilityWindow`, `BookingRequest`, `CalendarEvent`, conflict checks, and owner-approval requirement.
- No Cal.diy UI, Prisma, Next.js, routes, or database stack copied.

### Evolution API

- Added `districts/communications/providers/whatsapp.py`
- Disabled-by-default `WhatsAppProvider` with official Cloud API as preferred mode and Evolution external endpoint as explicit secondary mode.
- Normalizes inbound payloads and queues outbound text for permission handling.

### HelixDB

- Added `core/memory/external_mirror.py`
- Disabled external mirror boundary; SQLite remains source of truth.

### TurboVec

- Added `core/memory/vector_index_gate.py`
- Keeps NanoVectorDB/LightRAG default below the benchmark threshold; TurboVec only becomes eligible at large corpus scale.

### OpenAlice / Nautilus Trader

- Added `districts/investment/order_lifecycle.py`
- Clean-room staged order lifecycle, risk snapshots, approval-gated live submit, append-only transition list.
- No AGPL/LGPL code or schemas copied.

### Evolver

- Added `core/city/evolution_audit.py`
- Defines `StrategyGene` and `EvolutionEvent` with review-before-apply semantics and rollback notes.

### ECC

- Added `core/security/workspace_audit.py`
- Provides local skill inventory and hook/config review checks without installing external hooks.

### Supertonic

- Added `core/voice/engines/supertonic_engine.py`
- Lazy disabled live-TTS benchmark seam. No heavy package imported at startup.

### LongCat Video

- Extended `core/video/provider_capabilities.py` with a disabled `longcat_external` media provider entry.

## Tests

```powershell
python -m pytest -q tests\backend\test_repo_analysis_optional_boundaries.py
python -m pytest -q tests\backend\test_repo_analysis_security_and_provider.py tests\backend\test_repo_analysis_content_research_training.py tests\backend\test_repo_analysis_voice_sensing_gateway.py tests\backend\test_promoted_repo_upgrades.py
```

## Still Not Implemented By Design

- `text-to-cad`: remains bookmark-only until CAD/hardware becomes an explicit VECTOR district.
- `remotion`: skipped because VECTOR already owns a Playwright/ffmpeg video engine and the license is restrictive.
- `OpenCut`: skipped because the reviewed checkout was a scaffold.
- `voicebox`: skipped/superseded by current voice stack decision.
- `kickbacks.ai`: treated only as a detector pattern; no ad/telemetry behavior added.
- Full heavy installs for OmniVoice, Supertonic, Supervision/YOLO, HelixDB, TurboVec, LongCat, and WhatsApp remain owner/deployment decisions.
