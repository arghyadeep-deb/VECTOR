# Codex Repo-Analysis Implementation Pass 2

Date: 2026-06-22

This pass implements additional VECTOR-native slices from `docs/repo_analysis/_FINAL_CROSSCHECK.md`.
No external repo code was copied. Implementations are clean-room contracts, adapters, and safety layers.

## Implemented

### SkillSpector / ECC / kickbacks-style Security Gate

- Added `core/security/skill_scanner.py`
- Wired `vectorcode/src/skills/loader.py` so blocked skills are quarantined before load/injection.
- Added `districts/security/skill_spector.py`
- Detects:
  - hidden Unicode / bidi deception
  - dangerous inline shell expansion
  - remote-download-to-shell patterns
  - secret-to-network exfil patterns
  - static Python source-to-sink flows
  - wildcard permissions
  - MCP description injection language
  - extension/adware-style hook/prompt mutation signals

### OmniRoute Provider Resilience

- Added `core/inference/provider_health.py`
- Added `core/inference/provider_registry.py`
- Wired `core/inference/provider_client.py` to skip cooled-down/disabled provider-model routes and record success/failure health.

### QuantMind Paper Ingestion

- Added `districts/research/paper_ingestion.py`
- Added `PaperInput`, `PaperArtifact`, `PaperNode`, citations, source refs, extraction refs, stable hashes, and `embedding_text()`.
- Wired `PaperReader.run()` with `ingest_paper`, `paper_card`, and `summarize_paper_tree` task types.

### Pixelle Video Planning

- Added `districts/content/asset_video_pipeline.py`
- Added `core/video/provider_capabilities.py`
- Added `core/video/workflow_resolver.py`
- Wired content and video package exports.

### train-llm-from-scratch Post-Training Only

- Added `core/training/alignment_dataset.py`
- Supports SFT examples and DPO-style chosen/rejected pairs from VECTOR reasoning/outcome records.
- No from-scratch pretraining was added.

### OmniVoice / Supervision / Open WebUI Compatibility

- Added lazy optional OmniVoice adapter: `core/voice/engines/omnivoice_engine.py`
- Added optional presence detector seam: `core/sensing/presence_detector.py`
- Added minimal OpenAI-compatible gateway router: `core/api/routers/openai_compat.py`
- Mounted `/v1/models` and `/v1/chat/completions` in `core/api/app.py`.

### Existing Gap Fixed During Verification

- Fixed `districts/skills/gap_analyst.py` fake-success `run()` routing bug exposed by adjacent tests.

## Tests

```powershell
python -m pytest -q tests\backend\test_repo_analysis_security_and_provider.py
python -m pytest -q tests\backend\test_repo_analysis_content_research_training.py
python -m pytest -q tests\backend\test_repo_analysis_voice_sensing_gateway.py
python -m pytest -q tests\backend\test_promoted_repo_upgrades.py
python -m pytest -q tests\test_youtube_trends.py tests\test_seo_scorer.py tests\test_research_district.py tests\training\test_data_collector.py
python -m pytest -q tests\test_skills_run_wiring.py tests\test_security_district_run_wiring.py tests\unit\test_resilience.py
```

## Still Deferred By Design

- Full OmniVoice model install/benchmark.
- Supervision/YOLO runtime install and webcam loop wiring.
- Streaming SSE for `/v1/chat/completions`.
- HelixDB, turbovec, LongCat, WhatsApp provider, Cal.diy booking, and CAD remain optional/deferred.
- Remotion, OpenCut, voicebox, and kickbacks behavior remain skipped.
