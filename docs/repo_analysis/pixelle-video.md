# Pixelle-Video-main - VECTOR Absorption Review

**Verdict:** IMPLEMENT two narrow content-pipeline improvements; skip the engine.

**Priority:** MEDIUM

**Effort:** 1-2 focused sessions

**License:** Apache-2.0

**Repo size inspected:** ~313 files / ~10.5 MB

## What It Is

Pixelle-Video is a Python short-video automation engine. It takes a topic or script, generates narration, creates per-frame image/video prompts, calls media providers or ComfyUI/RunningHub workflows, renders frame templates, adds voice and BGM, and exports a finished short video.

The useful architecture pieces are:

- a linear storyboard pipeline: script -> scenes -> prompts -> per-frame media -> segments -> final video
- asset-based pipeline: analyze user-provided images/videos, write script from those assets, match assets to scenes
- provider capability registry for direct video/image APIs
- standardized workflow naming for `runninghub` vs `selfhost`

## VECTOR Already Has

- `districts/content/video_pipeline.py`: topic -> script/TTS/render/captions/upload pipeline
- `districts/content/video_generator.py`, `caption_generator.py`, `video_merger.py`, `voice_generator.py`, `uploader.py`
- `districts/content/comfyui_adapter.py`: local ComfyUI integration
- `core/video/vector_composer.py`: HTML composition -> browser frame capture -> audio mix -> ffmpeg encode
- `core/video/html_renderer.py`, `video_encoder.py`, `audio_mixer.py`, `studio_server.py`

VECTOR is already stronger than Pixelle in ownership of the render engine. Pixelle should not replace it.

## Overlap

Approximate overlap: **75-80%**.

Both systems automate short-video production, TTS, BGM, image/video generation, templates, and ffmpeg composition. Pixelle's engine would duplicate VECTOR's content district and `core/video` stack.

## Real Gaps Worth Absorbing

1. **Asset-based content pipeline.** The useful gap is "given my photos/videos, analyze them, generate a script, match each scene to existing assets, and render a marketing/story video."

2. **Provider capability registry.** Pixelle keeps structured metadata for video/image providers, including supported modalities, duration ranges, ratios, fps, and known contract issues. VECTOR's ComfyUI/provider paths would benefit from a small capability registry before choosing a model/workflow.

3. **Standard workflow resolver.** Pixelle's `source/service.json` convention is simple but useful. VECTOR can use an equivalent convention for `local`, `cloud`, `comfyui`, and future provider workflows.

## What Not To Absorb

- Do not import Pixelle as a package.
- Do not copy its Streamlit/FastAPI UI.
- Do not replace `VectorComposer`.
- Do not duplicate `video_pipeline.py`.
- Do not add RunningHub as a required cloud dependency.
- Do not copy provider tables verbatim. Recreate only the provider capabilities VECTOR actually uses.

## Implementation Plan For Sonnet

1. Add `districts/content/asset_video_pipeline.py`.
   - `AssetVideoPipelineAgent(AgentBase)`.
   - Accept `assets`, `intent`, `duration`, `title`, `orientation`, `bgm_path`.
   - Analyze images/videos using existing vision/image-analysis paths if available; otherwise use filename + lightweight metadata fallback.
   - Output a `Storyboard` with scenes, selected asset path, narration, duration, and render variables.

2. Add `core/video/provider_capabilities.py`.
   - Define `MediaProviderCapability` and `MediaModelCapability`.
   - Include modality, duration min/max, aspect ratios, fps, input requirements, and safety notes.
   - Register only providers already configured in VECTOR.
   - Return clear "not configured" results when keys/workflows are absent.

3. Add `core/video/workflow_resolver.py`.
   - Resolve `{source}/{service}.json` under VECTOR's own workflow/template directories.
   - Validate path stays under allowed roots.
   - No network calls.

4. Wire carefully.
   - Add optional route/action in `districts/content/video_pipeline.py` or the content orchestrator.
   - Use `VectorComposer` for rendering.
   - Use existing TTS stack.
   - Gate upload/publish through existing scheduling/upload safety paths.

5. Add tests.
   - Asset storyboard generation with fake assets.
   - Missing asset returns structured error.
   - Capability registry returns deterministic provider/model metadata.
   - Workflow resolver rejects path traversal.
   - Existing content tests still pass.

## Acceptance Criteria

- User can pass 2-5 local assets and get a storyboard without needing ComfyUI.
- Rendering still goes through `core/video/vector_composer.py`.
- No provider keys are required for unit tests.
- Path traversal in workflow names is blocked.

## Final Recommendation

Absorb Pixelle's **asset-aware storyboard flow** and **provider capability registry**. Skip the rest. VECTOR already owns the video engine; Pixelle's value is a better planning layer for user-provided media and a cleaner way to select optional media providers.
