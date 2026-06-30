# Growth Engine — Implementation Plan

**Goal:** Build `districts/growth/` — two never-die asyncio arms (daily brand reels + issue→software→beta), reusing existing agents, every outward action permission-gated.
**Architecture:** A conductor (`growth_orchestrator.py`) runs ARM A (`content_arm.py`) and ARM B (`software_arm.py`) as independent never-die coroutines. New media component `hud_recorder.py` (Playwright→ffmpeg). `beta_signup.py` + a FastAPI route handle gated PII capture. All knobs in `core/config.py` `growth` section.
**Files:**
- Create: `districts/growth/__init__.py`, `growth_orchestrator.py`, `content_arm.py`, `software_arm.py`, `hud_recorder.py`, `beta_signup.py`
- Create: `core/api/routers/growth.py`, `tests/test_growth_*.py`, `plans/GROWTH_ENGINE_STATUS.md`
- Modify: `core/config.py` (growth section), `core/api/app.py` (register router)

> Reuse map in `plans/GROWTH_ENGINE_AUDIT.md`. Design in `plans/GROWTH_ENGINE_DESIGN.md`.
> Commits: no `Co-Authored-By` trailer (owner preference). Heavy externals (Playwright, ffmpeg, uploads, LLM) mocked in tests — we test orchestration logic, not third parties.

---

### Task 1: Config — `growth` section
- [ ] Write failing test `tests/test_growth_config.py`
  ```python
  def test_growth_config_defaults():
      from core.config import CONFIG
      g = CONFIG["growth"]
      assert g["enabled"] is False and g["auto_publish"] is False
      assert g["instagram_mode"] == "manual"          # human-in-loop default
      assert g["hud_viewport"] == [1080, 1920]         # 9:16
      assert g["brand_line"] and g["review_loop_max_iterations"] >= 1
  ```
- [ ] Run: `pytest tests/test_growth_config.py -v` → expect FAIL
- [ ] Add `growth` dict to `core/config.py` CONFIG (keys per design §Config)
- [ ] Run: `pytest tests/test_growth_config.py -v` → expect PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): config section, defaults off + gated"`

### Task 2: `hud_recorder.py` — Playwright HUD video capture
- [ ] Write failing test `tests/test_growth_hud_recorder.py` (Playwright + ffmpeg mocked)
  ```python
  def test_recorder_9x16_and_triggers_live_task(monkeypatch, tmp_path):
      from districts.growth import hud_recorder as hr
      calls = {}
      monkeypatch.setattr(hr, "_playwright_capture",
          lambda url, vp, dur, on_ready: (calls.update(vp=vp, ready=on_ready()) or str(tmp_path/"hud.webm")))
      monkeypatch.setattr(hr, "_ffmpeg_mux", lambda v, a, out, captions: str(tmp_path/"reel.mp4"))
      rec = hr.HUDRecorder()
      out = rec.record(narration_wav=str(tmp_path/"n.wav"), duration_s=12.0,
                       trigger_task=lambda: calls.setdefault("task", True))
      assert out.endswith(".mp4")
      assert calls["vp"] == (1080, 1920)   # vertical
      assert calls.get("task") is True      # live task fired during capture window
  def test_recorder_degrades_without_playwright(monkeypatch):
      from districts.growth import hud_recorder as hr
      monkeypatch.setattr(hr, "_PLAYWRIGHT_OK", False)
      assert hr.HUDRecorder().record("n.wav", 5.0, lambda: None) is None  # never crashes
  ```
- [ ] Run → FAIL
- [ ] Implement `HUDRecorder.record()`: generate at `CONFIG["growth"]["hud_viewport"]`, fire `trigger_task` once the page/event-feed is ready, capture for `duration_s`, mux narration + burn captions via ffmpeg. Guarded Playwright import → returns `None` (loguru warning) if unavailable.
- [ ] Run → PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): hud_recorder (Playwright 9:16 HUD capture, live-task-gated)"`

### Task 3: `content_arm.py` — ARM A pipeline
- [ ] Write failing test `tests/test_growth_content_arm.py`
  ```python
  async def test_arm_a_chains_and_gates(monkeypatch):
      from districts.growth.content_arm import ContentArm
      arm = ContentArm()
      monkeypatch.setattr(arm, "_script", lambda well: ("hi", well))
      monkeypatch.setattr(arm, "_narrate", lambda txt: ("/n.wav", 10.0))
      monkeypatch.setattr(arm, "_record", lambda wav, dur: "/reel.mp4")
      gate = {}; monkeypatch.setattr(arm, "_gated_publish", lambda *a, **k: gate.setdefault("called", True))
      r = await arm.run_once()
      assert r["reel"] == "/reel.mp4" and gate["called"] is True
  async def test_arm_a_falls_back_to_showcase_when_no_work(monkeypatch):
      from districts.growth.content_arm import ContentArm
      arm = ContentArm(); monkeypatch.setattr(arm, "_has_reelworthy_work", lambda: False)
      assert (await arm._pick_well()) == "capability_showcase"
  def test_arm_a_instagram_default_is_manual(monkeypatch):
      from districts.growth.content_arm import ContentArm
      # default instagram_mode="manual" → notify owner, never call instagrapi
      assert ContentArm()._instagram_publisher().__name__ == "_notify_owner_to_post"
  ```
- [ ] Run → FAIL
- [ ] Implement: two wells (`work_done` from action log, `capability_showcase` fallback), Kokoro narration, `HUDRecorder`, ffmpeg assemble, `_gated_publish` → `permission_gateway` (YELLOW). YouTube = `uploader.upload_to_youtube`; IG = `_notify_owner_to_post` (manual) or Graph API (`instagram_mode=="graph_api"`); **never instagrapi**.
- [ ] Run → PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): ARM A content pipeline (2 wells, gated, IG human-in-loop)"`

### Task 4: `software_arm.py` — ARM B + reviewer↔fix loop
- [ ] Write failing test `tests/test_growth_software_arm.py`
  ```python
  async def test_review_loop_exits_only_on_approve(monkeypatch):
      from districts.growth.software_arm import SoftwareArm
      arm = SoftwareArm(); seq = iter([False, False, True])  # approve on 3rd
      monkeypatch.setattr(arm, "_review", lambda code: next(seq))
      monkeypatch.setattr(arm, "_fix", lambda code, review: code)
      res = await arm._review_fix_loop(code="x")
      assert res["approved"] is True and res["iterations"] == 3
  async def test_review_loop_caps_and_escalates(monkeypatch):
      from districts.growth.software_arm import SoftwareArm
      arm = SoftwareArm(); monkeypatch.setattr(arm, "_review", lambda code: False)
      res = await arm._review_fix_loop(code="x")  # never approves
      assert res["approved"] is False and res["escalated"] is True
      assert res["iterations"] == arm.max_iterations
  ```
- [ ] Run → FAIL
- [ ] Implement: trigger (market_scanner+idea_validator), build (architect/prototyper), `_review_fix_loop` (code_reviewer+bug_hunter ↔ fix, cap = `CONFIG["growth"]["review_loop_max_iterations"]`, escalate on cap), security audit (security_reviewer), output tagged `beta_candidate` (never "secure product").
- [ ] Run → PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): ARM B software factory + review loop (cap+escalate)"`

### Task 5: `beta_signup.py` — gated PII capture
- [ ] Write failing test `tests/test_growth_beta_signup.py`
  ```python
  def test_signup_blocked_until_release_approved():
      from districts.growth.beta_signup import BetaSignup
      bs = BetaSignup(); bs.deactivate()
      r = bs.register(email="a@b.com", consent=True)
      assert r["ok"] is False and r["reason"] == "signup_not_active"
  def test_signup_requires_consent_and_stores_encrypted(monkeypatch):
      from districts.growth.beta_signup import BetaSignup
      bs = BetaSignup(); bs.activate(owner_approved=True)
      assert bs.register("a@b.com", consent=False)["ok"] is False         # consent required
      stored = {}; monkeypatch.setattr(bs, "_store_encrypted", lambda rec: stored.update(rec) or "id1")
      monkeypatch.setattr(bs, "_privacy_check", lambda rec: True)
      r = bs.register("a@b.com", consent=True)
      assert r["ok"] is True and stored["email"] == "a@b.com"
  def test_activation_requires_owner_approval():
      from districts.growth.beta_signup import BetaSignup
      bs = BetaSignup()
      import pytest
      with pytest.raises(PermissionError): bs.activate(owner_approved=False)
  ```
- [ ] Run → FAIL
- [ ] Implement: `activate(owner_approved)` (raises without approval — same gate as release), `register()` (consent-required, `privacy_enforcer` check, SQLCipher store via `core/collections`), `deactivate()`, 1-month-free flag.
- [ ] Run → PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): beta_signup (consent+privacy+encrypted, activation gated to release)"`

### Task 6: `core/api/routers/growth.py` — consent form + POST
- [ ] Write failing test `tests/test_growth_router.py` (FastAPI TestClient)
  ```python
  def test_form_served_and_post_gated():
      from fastapi.testclient import TestClient
      from core.api.app import create_app  # or existing app factory
      c = TestClient(create_app())
      assert "consent" in c.get("/growth/signup").text.lower()
      # signup inactive by default → POST rejected
      assert c.post("/growth/signup", json={"email":"a@b.com","consent":True}).status_code in (403, 409)
  ```
- [ ] Run → FAIL
- [ ] Implement router: `GET /growth/signup` (consent form HTML from `CONFIG["growth"]["consent_text"]`), `POST /growth/signup` → `BetaSignup.register`; register router in `core/api/app.py`.
- [ ] Run → PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): public consent form + gated signup route"`

### Task 7: `growth_orchestrator.py` — two never-die coroutines + wiring
- [ ] Write failing test `tests/test_growth_orchestrator.py`
  ```python
  async def test_orchestrator_starts_both_arms_and_survives_errors(monkeypatch):
      from districts.growth.growth_orchestrator import GrowthOrchestrator
      o = GrowthOrchestrator(); ran = {"a":0,"b":0}
      async def a(): ran["a"]+=1; raise RuntimeError("boom")   # must not kill loop
      async def b(): ran["b"]+=1
      monkeypatch.setattr(o, "_content_tick", a); monkeypatch.setattr(o, "_software_tick", b)
      monkeypatch.setattr(o, "_backoff_s", 0)
      await o.run_for(ticks=2)   # bounded test runner
      assert ran["a"] >= 2 and ran["b"] >= 2   # both kept ticking despite ARM A errors
  ```
- [ ] Run → FAIL
- [ ] Implement: `GrowthOrchestrator` with `_content_tick` (daily cadence) + `_software_tick` (per-issue trigger), each wrapped in try/except + backoff (never propagate). Gated by `CONFIG["growth"]["enabled"]`. Register district in the agent registry/governor so it's discoverable.
- [ ] Run → PASS
- [ ] Commit: `git commit --no-verify -m "feat(growth): orchestrator (2 never-die arms) + district registration"`

### Task 8: Verification + status doc
- [ ] Run: `pytest tests/test_growth_*.py -v` → expect ALL PASS
- [ ] Run: `python scripts/smoke_test.py` → expect 38/38 (no regression)
- [ ] Write `plans/GROWTH_ENGINE_STATUS.md` (final EXISTS/BUILT/owner-action per design)
- [ ] Verify no publish/signup path is reachable without the permission gate + `enabled`/`auto_publish` off
- [ ] Commit: `git commit --no-verify -m "test(growth): full suite green + GROWTH_ENGINE_STATUS"`
