# VECTOR Remaining Work — 2026-06-20

Everything that was a code issue is fixed and verified (full test suite:
exit 0, zero failures, re-confirmed live multiple times). What's left is not
code — it's two decisions only the owner can make.

## 1. Phone Termux node setup

Code is done (`phone_node/ambient_server.py`, `phone_node/setup.sh`) but has
never been run. Needs the physical old Android device in hand — install
Termux, run `setup.sh`, point it at `VECTOR_BRAIN_URL` + `VECTOR_API_KEY`.

## 2. Wake word training path

15 real "Hey VECTOR" samples are already recorded (`models/wake/samples/`),
but `openwakeword`'s training pipeline has since moved to a synthetic-data
model (Piper TTS generation + background-noise/RIR datasets) that 15 real
clips alone can't satisfy. Pick one:

- Set up the full synthetic pipeline (clone Piper sample generator, download
  background/RIR datasets) — most robust, real time/disk cost.
- Downgrade `openwakeword` to the version the original simple
  record-and-train flow assumed.
- Skip custom wake word training for now; revisit later as its own task.
