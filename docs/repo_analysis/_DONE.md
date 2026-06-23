# Repo Absorption — 24 DONE + 6 closed-by-decision (consolidated)

**Date:** 2026-06-23. Supersedes the individual per-repo `.md` files this
consolidates (removed from this directory — their content is folded in
below). Source of truth for "is X done" is `_MASTER_TODO.md` §2; this file
is the evidence archive for the ✅ rows there, plus (from item 25 onward)
the SKIP/reference items that are closed by decision rather than by code.
Don't re-investigate these — re-verify only if something here turns out to
be wrong (see the self-correction rounds noted in `_MASTER_TODO.md` for
why that's a real possibility, not a hypothetical).

**"DONE" means:** the gap identified in `_FINAL_CROSSCHECK.md` is closed —
either a narrow real feature is implemented and wired (`IMPLEMENT` verdicts),
or a clean-room seam/concept exists matching the verdict's own stated scope
(`Optional sidecar` / `Clean-room only` / `HOLD` / `scale-gated` verdicts).
For the latter group, an **owner action may still remain** (a heavy package
install, an external account/API key, or a default-flip decision) — that's
tracked but does not block "done," since the code-side gap the crosscheck
identified is genuinely closed.

---

## 1. SkillSpector
**Verdict:** IMPLEMENT, do first (security gate for everything else absorbed).
**Files:** `core/security/skill_scanner.py`, `districts/security/skill_spector.py`, `vectorcode/src/skills/loader.py:313-341`.
**Evidence:** Fail-**closed** confirmed directly — a scanner error blocks (raises `ValueError`, doesn't warn-and-load). Manifest-registered (`scripts/manifest_gap.py` 0 hits for this class) and dispatch-verified through `Governor().dispatch()` — returned a real scan verdict on a live file. Detects hidden Unicode/bidi deception, dangerous shell expansion, remote-download-to-shell, secret-exfil patterns, static taint flows, wildcard permissions, MCP description injection, extension/adware signals.
**Owner action:** none.

## 2. auto-browser
**Verdict:** IMPLEMENT (browser action governance).
**Files:** `core/browser/governance.py`, `core/loop/permission_gateway.py::request_approval()`, `core/vision_control/browser_controller.py`, `core/mcp_tools/browser.py`.
**Evidence:** GREEN/YELLOW/RED/UNKNOWN classification, receipts (screenshot SHA-256 hashing, PII redaction). RED actions now route through `PermissionGateway.request_approval()` (a new approval-only helper — doesn't delegate execution since browser actions must resume the live Playwright page, not redispatch through the governor) and proceed on owner approval instead of hard-blocking unconditionally. 68/68 gateway tests + 3 new controller tests pass.
**Not done (lower priority, doesn't block):** persistent receipt storage, human-takeover state, `mcp_tools/browser.py`'s narrower YELLOW-default edge case.

## 3. headroom
**Verdict:** IMPLEMENT (context-budget manager).
**Files:** `districts/memory_curator/context_budget.py`, wired into `core/inference/provider_client.py::chat()`.
**Evidence:** Was completely unwired (confirmed via grep: zero callers anywhere) before this pass. Added `_persist_handle()` (episodic memory, never raises), `get_context_budget_manager()` singleton, wired into every LLM call — compacts oversized messages before they reach a provider, no-op for normal-sized ones. 6 new tests + full smoke/regression pass.
**Owner action:** none. Per-provider telemetry beyond the existing log line not attempted (lower value).

## 4. OmniRoute
**Verdict:** IMPLEMENT (provider resilience, narrow scope only — not the full TS gateway).
**Files:** `core/inference/provider_health.py`, `core/inference/provider_registry.py`, wired into `provider_client.py`.
**Evidence:** Skips cooled-down/disabled provider-model routes, records success/failure health. Narrow scope as specified — no full gateway absorbed (stealth/free-tier/OAuth-bypass surfaces correctly not copied).
**Owner action:** none.

## 5. train-llm-from-scratch (post-training only)
**Verdict:** IMPLEMENT (post-training only — from-scratch pretraining explicitly out of scope, needs H100s).
**Files:** `core/memory/counterfactual.py::get_all_rejections()`, `core/training/reasoning_chain_dataset.py`, `core/training/post_training/sft_trainer.py`, `core/training/post_training/dpo_trainer.py`, `core/config.py::TrainingConfig`, `core/loop/cron_jobs.py::job_post_training_run()`.
**Evidence:** Closes the loop — VECTOR reasons → stores `reasoning_chains` → trains its own LoRA adapter on them. Wired to real `ReasoningMemory`/`CounterfactualMemory` reads (not the generic, unwired `alignment_dataset.py` shape that predated this). `run_sft()`/`run_dpo()` delegate to `LoRATrainer`'s established try-real-library/simulate-fallback convention. Export wiring to `OllamaExporter` included. Gated behind `post_training_enabled` (default `False`) + weekly cron (Sat 04:00), zero heavy imports when disabled. 19 new tests across 5 files, zero regressions (`pytest -k cron` 41/41).
**Owner action:** `pip install peft trl` for real training instead of the simulated-but-real pipeline; decide when to flip `post_training_enabled`; the actual overnight run is owner-scheduled.

## 6. youtube-automation-agent
**Verdict:** IMPLEMENT (3 narrow gaps — trending harvest, competitor analysis, SEO scorer/chapter builder; 85% was already duplicate of `districts/content/`).
**Files:** `districts/content/youtube_trends.py` (`YouTubeTrendScout`).
**Evidence:** Manifest-registered. `pytest tests/test_youtube_trends.py tests/test_seo_scorer.py` → 25/25 passing.
**Owner action:** none.

## 7. supervision
**Verdict:** IMPLEMENT (ambient sensing — upgrades the brittle frontal-face-only presence check).
**Files:** `core/sensing/presence_detector.py`.
**Evidence:** Read in full — complete YOLO+ByteTrack detection logic, dwell-time tracking, `in_desk_zone`, graceful fallback to the existing face detector when unavailable. Not a stub; the only remaining gap is the heavy install.
**Owner action:** `pip install supervision ultralytics` + `yolo11n.pt` weights (confirmed neither package is pip-installed in this environment).

## 8. quant-mind
**Verdict:** IMPLEMENT (paper-ingestion contract).
**Files:** `districts/research/paper_ingestion.py`, wired into `PaperReader.run()`.
**Evidence:** `PaperInput`/`PaperArtifact`/`PaperNode`, citations, source/extraction refs, content hashes, `embedding_text()`. Task types `ingest_paper`/`paper_card`/`summarize_paper_tree` confirmed wired in `paper_reader.py`.
**Owner action:** none.

## 9. Pixelle-Video
**Verdict:** IMPLEMENT (asset-based storyboard + media-provider capability registry; skip the Streamlit/FastAPI engine duplication).
**Files:** `districts/content/asset_video_pipeline.py` (`AssetVideoPipelineAgent`), `core/video/provider_capabilities.py`, `core/video/workflow_resolver.py`.
**Evidence:** Was genuinely unregistered until this session's re-audit (same discrepancy as SkillSpector — see `_MASTER_TODO.md`'s correction note). Now manifest-registered and dispatch-verified: correctly validated a deliberately-empty test input rather than crashing.
**Owner action:** none.

## 10. competitor-x-ray
**Verdict:** VET/IMPLEMENT (workflow, not a skill import).
**Files:** `districts/marketing/competitor_xray.py`, `districts/marketing/competitor_intel_agent.py::build_xray_brief()`.
**Evidence:** Converts the agent's existing real LLM competitor research into the evidence-tiered brief schema (CONFIRMED/REPORTED/INFERRED/NOT_FOUND tiers) — LLM findings tagged INFERRED, not CONFIRMED, since no independent source verification happens (documented in the method's own docstring). New `xray_brief` task type wired into `run()`. Manifest capabilities corrected to match real dispatch (was `[competitor_intel]`, a thematic tag matching nothing `run()` actually dispatches on). 3 new tests.
**Owner action:** none.

## 11. VoxCPM
**Verdict:** HOLD — revisit only if OmniVoice fails quality/cloning/VRAM/setup/multilingual tests.
**Files:** `core/voice/voxcpm_cloning.py`, `core/voice/cloning.py::get_cloner()`.
**Evidence:** Wired as an opt-in alternative (`cloning_engine="voxcpm"`), but `core/config.py:193` confirms the default is `"chatterbox"`, not VoxCPM — the hold is genuinely respected, not silently overridden.
**Owner action:** none unless OmniVoice's eventual real benchmark (see `_MASTER_TODO.md` §5.1) fails.

## 12. turbovec
**Verdict:** UPGRADE, scale-gated — only matters above ~1M vectors, never default.
**Files:** `core/memory/vector_index_gate.py::decide_vector_index_backend()`.
**Evidence:** Real scale-gate logic — keeps NanoVectorDB/LightRAG as the default below a 1,000,000-vector threshold; TurboVec only becomes `should_enable=True` above it, and even then notes "benchmark before default flip." Exactly the intended scope — never silently defaults.
**Owner action:** none until corpus scale demands it.

## 13. HelixDB
**Verdict:** Optional sidecar — graph-vector mirror, must not replace the SQLite hot path.
**Files:** `core/memory/external_mirror.py` (35 lines).
**Evidence:** Disabled external mirror boundary; SQLite remains source of truth, exactly as specified.
**Owner action:** none unless graph-vector mirroring is wanted later.

## 14. LongCat-Video
**Verdict:** Optional external provider — license/weights need separate checks; useful only as a disabled registry entry.
**Files:** `core/video/provider_capabilities.py` (`longcat_external` entry).
**Evidence:** A disabled `MediaProviderCapability` registry entry (long video / audio-to-avatar sidecar, `configured=False`, `local=False`) — matches the verdict's own exact scope ("useful only as a disabled provider-registry/sidecar entry").
**Owner action:** real integration + license verification if long-video/avatar work is ever wanted.

## 15. Evolution API
**Verdict:** Optional WhatsApp provider — official WhatsApp Cloud API should be preferred for production.
**Files:** `districts/communications/providers/whatsapp.py` (60 lines).
**Evidence:** Disabled-by-default `WhatsAppProvider`, official Cloud API as the preferred mode, Evolution as an explicit secondary mode. Normalizes inbound payloads, queues outbound text for permission handling.
**Owner action:** none unless WhatsApp messaging is activated.

## 16. Cal.diy
**Verdict:** Optional concept source — small availability/booking adapters, not a full Cal.com fork.
**Files:** `districts/time_calendar/booking.py` (62 lines).
**Evidence:** `AvailabilityWindow`, `BookingRequest`, `CalendarEvent`, conflict checks, owner-approval requirement. No Cal.diy UI/Prisma/Next.js/database stack copied.
**Owner action:** none unless real booking/scheduling integration is wanted.

## 17. Evolver
**Verdict:** Clean-room only (GPL-3.0-or-later) — VECTOR already has HP/ghost-memory evolution; use only event/gene/audit ideas.
**Files:** `core/city/evolution_audit.py` (45 lines).
**Evidence:** Read in full — pure dataclasses/enum (`EvolutionEvent`, `EvolutionStatus`, `StrategyGene`), review-before-apply + rollback semantics. Explicit "Clean-room" docstring; zero GPL or "Evolver" string traces.
**Owner action:** none.

## 18. ECC
**Verdict:** Vet/selective clean-room — skill inventory, hook/config audit ideas only; do not bulk-install.
**Files:** `core/security/workspace_audit.py` (40 lines).
**Evidence:** `audit_skill_inventory()`, `audit_hook_configs()` — local-only checks, no external hooks installed.
**Owner action:** none.

## 19. OpenAlice
**Verdict:** Clean-room only (AGPL-3.0-only) — staged order lifecycle, broker-boundary ideas only.
**Files:** `districts/investment/order_lifecycle.py` (79 lines, shared with item 20).
**Evidence:** `OrderState` enum, `RiskSnapshot`/`StagedOrder` dataclasses, `transition_order()` — staged/append-only transitions, approval-gated live submit. No AGPL code/schemas copied.
**Owner action:** none unless stronger real-money readiness is wanted.

## 20. Nautilus Trader
**Verdict:** Clean-room only (LGPL-3.0-or-later) — staged orders, risk snapshots, paper/live parity ideas only.
**Files:** Same `districts/investment/order_lifecycle.py` as item 19 — one implementation satisfies both verdicts' clean-room scope.
**Owner action:** none unless stronger real-money readiness is wanted.

## 21. supertonic
**Verdict:** UPGRADE — config-selectable live-conversation TTS engine, alternate to Kokoro (NOT the cloning role — that stays VoxCPM/Chatterbox via `cloning_engine`).
**Files:** `core/voice/supertonic_tts.py` (`SupertonicTTS`, `get_live_tts()`, `map_lang_code()`), 4 new `VoiceConfig` fields, wired into `core/voice/tts.py::speak()` via `_speak_supertonic()`.
**Evidence:** Built per the doc's own integration plan almost exactly as specified — lazy guarded-import wrapper, factory mirroring `get_cloner()`'s pattern, en/hi/ja mapped directly, bn/as explicitly excluded and confirmed to stay on the existing gTTS route. 10 new tests + 168/168 voice-suite regression clean. The pre-existing `core/voice/engines/supertonic_engine.py` (thinner, benchmark-only) is untouched — different purpose, still used by the voice-engine benchmark harness.
**Owner action:** `pip install supertonic`, ~260MB model download, pick/build a persona voice JSON, A/B against Kokoro's `bf_emma` before flipping the `live_engine` default.

## 22. open-webui
**Verdict:** Gateway, not absorption — become OpenAI-API-compatible so Open WebUI (or any compatible client) can talk to VECTOR, never embed its code/UI (source-available license with branding restrictions).
**Files:** `core/api/routers/openai_compat.py` — `GET /v1/models`, `POST /v1/chat/completions` (non-streaming + streaming).
**Evidence:** Added SSE streaming for `stream: true` (`StreamingResponse`, `text/event-stream`, `chat.completion.chunk` framing ending in `data: [DONE]`). Honest scope: buffered framing over the existing non-streaming `ProviderClient.chat()` call (one content chunk + a final empty-delta finish-reason chunk), not real per-token incremental streaming — `provider_client.py` has zero per-provider streaming support across its ~27 backends, and rewiring all of them is real, separate, much larger work, not attempted. Still satisfies the doc's actual goal (an OpenAI-compatible client can connect and receive valid SSE framing) regardless of chunk granularity. 3 new tests replacing the old "rejects streaming" placeholder; full FastAPI app build (390 routes) + smoke verified.
**Owner action:** none for the gateway itself. If real per-token streaming is ever wanted, that's separate provider-layer work, not gateway work.

## 23. crawl4ai
**Verdict:** IMPLEMENT narrow crawler/extraction upgrade — VECTOR-native provider wrapper, not the full Crawl4AI server/Docker stack.
**Files:** `core/research_engine/content_fetcher/extraction.py` — `WebExtractionArtifact` contract (pre-existing), `Crawl4AIProvider` + `persist_extraction_artifact()` (new this pass). SSRF guard: `core/research_engine/security/ssrf_validator.py`, `core/research_engine/security/__init__.py`, `core/research_engine/research_library/services/download_service.py`.
**Evidence:** All "Recommendation For Sonnet" items closed within what's buildable without the real package. **SSRF tests** surfaced a real, live bug — `validate_url()` crashed with an uncaught `ModuleNotFoundError` on every single call (not just edge cases) because an unconditional settings lookup transitively imports a missing `core.research_engine.web` package; fixed with a safe-default fallback. **`Crawl4AIProvider`**: disabled-by-default, guarded import, normalizes the real package's output into the same `WebExtractionArtifact` contract every other extraction path uses. **`persist_extraction_artifact()`**: stores extraction results via `EpisodicMemory`, never raises. Both added directly to `extraction.py` (pure stdlib, zero problematic imports) rather than wired through `fetcher.py` — `fetcher.py` and every other caller checked are themselves currently un-importable in this checkout, hitting the same missing `web` package via 3+ independent paths (separate, larger, structural gap — tracked, not fixed wholesale here). 6 + 6 = 12 new tests across this and the SSRF pass.
**Owner action:** none for the gap as scoped. Fixing the missing `core.research_engine.web` package (a real, separate structural issue, not specific to crawl4ai) remains open — see `_MASTER_TODO.md` §3 item 12.

## 24. kickbacks.ai (detector rule only)
**Verdict:** HARD SKIP the product (proprietary ad-injection VS Code extension) — the only legitimate takeaway is a defensive SkillSpector detection rule for the pattern it represents.
**Files:** `core/security/skill_scanner.py:127-132,246` — `_KICKBACKS_STYLE` regex, `"extension_adware"` finding category (HIGH severity).
**Evidence:** This rule already existed before this session — it had been wrongly carried forward as "no detector rule built yet" in an earlier pass of this same audit. Confirmed it genuinely works (fires on ad-injection/extension-hook text and claude_config+sponsored-prompt text, doesn't false-positive on ordinary skill text) and added the test coverage that was missing: `tests/test_skill_scanner_adware_detection.py` (4 tests, including a `scan_artifact()` end-to-end check that a kickbacks-style file gets flagged CAUTION/DO_NOT_LOAD). Zero kickbacks source code copied — detection patterns only, clean-room.
**Owner action:** none.

## 25. last30days-skill
**Verdict:** VET/IMPLEMENT after SkillSpector — recency-first research mode, clean-room only (the upstream skill itself is untrusted prompt/tool material).
**Files:** `districts/research/last30days.py` (schema), `districts/research/last30days_connectors.py` (4 connectors + fan-out).
**Evidence:** Every genuinely accessible free source now has a connector: `connect_hackernews()` (reuses `ResearchHub.get_hn_top()`), `connect_reddit()` (reuses `RedditMiner.fetch_hot()`), `connect_github()` (reuses `ResearchHub.get_github_trending()`), `connect_web_search()` (reuses `WebScout().search()` — DuckDuckGo, no key). All first-party, already-tested data sources, not third-party skill text. `connect_all()` fans out and merges; one connector's failure only degrades, never takes the whole brief down. 9 tests. **Verified-blocked, not skipped out of caution**: live-tested Bluesky's public search endpoint via WebFetch — got HTTP 403 (ambiguous: auth-required or bot-blocked, either way not reliably usable from here, so no connector was shipped for it rather than risk an unverified integration).
**Owner action:** Twitter/X, TikTok, Instagram, Polymarket all need paid/app-review API access — see `OWNER_ACTIONS_NEEDED.md`. YouTube transcript fetching exists (`core/stealth_browser/transcripts.py`) but needs a known video URL, not a discovery mechanism — doesn't fit this model without a paid YouTube Data API key for search/trending.

---

# Skipped / reference-only — no code action needed (5 repos + 1 strategy doc)

These were never "implement" verdicts — closed by decision, not by code. Consolidated here for the same reason as the 24 above: their individual `.md` files added no further information once distilled.

## 26. remotion — SKIP
**Why:** VECTOR independently built the *same* architecture Remotion uses (deterministic headless-Chromium frame-seek capture of animated HTML/CSS/JS → ffmpeg encode) in `core/video/vector_composer.py` + `html_renderer.py` + `vector_runtime.js`, including GSAP/anime.js/WAAPI adapters. Zero real capability gap — only an authoring-ergonomics delta (React/JSX vs. Python-generated HTML). Decisive factor: Remotion's source-available license mandates a paid Company License the instant VECTOR's content/agency districts operate commercially at any scale.
**Revisit only if:** VECTOR's home-grown composer proves inadequate for complex motion graphics AND the licensing cost is acceptable. Neither is true today.

## 27. OpenCut — SKIP
**Why:** The checked-out repo is a scaffold — Bun/TanStack/Cloudflare web shell with no editor core, timeline engine, rendering API, plugin runtime, or headless renderer yet (all "coming" per its own README). Nothing to absorb from the current code.
**Revisit only if:** the project ships a real headless/programmatic editor API later.

## 28. text-to-cad — SKIP
**Why:** VECTOR has zero CAD/3D capability (confirmed — no cadquery/build123d/STL/STEP hits anywhere). That's by design, not a gap: CAD/robotics/3D-printing is off-mission for this owner's software-builder JARVIS. The repo's actual polished value (React/Three.js viewer, agent-skill prompt scaffolding) is exactly the part VECTOR can't use; the portable Python slice reduces to "add build123d as a dependency," which isn't an absorption.
**Revisit only if:** the owner explicitly pivots to hardware/robotics/3D-printing — bookmark this as the starting point (build123d directly, skip `cadpy`/the viewer fork).

## 29. voicebox — SKIP, with one real unaddressed gap
**Why mostly skip:** This is the same repo VECTOR already absorbed 2026-05-27 (`core/voice/cloning.py`, `voice_profiles.py`, `effects.py`) — re-absorbing would be pure duplication.
**The one genuinely new, never-built gap:** **system-wide dictation** — Whisper STT → inject text into whatever OS window currently has focus (not VECTOR's own UI). VECTOR has the STT half (`core/voice/stt.py`) and the keystroke-injection half (`core/control/pc_controller.py`, already used for vision-guided PC control) but nothing wires them together for this specific "dictate into any app" use case.
**This is a feature decision, not a bug** — flagging it here rather than building it unprompted, since it's owner-preference-gated (do you actually want push-to-talk-into-any-app?) and security-sensitive (the original analysis explicitly says: gate it through `PermissionGateway`, since it writes keystrokes into arbitrary apps). Estimated ~half a session if wanted.

## 30. awesome-llm-apps — REFERENCE ONLY
**Why:** A large (1653-file) cookbook of standalone LLM/agent/RAG templates, Apache-2.0. Mine occasional patterns from it; never bulk-absorb. No specific action pending.

## 30. Voice stack decision (`voice-stack-decision.md`, a cross-cutting strategy note, not a single repo)
**Decision:** one live engine (Kokoro, with supertonic as a benchmarked alternative), one high-quality studio/cloning engine (OmniVoice, with VoxCPM on hold), pyttsx3/gTTS as fallbacks — explicitly avoiding "implement every voice repo" engine sprawl.
**Status: fully executed and confirmed**, all 6 acceptance criteria met as of this session: only one live TTS default exists (`live_engine="kokoro"`); only one cloning/design engine is active by default (`cloning_engine="chatterbox"`, VoxCPM on hold); OmniVoice does not load at startup (`enabled=False`, lazy `_load()`); heavy voice models respect the model-residency lock (CPU-only Supertonic, lazy-loaded OmniVoice); 168/168 existing voice tests still pass; pyttsx3/gTTS fallbacks remain in place and untouched.

---

*Consolidated from: `SkillSpector.md`, `auto-browser.md`, `headroom.md`, `omniroute.md`, `train-llm-from-scratch.md`, `youtube-automation-agent.md`, `supervision.md`, `quant-mind.md`, `pixelle-video.md`, `competitor-x-ray.md`, `VoxCPM.md`, `turbovec.md`, `helix-db.md`, `longcat-video.md`, `evolution-api.md`, `cal-diy.md`, `evolver.md`, `ecc.md`, `openalice.md`, `nautilus-trader.md`, `supertonic.md`, `open-webui.md`, `crawl4ai.md`, `kickbacks-ai.md`, `remotion.md`, `opencut.md`, `text-to-cad.md`, `voicebox.md`, `awesome-llm-apps.md`, `voice-stack-decision.md` (all removed from this directory).*
