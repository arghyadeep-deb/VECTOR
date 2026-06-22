# LongCat-Video-main - VECTOR Absorption Review

**Verdict:** DO NOT ABSORB the model pipeline into VECTOR. Add only an optional external media-provider/sidecar plan if video/avatar generation becomes a priority.

**Priority:** MEDIUM-LOW

**Effort:** 1 session for a provider-registry entry and sidecar spec; much larger for real local integration and benchmarking

**License:** MIT for repository code. Model weights may have separate Hugging Face / ModelScope terms and must be checked before production or commercial media use.

**Repo size inspected:** About 58 files / 47 MB, excluding git/build/cache/model-weight directories.

## What It Is

LongCat-Video is a foundation video-generation project. The local checkout includes:

- text-to-video, image-to-video, video continuation, and long-video demos
- LongCat-Video-Avatar / Avatar 1.5 audio-driven human video paths
- model pipeline code, DiT modules, block-sparse attention, quantization pieces, Wav2Vec/audio preprocessing
- Streamlit demo entrypoints and installation requirements

The README describes a 13.6B video model, 720p/30fps long-video generation, audio-driven avatar support, and INT8/avatar acceleration options.

## VECTOR Overlap

VECTOR already has its own content/video direction:

- `core/video` render/composer pieces
- content automation districts
- planned media-provider capability registry from the Pixelle review

LongCat is not a missing VECTOR core. It is a possible external media model provider.

## Real Value For VECTOR

Useful clean-room ideas:

- provider capability registry entries for video models
- long-video and video-continuation workflow metadata
- audio-to-avatar generation as a content/studio capability
- sidecar contract for expensive GPU/cloud media jobs

## Risks

- huge model footprint and likely GPU pressure
- weights are not part of the normal code license boundary
- slow install path with CUDA, torch, flash-attn, diffusers, video libraries
- overlaps with existing VECTOR video stack if absorbed directly
- local 12 GB VRAM should not be treated as enough until benchmarked

## Recommendation For Sonnet

Do not copy LongCat pipeline code into VECTOR.

Implement only a narrow optional provider description if wanted:

1. Add a media-provider capability schema if the Pixelle provider-registry work has not already done it.
2. Represent LongCat as a disabled-by-default external provider.
3. Require explicit model-weight/license confirmation before enabling.
4. Route jobs through existing PermissionGateway / task queue controls.
5. Keep all heavy inference out of VECTOR startup.

## Acceptance Criteria

- VECTOR boots with no LongCat dependency installed.
- No LongCat code, demos, or model files are copied into core runtime.
- Provider is disabled by default.
- Missing provider/model returns a clean unavailable status.
- Weight license is documented before any production use.

