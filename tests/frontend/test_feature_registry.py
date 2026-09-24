import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIDGETS_JS = ROOT / "frontend" / "js" / "widgets.js"
TERMINAL_JS = ROOT / "frontend" / "js" / "terminal.js"
DEMO_JS = ROOT / "frontend" / "js" / "demo.js"
CONFIG_JS = ROOT / "frontend" / "js" / "config.js"
HUD_CONTROLS_JS = ROOT / "frontend" / "js" / "hud-controls.js"


def _feature_ids() -> list[str]:
    text = WIDGETS_JS.read_text(encoding="utf-8")
    registry = re.search(
        r"const FEATURE_REGISTRY = \[(?P<body>.*?)\];",
        text,
        flags=re.S,
    )
    assert registry, "FEATURE_REGISTRY not found"
    ids = re.findall(r"\{\s*id:'([^']+)'", registry.group("body"))
    assert ids and ids[0] == "features"
    return ids


def _quoted_values(path: Path) -> set[str]:
    return set(re.findall(r"'([^']+)'", path.read_text(encoding="utf-8")))


def _director_widget_ids() -> set[str]:
    text = DEMO_JS.read_text(encoding="utf-8")
    block = re.search(
        r"\[\s*'chat'.*?\]\s*\.forEach\(id=>mk\('g-wid'",
        text,
        flags=re.S,
    )
    assert block, "Director widget list not found"
    return set(re.findall(r"'([a-z0-9]+)'", block.group(0)))


def test_feature_panels_are_openable_from_terminal_and_director() -> None:
    feature_ids = set(_feature_ids())

    terminal_values = _quoted_values(TERMINAL_JS)
    director_values = _director_widget_ids()

    assert feature_ids <= terminal_values
    assert feature_ids <= director_values


def test_feature_registry_endpoints_are_main_api_or_labeled_side_systems() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")
    endpoints = re.findall(r"endpoints:\[(.*?)\]", text, flags=re.S)
    assert endpoints

    all_paths: list[str] = []
    for block in endpoints:
        all_paths.extend(re.findall(r"'([^']+)'", block))

    assert all_paths
    for path in all_paths:
        assert path.startswith(
            ("/", "studio:", "sidecar:", "comfyui:")
        ), f"unlabeled feature endpoint: {path}"

    assert "/world/snapshot" in all_paths
    assert "/missions" in all_paths
    assert "/health/hardened-readiness" in all_paths


def test_every_backend_feature_has_bespoke_blueprint() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")
    blueprints = re.search(
        r"const FEATURE_BLUEPRINTS = \{(?P<body>.*?)\n  \};",
        text,
        flags=re.S,
    )
    assert blueprints, "FEATURE_BLUEPRINTS not found"
    blueprint_ids = set(re.findall(r"^\s+([a-z0-9]+): \{", blueprints.group("body"), flags=re.M))

    feature_ids = set(_feature_ids()) - {"features"}

    assert feature_ids <= blueprint_ids


def test_feature_action_rail_uses_executor_plan_contract() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")

    assert "function actionTypeFromEndpoint" in text
    assert "apiPost('/execute/plan'" in text
    assert "proposed_by: 'hud.'+cfg.id" in text


def test_platform_panel_surfaces_mission_endpoints() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")

    assert "F.missioncontrol = function" in text
    assert "'/missions'" in text
    assert "'/missions/decompose'" in text
    assert "'/missions/jobs'" in text
    assert "'/missions/{id}/timeline'" in text
    assert "'/missions/{id}/artifacts'" in text
    assert "'/missions/{id}/retry'" in text
    assert "'/missions/{id}/rollback'" in text
    assert "'/missions/plan'" in text
    assert "'/missions/advise'" in text
    assert "'/missions/run'" in text
    assert "'/missions/run-async'" in text


def test_mission_control_has_review_workflow_controls() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")
    demo = DEMO_JS.read_text(encoding="utf-8")
    terminal = TERMINAL_JS.read_text(encoding="utf-8")

    assert "data-act=\"decompose\"" in text
    assert "data-act=\"advise\"" in text
    assert "data-act=\"plan\"" in text
    assert "data-act=\"dry\"" in text
    assert "data-act=\"run\"" in text
    assert "data-act=\"retry\"" in text
    assert "data-act=\"rollback\"" in text
    assert "recoverMission" in text
    assert "runAsync" in text
    assert "/missions/run-async" in text
    assert "/missions/jobs/" in text
    assert "renderMissionEvents" in text
    assert "renderMissionArtifacts" in text
    assert "hud.missioncontrol" in text
    assert "'missioncontrol'" in demo
    assert "'missioncontrol'" in terminal


def test_demo_panel_exposes_honest_runtime_modes() -> None:
    text = DEMO_JS.read_text(encoding="utf-8")

    assert "V.setRuntimeMode" in text
    assert "V.getRuntimeMode" in text
    assert "DEMO MODE · seed data only" in text
    assert "waiting for backend health check" in text
    assert "dataset.runtimeMode" in text
    assert "connect failed · using demo data" not in text


def test_frontend_config_uses_same_origin_only_when_api_served() -> None:
    text = CONFIG_JS.read_text(encoding="utf-8")

    assert "location.pathname.startsWith('/hud')" in text
    assert "base: VECTOR_SERVED_BY_API ? location.origin : ''" in text
    assert "autoConnect: VECTOR_SERVED_BY_API" in text
    assert "base: 'http://127.0.0.1:8000'" not in text


def test_production_hud_controls_expose_dock_without_dev_director() -> None:
    # 2026-07-14 LEAN DOCK: features/missioncontrol moved off the dock into the
    # Ctrl+Shift+H terminal (covered by the terminal registry test above); the
    # dock now carries only the always-working production controls.
    text = HUD_CONTROLS_JS.read_text(encoding="utf-8")

    assert "VectorHudControls" in text
    assert "buildDock" in text
    assert "V.openWidget('chat')" in text
    assert "V.openWidget('goals')" in text
    assert "V.openWidget('approvals')" in text
    assert "Director" not in text
    assert "autoDemo" not in text
    assert "d-base" not in text


def test_backend_polling_surfaces_degraded_state() -> None:
    text = (ROOT / "frontend" / "js" / "backend.js").read_text(encoding="utf-8")

    assert "markRuntime('live'" in text
    assert "markRuntime('degraded'" in text
    assert "Falls back silently" not in text
    assert "seed data from data.js remains visible as explicit demo/degraded state" in text


def test_command_fallbacks_are_labeled_as_local_demo() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")

    assert "LOCAL DEMO FALLBACK · " in text
    assert "localFallbackReply" in text
    assert "sayLocalFallback" in text
    assert "V.setRuntimeMode('degraded'" in text
    assert ".catch(()=>{ setTimeout(()=>V.say(localReply(text)), 500); })" not in text
    assert "}catch(e){ V.say(localReply(text)); }" not in text


def test_terminal_connect_disconnect_updates_runtime_mode() -> None:
    text = TERMINAL_JS.read_text(encoding="utf-8")

    assert "V.setRuntimeMode('connecting'" in text
    assert "V.setRuntimeMode('demo'" in text
    assert "waiting for backend health" in text
    assert "disconnected · demo data" not in text


def test_telemetry_widget_labels_simulated_data() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "styles" / "widgets.css").read_text(encoding="utf-8")

    assert "SIMULATED · waiting for backend metrics" in text
    assert "LIVE · backend metrics" in text
    assert "SIMULATED · backend metrics unavailable" in text
    assert "telemetry backend unavailable" in text
    assert "demo animation keeps running" not in text
    assert ".ve-source" in css


def test_camera_widget_labels_simulated_detector_overlay() -> None:
    text = WIDGETS_JS.read_text(encoding="utf-8")

    assert "CAMERA · LOCAL PREVIEW STANDBY" in text
    assert "SIMULATED · detector overlay only" in text
    assert "SIMULATED DETECTION · person" in text
    assert "CAMERA UNAVAILABLE · no local preview" in text
    assert "camera preview unavailable" in text
    assert "mock YOLO" not in text
    assert "person · 0.97" not in text
