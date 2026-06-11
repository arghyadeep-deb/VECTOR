# Task 07 — Face ID activation

- **Depends on:** Task 03
- **Who:** OWNER + me
- **Effort:** ~15 min

## Objective

`FaceDetector` names the owner instead of returning unknown; `FatigueMonitor`
produces a real EAR score instead of neutral 5.0.

## Implementation

1. Create `data/known_faces/arghyadeep/` with 3-5 clear photos (different
   angles/lighting).
2. `python core/sensing/camera.py` — self-test should detect + name you.
3. Verify fatigue scoring returns a non-5.0 value with mediapipe active.

## Tests

Camera self-test; one frame through `FatigueMonitor.score()`.

## Demo

Sit in front of the webcam → log shows `face: arghyadeep` and a live fatigue
score.

## Acceptance

- [ ] Owner recognized by name from live camera
- [ ] Unknown person reported as unknown (test with a photo of someone else)
- [ ] Fatigue score varies with eyes open vs nearly closed
