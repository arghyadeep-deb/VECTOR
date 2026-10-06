"""Final audit: composition_linter + studio_server + VectorPlayer + studio UI"""
import sys, os, ast, re, asyncio, tempfile
sys.stdout.reconfigure(encoding="utf-8")

results = []
def ok(m): results.append(("PASS", m)); print(f"  PASS  {m}")
def fail(m): results.append(("FAIL", m)); print(f"  FAIL  {m}")

# GROUP 1: Syntax
print("GROUP 1 -- New files syntax")
for f in ["core/video/composition_linter.py", "core/video/studio_server.py", "core/video/__init__.py"]:
    try:
        with open(f, encoding="utf-8") as fh: ast.parse(fh.read())
        ok(f"syntax: {f}")
    except Exception as e:
        fail(f"syntax: {f}: {e}")
print()

# GROUP 2: Imports
print("GROUP 2 -- Imports")
for mod, syms in [
    ("core.video.composition_linter", ["lint_composition","lint_file","lint_project","LintResult","LintFinding"]),
    ("core.video", ["lint_composition","LintResult","VectorComposer","BackgroundRemover"]),
]:
    try:
        m = __import__(mod, fromlist=syms)
        for s in syms: assert hasattr(m, s), f"missing {s}"
        ok(f"import: {mod}")
    except Exception as e:
        fail(f"import: {mod}: {e}")
print()

# GROUP 3: Linter functional
print("GROUP 3 -- Composition Linter rules")
from core.video.composition_linter import lint_composition

GOOD = """<!DOCTYPE html>
<html data-composition-variables="[]">
<body>
  <div data-composition-id="intro-001" data-width="1920" data-height="1080">
    <div id="title" data-start="0" data-track-index="0">VECTOR</div>
  </div>
</body></html>"""

BAD = """<!DOCTYPE html>
<html><body>
  <div data-width="1920">
    <div id="dup">A</div><div id="dup">B</div>
    <video autoplay></video>
  </div>
</body></html>"""

good = lint_composition(GOOD, file_path="intro.html")
assert good.error_count == 0, [(f.code, f.message) for f in good.errors]
ok(f"GOOD composition: 0 errors, {good.warning_count} warnings")

bad = lint_composition(BAD, file_path="bad.html")
assert bad.error_count >= 2, bad.error_count
codes = {f.code for f in bad.findings}
assert "root_missing_composition_id" in codes
assert "duplicate_element_id" in codes
assert "autoplay_without_muted" in codes
ok(f"BAD: detects root_missing_id + duplicate_id + autoplay_no_muted ({bad.error_count}E {bad.warning_count}W)")

big_lines = "\n".join(f"<div id='el{i}'>Line {i}</div>" for i in range(310))
big_html = f"<html><body><div data-composition-id='x' data-width='1920' data-height='1080'>{big_lines}</div></body></html>"
big = lint_composition(big_html)
assert any(f.code == "composition_file_too_large" for f in big.findings)
ok("composition_file_too_large triggers at >300 lines")

track_divs = "".join(f"<div id='e{i}' data-start='{i}' data-track-index='0'>E{i}</div>" for i in range(5))
track_html = f"<html><body><div data-composition-id='t' data-width='1920' data-height='1080'>{track_divs}</div></body></html>"
track = lint_composition(track_html)
assert any(f.code == "track_density_high" for f in track.findings)
ok("track_density_high triggers at >3 elements per track")

gsap_html = """<html><body><div data-composition-id="g" data-width="1920" data-height="1080">
<script>
window.__timelines["intro"] = gsap.timeline();
gsap.to(".el", {x: 100});
</script>
</div></body></html>"""
gsap = lint_composition(gsap_html)
assert any(f.code == "timeline_registry_missing_init" for f in gsap.findings)
ok("timeline_registry_missing_init catches missing window.__timelines init")

# Variable type validation
vars_html = """<html data-composition-variables='[{"id":"x","type":"invalid_type","label":"X","default":"v"}]'>
<body><div data-composition-id="v" data-width="1920" data-height="1080"></div></body></html>"""
vars_result = lint_composition(vars_html)
assert any(f.code == "invalid_variable_type" for f in vars_result.findings)
ok("invalid_variable_type catches unknown variable types in data-composition-variables")
print()

# GROUP 4: Studio server REST API
print("GROUP 4 -- Studio server API")
try:
    from core.video.studio_server import app, set_project_dir
    from fastapi.testclient import TestClient
    client = TestClient(app)

    with tempfile.TemporaryDirectory() as tmp:
        set_project_dir(tmp)
        html_good = """<!DOCTYPE html>
<html><body>
  <div data-composition-id="s001" data-width="1920" data-height="1080">
    <div id="t" data-start="0" data-track-index="0">VECTOR Studio</div>
  </div>
</body></html>"""
        open(os.path.join(tmp, "studio.html"), "w", encoding="utf-8").write(html_good)

        r = client.get("/compositions")
        assert r.status_code == 200
        assert len(r.json()["compositions"]) >= 1
        ok("GET /compositions returns file list")

        r2 = client.get("/compositions/studio.html")
        assert r2.status_code == 200
        d = r2.json()
        assert d["lint"]["ok"] is True
        assert "VECTOR Studio" in d["html"]
        ok("GET /compositions/{path} returns html + lint (ok=True for valid composition)")

        r3 = client.get("/lint/studio.html")
        assert r3.status_code == 200
        assert r3.json()["ok"] is True
        ok("GET /lint/{path} returns lint-only result")

        bad_html = "<html><body><div></div></body></html>"
        r4 = client.put("/compositions/new.html", json={"html": bad_html})
        assert r4.status_code == 200
        assert os.path.exists(os.path.join(tmp, "new.html"))
        assert r4.json()["lint"]["ok"] is False
        ok("PUT /compositions saves file + returns lint errors for bad composition")

except Exception as e:
    fail(f"Studio server: {e}")
print()

# GROUP 5: Player rebranding
print("GROUP 5 -- VectorPlayer web component")
player_dir = "dashboard/src/components/VectorPlayer"
if os.path.exists(player_dir):
    files = os.listdir(player_dir)
    assert "vector-player.ts" in files, f"missing vector-player.ts: {files}"
    ok(f"VectorPlayer has {len(files)} files including vector-player.ts")

    remaining = 0
    for f in files:
        with open(os.path.join(player_dir, f), encoding="utf-8") as fh: content = fh.read()
        hits = len(re.findall(r"hyperframes", content, re.IGNORECASE))
        if hits: remaining += hits

    if remaining == 0:
        ok("Zero hyperframes refs in VectorPlayer/ (all rebranded to vector)")
    else:
        fail(f"{remaining} hyperframes refs remain in VectorPlayer/")

    # Check VectorPlayer class name exists in main file
    with open(os.path.join(player_dir, "vector-player.ts"), encoding="utf-8") as f:
        content = f.read()
    assert "VectorPlayer" in content
    ok("VectorPlayer class name present in vector-player.ts")
else:
    fail(f"VectorPlayer dir missing: {player_dir}")
print()

# GROUP 6: Studio UI rebranding
print("GROUP 6 -- Studio UI (167 files)")
studio_dir = "dashboard/src/studio"
if os.path.exists(studio_dir):
    total = sum(1 for _, _, files in os.walk(studio_dir) for _ in files)
    ok(f"Studio directory has {total} files")

    remaining = 0
    for root, _, files in os.walk(studio_dir):
        for fname in files:
            try:
                with open(os.path.join(root, fname), encoding="utf-8") as fh: content = fh.read()
                hits = len(re.findall(r"hyperframes", content, re.IGNORECASE))
                if hits: remaining += hits
            except Exception as e:
                print(f"[audit] read skipped {os.path.join(root, fname)}: {e}")
    if remaining == 0:
        ok("Zero hyperframes refs in dashboard/src/studio/ (all rebranded)")
    else:
        fail(f"{remaining} hyperframes refs remain in studio/")
else:
    fail(f"Studio dir missing: {studio_dir}")
print()

# GROUP 7: Linter wired into VectorComposer
print("GROUP 7 -- Linter integration")
with open("core/video/vector_composer.py", encoding="utf-8") as f: src = f.read()
assert "from core.video.composition_linter import lint_file" in src
assert "Stage 0: Lint" in src
ok("VectorComposer.render() lints before frame capture (Stage 0)")

# Summary
print()
passed = sum(1 for r, _ in results if r == "PASS")
failed = sum(1 for r, _ in results if r == "FAIL")
print(f"RESULT: PASS={passed} FAIL={failed}")
if failed:
    print("FAILURES:")
    for r, m in results:
        if r == "FAIL": print(f"  - {m}")

sys.exit(1 if failed else 0)
