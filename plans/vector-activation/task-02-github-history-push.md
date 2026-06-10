# Task 02 — GitHub scrubbed-history push

- **Depends on:** Task 01
- **Who:** OWNER decides → me
- **Effort:** ~20 min

## Objective

GitHub no longer serves the secret-bearing history. Local history is already
scrubbed (verified `git log --all -- .env` → empty; backup bundle at
`../VECTOR-backup-20260611.bundle`). The force-push is blocked because history
contains 4 blobs >100MB (kokoro ×2, piper, a 293MB cmake `.gch`).

## Owner decision (pick one)

- **(a) Strip + push (recommended):** authorize
  `git filter-repo --strip-blobs-bigger-than 100M --force`. Models are backed
  up at `../model-backup-20260611/` and get restored to disk + gitignored
  (`models/**/*.onnx`) afterward. Then `git push origin main --force`.
- **(b) Recreate:** delete the GitHub repo, create fresh, push scrubbed history.
- **(c) Leave stale:** GitHub keeps old history; rotation (Task 01) is then the
  only mitigation.

## Tests / Demo

On GitHub: `.env` absent from history; repo clones and `run_vector.py smoke`
passes from a fresh clone.

## Acceptance

- [ ] Owner picked an option and it executed without data loss
- [ ] `models/kokoro/*.onnx` + `models/piper/*.onnx` still on disk
- [ ] If (a)/(b): GitHub history has no `.env` and no >100MB blobs
