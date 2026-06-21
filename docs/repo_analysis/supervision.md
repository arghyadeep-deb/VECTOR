# supervision — Absorption Analysis

**Verdict:** IMPLEMENT (augments sensing) — add as an optional pip dependency behind `core/sensing`, do NOT reimplement.

---

## What it is
`roboflow/supervision` v0.29.0 — a mature, production-grade ("Development Status :: 5 - Production/Stable", `pyproject.toml:28`), **model-agnostic** computer-vision toolkit. It is the glue layer *around* a detection model: you bring any detector (YOLO/Ultralytics, RF-DETR, Transformers, Inference) and supervision handles everything downstream.

- **License:** MIT (`pyproject.toml:19`, `LICENSE.md:1` — Copyright Roboflow). Fully compatible with VECTOR; absorb-by-pip, zero license friction.
- **Install:** `pip install supervision` (pure Python, `requires-python = ">=3.9"`, `pyproject.toml:26`). Deps are all already-or-trivially in VECTOR's stack: `numpy`, `opencv-python`, `pillow`, `scipy`, `matplotlib`, `pyyaml`, `requests`, `defusedxml`, `tqdm` (`pyproject.toml:50-61`). **No torch / no model weights bundled** — it does not pull a heavy ML runtime by itself. `metrics` extra adds only `pandas`.
- **Capabilities** (from `src/supervision/__init__.py:9-156`):
  - **`Detections`** unified container (`detection/core.py`) with `from_ultralytics` / `from_inference` / `from_transformers` connectors + boolean-mask filtering (`detections[detections.class_id == 0]`, see `examples/count_people_in_zone/ultralytics_example.py:89-92`).
  - **`ByteTrack`** multi-object tracker (`tracker/byte_tracker/core.py` — Kalman filter + matching), giving stable `tracker_id` across frames.
  - **`PolygonZone` + `PolygonZoneAnnotator`** (`detection/tools/polygon_zone.py`) — region presence/occupancy counting via `zone.trigger(detections)`.
  - **`LineZone`** (`detection/line_zone.py`) — directional in/out crossing counters.
  - **~25 annotators** (`BoxAnnotator`, `LabelAnnotator`, `HeatMapAnnotator`, `TraceAnnotator`, `BlurAnnotator`, etc., `__init__.py:9-33`) for annotated-frame debugging.
  - **Geometry / draw / NMS / IoU utils**, **`DetectionsSmoother`**, **`InferenceSlicer`** (SAHI tiling), **dataset I/O** (COCO/YOLO/Pascal-VOC load/split/merge/save), **metrics** (`ConfusionMatrix`, `MeanAveragePrecision`), **video utils** (`get_video_frames_generator`, `VideoSink`, `FPSMonitor`), **sinks** (`CSVSink`, `JSONSink`).
  - Ready-made examples that map 1:1 to VECTOR's gap: `examples/count_people_in_zone/`, `examples/time_in_zone/` (dwell-time), `examples/heatmap_and_track/`.

---

## VECTOR already has
- `core/sensing/camera.py` — `FaceDetector` (face_recognition HOG model, identity match against `known_faces_dir`, `camera.py:140-168`) and `FatigueMonitor` (mediapipe Face-Mesh EAR → 0-10 fatigue, `camera.py:249-300`).
- `core/sensing/screen_observer.py`, `health_monitor.py`, `sound_classifier.py` — non-camera ambient sources.
- `core/vision_control/` — `gui_agent.py`, `vision_operator.py`, `action_parser.py`, `browser_controller.py` (qwen2.5-vl GUI automation; this is screen/GUI vision, **orthogonal** to ambient camera perception).
- Loop wiring: `core/loop/autonomous_loop._sense_tick` (`autonomous_loop.py:2012-2030`) calls `FaceDetector().capture_and_scan` and derives a coarse `presence` enum: `absent / present / multiple / unknown_visitor` (counts faces only); fatigue from `HealthMonitor` at `autonomous_loop.py:2037-2040`; presence-change → event at `autonomous_loop.py:2102-2106`.

**Confirmed:** grep across the codebase shows **no `import supervision`, no `ByteTrack`, no `PolygonZone`, no `YOLO`/ultralytics** in any runtime path (the `supervision` substring hits are unrelated config flags / MLOps text). Object/person detection, tracking, and spatial zones do not exist in VECTOR today.

---

## Overlap / what it adds
There is almost **no overlap** — they sit at different layers:

| Capability | VECTOR today | supervision adds |
|---|---|---|
| Person *identity* | `FaceDetector` (face_recognition) | — (keep face_recognition; supervision doesn't do recognition) |
| Person *detection / count* | "count faces in frame" only — fails when owner faces away from camera | true full-body person detection (needs a detector model) → robust head-count |
| *Tracking* across frames | none | `ByteTrack` stable `tracker_id` → "same person stayed 40 min" |
| *Presence zones* | none | `PolygonZone.trigger()` → "is owner at the desk region?" |
| *Dwell / direction* | none | `LineZone` + time-in-zone example → entered/left, time-at-desk |
| Fatigue | `FatigueMonitor` EAR | — (keep mediapipe; out of scope for supervision) |
| Annotated debug frames | none | ~25 annotators → save a labelled JPG when presence is ambiguous |

The face-count heuristic at `autonomous_loop.py:2017-2028` is the weak spot supervision directly upgrades: a person reading on the couch or turned away registers as `absent` to `FaceDetector` (no frontal face), but a person-detection model + `Detections` would still see them as `present`. **Caveat:** supervision is model-agnostic — it needs a detector feeding it. That means a `pip install ultralytics` + a small YOLO weight (~6 MB for `yolo11n`) is the real cost, runnable on the RTX 5070 Ti or even CPU at low FPS. supervision itself stays lightweight.

---

## Relevance to the ambient-perception gap
High. `plans/governor-wiring-and-ambient-perception.md` **Part B** is explicitly about getting richer presence/fatigue/phone/wearable signal into the loop. supervision strengthens the **camera-presence** half of that:
- B.1 (fatigue) is mediapipe's job — supervision does not touch it.
- The **presence quality** problem (B's framing of camera reaching `context_engine` but being coarse) is exactly what supervision fixes: it turns the brittle `absent/present/multiple` face-count into reliable **person-count + per-person tracker_id + desk-zone occupancy + dwell time**. That is materially better "always-on JARVIS" signal: VECTOR could know "owner has been at the desk 90 min, no break" (fatigue + dwell) or "owner left the room 12 min ago" (zone exit) instead of just "no face this frame."
- It does **not** address ADB-phone (B.2) or wearable (B.3) — those are separate sources.

So: supervision is a strong augmentation of the camera observe source that B.1's surrounding context calls for, but it is **complementary**, not a substitute for the rest of Part B.

---

## Integration plan
Absorption rule applied: **use the pip package, reuse the existing sensing seam, reimplement nothing.**

1. **Deps (optional, behind a flag):** add `supervision` + `ultralytics` to an *optional* requirements group; gate behind `CONFIG["sensing"]["object_detection_enabled"]` (default off, like the existing lazy-import pattern in `camera.py:42-54`). Keep graceful-degradation: if libs/weights absent → fall back to today's `FaceDetector`-only presence.
2. **New seam, not a rewrite:** add `core/sensing/presence_detector.py` exposing a `PresenceDetector` that lazily imports `ultralytics.YOLO` + `supervision as sv`, runs person detection (`class_id == 0`), pipes through `sv.ByteTrack` and an optional `sv.PolygonZone` (desk region from config), and returns a richer dict: `{person_count, tracked_ids, in_desk_zone, dwell_seconds}`. Mirror the existing graceful-`[]`/neutral-return contract of `FaceDetector`.
3. **Wire into the loop at one place:** in `autonomous_loop._sense_tick` (`autonomous_loop.py:2013-2030`), when object detection is enabled, prefer `PresenceDetector` output to refine the `presence` enum (e.g. person-detected-but-no-face → `present` instead of `absent`); keep `FaceDetector` for *identity*. No change to the event/`_on_presence_change` plumbing (`autonomous_loop.py:2102-2106`).
4. **Debugging bonus (cheap):** on ambiguous presence, save one `sv.BoxAnnotator`-annotated JPG to a debug dir — turns "why did VECTOR think I left?" into an inspectable artifact.
5. **Effort:** ~1 focused session. New `presence_detector.py` (~120 LOC) + a config flag + a ~6-line refinement in `_sense_tick` + tests mocking the detector (matching the mocked-fatigue test pattern B.1 already established). The owner one-time cost is `pip install ultralytics` and accepting a small YOLO weight download.

---

## Recommendation
**IMPLEMENT, priority MED.** supervision is a textbook absorption candidate: MIT-licensed, pure-Python, lightweight (no torch by itself), production-mature, and it fills a real and currently-empty capability — VECTOR has *face identity* and *EAR fatigue* but **zero general person detection, tracking, or spatial-zone reasoning**, and its presence signal is a brittle frontal-face count that silently mislabels a present-but-turned-away owner as `absent`. Adding `supervision` (+ a tiny YOLO detector) behind a `core/sensing` config flag directly upgrades the camera observe source that the ambient-perception plan is trying to enrich, giving VECTOR robust head-count, per-person dwell time, desk-zone occupancy, and annotated debug frames — exactly the kind of richer presence context an "always-on JARVIS" needs. It is MED rather than HIGH only because (a) it depends on the owner being willing to run a detector model and webcam continuously, and (b) it does not address the ADB-phone/wearable halves of the gap; it is a clean, low-risk, high-leverage augmentation rather than a blocker. Sequence it after Part B.1 (fatigue wiring) lands, reusing the same mocked-sensing test pattern.
