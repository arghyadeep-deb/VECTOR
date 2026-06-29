# VECTOR — Open Issues (reconciled 2026-06-29)

Single clean list of what is **genuinely still open**, checked against current
code/state. The headline: **there is no open code work** — everything buildable
has been built, tested, and (for cloud) deployed. Every item below is
owner-gated: physical hardware, a paid/verified account, a deploy step, or a
decision only you can make.

Full per-item evidence lives in `repo_analysis/_MASTER_TODO.md` (source of truth)
and `repo_analysis/OWNER_ACTIONS_NEEDED.md`. This file is the short, current
"what's left" view; the done-work archives were removed.

---

## A. This session's follow-ups (2026-06-29)

1. **Force-push the rewritten history.** Git history was rewritten twice this
   session to strip >100MB blobs (293MB cmake artifact + ONNX models) and the
   `finagent/qt/build/` cruft — GitHub push is now unblocked but needs a force:
   `git push -u origin production-hardening-complete --force`.
2. **Delete the safety backups once the push is confirmed** (~3.4GB total):
   `../vector_git_backup_20260629_180411`, `../vector_git_backup2_*`, and
   `vector_memory.db.premaint.bak.20260629_135132`.

## B. Physical hardware / OS settings (cannot be done from code)

3. **Termux node:** run `bash phone_node/setup.sh` on the Android device — needed
   before the phone↔Legion command relay can be tested end-to-end.
4. **Legion Wake-on-LAN:** enable WoL in BIOS/UEFI + network-adapter settings,
   then set `LEGION_HOST` to Legion's LAN IP in `phone_config.env`. Code
   (`core/control/wake_on_lan.py`, `ambient_server.py`) is built/tested against
   local sockets; only firmware WoL is missing.
5. **`face_recognition`:** installed, but its native `dlib` DLL is blocked by a
   Windows Application Control policy (`ImportError: ... blocked by an Application
   Control policy`). This is an OS security setting only you can change — not a
   missing package. Camera/face features fall back to neutral until then.
6. **"Hey VECTOR" wake word** (scoped-up, not a quick step): openWakeWord's real
   recipe needs `piper-sample-generator` (external TTS, not installed) to make
   thousands of synthetic clips + RIR/background-noise augmentation — not 15
   manual recordings. `core/voice/wake_word.py` falls back to Whisper-chunk
   keyword spotting, so nothing is broken; build this when you actually want it.

## C. Cloud deploy (needs your Cloudflare account/credentials)

7. **`cloud/email` Worker deploy** (separate from the already-live API Worker):
   needs a Cloudflare account/domain, Email Routing, R2 bucket `vector-email`,
   Workers AI, Cloudflare Access, and Worker secrets `POLICY_AUD`/`TEAM_DOMAIN`.
8. **`cloud/email` dependency advisories** (decision): 3 high, dev-only
   (`react-router`/`@react-router/node`/`@react-router/dev`), fixable only via a
   breaking major bump. Not in the deployed Worker runtime. Accept (low real risk)
   or schedule a `react-router` major upgrade + retest.
9. **Cloudflare Worker parity tests** (`api/test/smoke.test.ts`): the harness is
   real and correct but `workerd`'s module loader can't resolve modules because
   this repo's path contains a literal space (`V.E.C.T.O.R. Codebase`). It runs
   in CI (Linux) or any space-free clone path — an upstream tooling limitation,
   not a code bug.

## D. Paid / verified API keys (optional — only for the `last30days` research brief)

10. **Twitter/X, TikTok, Instagram, Polymarket** connectors need paid tiers or
    app-review/business verification. Three free connectors (HackerNews, Reddit,
    GitHub) already work today; the rest stay disabled until you provide keys.

## E. Decisions that need no code — just your choice

11. **Post-training:** flip `post_training_enabled` in `core/config.py` and decide
    when the weekly Sat-04:00 run (`cron_jobs.py::job_post_training_run()`) should
    fire. Gated OFF by default; zero heavy imports until flipped.
12. **Voice engine default:** all engines (Kokoro/OmniVoice/Supertonic) are
    installed with weights downloaded; only Kokoro has real benchmark numbers so
    far. Defaults unchanged (`live_engine="kokoro"`, `cloning_engine="chatterbox"`).
    A/B listening + any default flip is your call.
13. **Optional integrations** (all have disabled-by-default seams; enable only if
    wanted): HelixDB graph-vector mirroring, LongCat-Video, Evolution-API
    (WhatsApp), Cal.diy calendar booking.

---

*All code-side work is closed. Update this file in place as owner actions land.*
