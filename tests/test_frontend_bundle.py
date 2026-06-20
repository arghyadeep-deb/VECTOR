"""Guards against the frontend production bundle going stale again.

This caught a real bug once already: dist/vector-hud.prod.js existed and
VECTOR.prod.html referenced it, but the bundle itself was generated from a
stale script list (missing js/provider-keys.js) — nothing failed loudly, the
HUD just silently shipped old code. This test fails CI the moment
tools/build_frontend.py's output stops matching frontend/VECTOR.prod.html's
actual script order, instead of relying on someone remembering to rebuild.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_frontend  # noqa: E402


def test_prod_html_references_the_bundle():
    html = build_frontend.PROD_HTML.read_text(encoding="utf-8")
    assert "dist/vector-hud.prod.js" in html


def test_bundle_matches_current_source_files():
    expected = build_frontend.build_bundle(write=False)
    current_bundle = (
        build_frontend.BUNDLE.read_text(encoding="utf-8") if build_frontend.BUNDLE.exists() else ""
    )
    assert current_bundle, "dist/vector-hud.prod.js is missing — run: python tools/build_frontend.py"
    import hashlib
    current_hash = hashlib.sha256(current_bundle.encode("utf-8")).hexdigest()
    assert current_hash == expected["sha256"], (
        "frontend bundle is stale (a js/*.js file changed without rebuilding) — "
        "run: python tools/build_frontend.py"
    )


def test_manifest_script_list_matches_current_build():
    import json
    expected = build_frontend.build_bundle(write=False)
    manifest = json.loads(build_frontend.MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("bundled_scripts") == expected["bundled_scripts"], (
        "dist/manifest.json script order is stale — run: python tools/build_frontend.py"
    )


def test_every_bundled_script_file_actually_exists():
    expected = build_frontend.build_bundle(write=False)
    for src in expected["bundled_scripts"]:
        assert (build_frontend.FRONTEND / src).is_file(), f"missing bundled script: {src}"


if __name__ == "__main__":
    print("✅ test_frontend_bundle.py module loads")
