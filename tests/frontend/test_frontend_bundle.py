from __future__ import annotations

from pathlib import Path

from core.frontend_bundle import extract_local_scripts, validate_frontend_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_extract_local_scripts_ignores_remote_cdn_sources() -> None:
    html = """
    <script src="https://cdn.example/three.js"></script>
    <script src="//cdn.example/leaflet.js"></script>
    <script src="js/vector-core.js"></script>
    <script src="js/demo.js"></script>
    """

    assert extract_local_scripts(html) == ["js/vector-core.js", "js/demo.js"]


def test_production_bundle_rejects_demo_script(tmp_path: Path) -> None:
    html = tmp_path / "VECTOR.html"
    html.write_text(
        '<script src="js/vector-core.js"></script><script src="js/demo.js"></script>',
        encoding="utf-8",
    )

    check = validate_frontend_bundle(html, production=True)

    assert check.status == "fail"
    assert check.dev_only_scripts == ["js/demo.js"]
    assert "development-only" in check.message


def test_development_bundle_allows_demo_script(tmp_path: Path) -> None:
    html = tmp_path / "VECTOR.html"
    html.write_text('<script src="js/demo.js"></script>', encoding="utf-8")

    check = validate_frontend_bundle(html, production=False)

    assert check.ok is True
    assert check.dev_only_scripts == ["js/demo.js"]


def test_current_vector_html_is_not_a_production_bundle() -> None:
    check = validate_frontend_bundle(ROOT / "frontend" / "VECTOR.html", production=True)

    assert check.status == "fail"
    assert "js/demo.js" in check.dev_only_scripts


def test_current_vector_prod_html_is_a_production_bundle() -> None:
    """VECTOR.prod.html loads the built dist/ bundle (tools/build_frontend.py)
    instead of individual js/*.js script tags — see tests/test_frontend_bundle.py
    for staleness coverage of the bundle itself. This test only needs to
    confirm the prod HTML's script boundary is still demo-free."""
    prod_html = ROOT / "frontend" / "VECTOR.prod.html"
    check = validate_frontend_bundle(prod_html, production=True)

    assert check.ok is True
    assert "dist/vector-hud.prod.js" in check.local_scripts
    assert "js/demo.js" not in check.local_scripts
    assert check.dev_only_scripts == []


def test_vector_prod_html_excludes_demo_mounts_but_keeps_runtime_mode() -> None:
    html = (ROOT / "frontend" / "VECTOR.prod.html").read_text(encoding="utf-8")

    assert '<script src="js/demo.js"></script>' not in html
    assert '<script src="dist/vector-hud.prod.js"></script>' in html
    assert 'id="director"' not in html
    assert "V.setRuntimeMode = V.setRuntimeMode || function" in html
