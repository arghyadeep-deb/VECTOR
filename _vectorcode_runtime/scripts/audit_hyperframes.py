"""Audit script for hyperframes absorption into core/video/"""
import sys, os, ast, asyncio, tempfile
sys.stdout.reconfigure(encoding="utf-8")

results = []

def ok(msg):
    results.append(("PASS", msg))
    print(f"  PASS  {msg}")

def fail(msg):
    results.append(("FAIL", msg))
    print(f"  FAIL  {msg}")

# ── GROUP 1: Syntax ───────────────────────────────────────────────────────────
print("GROUP 1 -- Syntax check")
new_files = [
    "core/video/__init__.py",
    "core/video/composition_types.py",
    "core/video/html_renderer.py",
    "core/video/video_encoder.py",
    "core/video/audio_mixer.py",
    "core/video/background_remover.py",
    "core/video/vector_composer.py",
    "core/video/website_to_video.py",
    "districts/content/website_to_video.py",
]
for f in new_files:
    try:
        with open(f, encoding="utf-8") as fh:
            ast.parse(fh.read())
        ok(f"syntax: {f}")
    except Exception as e:
        fail(f"syntax: {f}: {e}")
print()

# ── GROUP 2: Imports ──────────────────────────────────────────────────────────
print("GROUP 2 -- Import check")
import_tests = [
    ("core.video.composition_types", ["Fps","canvas_size","CANVAS_DIMENSIONS","RenderJob","QUALITY_CRF"]),
    ("core.video.html_renderer",     ["HTMLFrameRenderer","RendererConfig","capture_screenshot"]),
    ("core.video.video_encoder",     ["VideoEncoder","EncodeOptions","find_ffmpeg"]),
    ("core.video.audio_mixer",       ["AudioMixer","AudioTrack","NarrationPipeline"]),
    ("core.video.background_remover",["BackgroundRemover","BGSession","remove_background"]),
    ("core.video.vector_composer",["VectorComposer","ComposerJob","CompositionTemplate"]),
    ("core.video.website_to_video",  ["WebsiteToVideo","WebContentExtractor","CaptureOptions"]),
]
for mod, symbols in import_tests:
    try:
        m = __import__(mod, fromlist=symbols)
        for s in symbols:
            assert hasattr(m, s), f"missing {s}"
        ok(f"import: {mod}")
    except Exception as e:
        fail(f"import: {mod}: {e}")
print()

# ── GROUP 3: Functional ───────────────────────────────────────────────────────
print("GROUP 3 -- Functional tests")

from core.video.composition_types import (
    Fps, canvas_size, normalize_resolution, QUALITY_CRF, BG_REMOVAL_CRF, RenderJob
)

# FPS rational math
fps = Fps(30000, 1001)
assert fps.to_ffmpeg_arg() == "30000/1001"
assert abs(fps.to_float() - 29.97) < 0.01
fps30 = Fps.from_value(30)
assert fps30.to_ffmpeg_arg() == "30"
fps_str = Fps.from_value("24000/1001")
assert fps_str.to_ffmpeg_arg() == "24000/1001"
ok("Fps rational math (NTSC 30000/1001, int 30, string 24000/1001)")

# Canvas sizes
w, h = canvas_size("4k")
assert (w, h) == (3840, 2160)
w2, h2 = canvas_size("1080p")
assert (w2, h2) == (1920, 1080)
assert normalize_resolution("uhd") == "landscape-4k"
assert normalize_resolution("portrait") == "portrait"
ok("canvas_size + resolution aliases (4k=3840x2160, 1080p=1920x1080, uhd=landscape-4k)")

# Quality CRF
assert QUALITY_CRF["draft"] == 35
assert QUALITY_CRF["standard"] == 23
assert QUALITY_CRF["high"] == 18
assert BG_REMOVAL_CRF["balanced"] == 18
assert BG_REMOVAL_CRF["best"] == 12
ok("QUALITY_CRF + BG_REMOVAL_CRF values")

# RenderJob
job = RenderJob(composition_path="test.html", output_path="out.mp4", fps=Fps(60, 1))
assert job.fps.to_ffmpeg_arg() == "60"
assert job.quality == "standard"
ok("RenderJob dataclass defaults")

# HTMLFrameRenderer
from core.video.html_renderer import HTMLFrameRenderer, RendererConfig
cfg = RendererConfig(quality="high", use_gpu=False)
r = HTMLFrameRenderer(cfg)
args = r._browser_args()
assert "--no-sandbox" in args
assert "--disable-gpu" in args
ok("HTMLFrameRenderer._browser_args() software mode (no-sandbox, disable-gpu)")

cfg_gpu = RendererConfig(quality="high", use_gpu=True)
r_gpu = HTMLFrameRenderer(cfg_gpu)
args_gpu = r_gpu._browser_args()
assert "--no-sandbox" in args_gpu
assert "--disable-gpu" not in args_gpu
ok("HTMLFrameRenderer._browser_args() GPU mode (no disable-gpu)")

# VideoEncoder codec selection
from core.video.video_encoder import VideoEncoder, EncodeOptions
enc = VideoEncoder()
opts_cpu  = EncodeOptions(fps=Fps(30,1), format="mp4",  use_gpu=False)
opts_gpu  = EncodeOptions(fps=Fps(60,1), format="mp4",  use_gpu=True)
opts_webm = EncodeOptions(fps=Fps(30,1), format="webm")
opts_mov  = EncodeOptions(fps=Fps(30,1), format="mov")
opts_seq  = EncodeOptions(fps=Fps(30,1), format="png-sequence")
assert enc._codec_name(opts_cpu)  == "libx264"
assert enc._codec_name(opts_gpu)  == "h264_nvenc"
assert enc._codec_name(opts_webm) == "libvpx-vp9"
assert enc._codec_name(opts_mov)  == "prores_ks"
assert enc._codec_name(opts_seq)  == "png"
ok("VideoEncoder codec (libx264/h264_nvenc/libvpx-vp9/prores_ks/png)")

gpu_args = enc._h264_args(opts_gpu, 18)
assert "h264_nvenc" in gpu_args
assert "vbr" in gpu_args
cpu_args = enc._h264_args(opts_cpu, 23)
assert "libx264" in cpu_args
assert "faster" in cpu_args
ok("VideoEncoder GPU (h264_nvenc+vbr) vs CPU (libx264+faster) args")

vp9_args = enc._vp9_args(opts_webm, 18)
assert "yuva420p" in vp9_args
assert "alpha_mode=1" in " ".join(vp9_args)
ok("VP9 alpha channel (yuva420p + alpha_mode=1 metadata)")

prores_args = enc._prores_args(opts_mov)
assert "prores_ks" in prores_args
assert "yuva444p10le" in prores_args
ok("ProRes 4444 args (prores_ks + yuva444p10le)")

# Audio
from core.video.audio_mixer import AudioMixer, AudioTrack, NarrationPipeline
mixer = AudioMixer()
track = AudioTrack(path="test.wav", volume=0.8, start_time=2.0, fade_in=0.5)
assert track.volume == 0.8
assert track.start_time == 2.0
assert track.fade_in == 0.5
ok("AudioTrack dataclass (volume, start_time, fade_in)")

np_obj = NarrationPipeline()
assert hasattr(np_obj, "_mixer")
ok("NarrationPipeline init")

# BackgroundRemover
from core.video.background_remover import BackgroundRemover, BGSession, DEFAULT_MODEL
rem = BackgroundRemover(model_id="u2net_human", quality="balanced")
assert rem._model_id == "u2net_human"
assert rem._quality == "balanced"
session = BGSession(model_id="isnet-dis")
assert session._input_size == 1024
session2 = BGSession(model_id="u2net")
assert session2._input_size == 320
ok("BackgroundRemover + BGSession input sizes (isnet-dis=1024, u2net=320)")

# CompositionTemplate HTML
from core.video.vector_composer import CompositionTemplate, VectorComposer, ComposerJob
with tempfile.TemporaryDirectory() as tmp:
    tc = os.path.join(tmp, "title.html")
    CompositionTemplate.title_card("VECTOR AI", "Intelligence", output_path=tc)
    html = open(tc, encoding="utf-8").read()
    assert "VECTOR AI" in html
    assert "window.__vector" in html
    assert "enableRenderMode" in html
    assert "renderSeek" in html
    assert "setVariables" in html
    ok("CompositionTemplate.title_card has __vector runtime + all 3 methods")

    dv = os.path.join(tmp, "viz.html")
    CompositionTemplate.data_viz("Metrics", {"Research": 90, "Security": 95}, output_path=dv)
    dvhtml = open(dv, encoding="utf-8").read()
    assert "Metrics" in dvhtml
    assert "Research" in dvhtml
    assert "bar-fill" in dvhtml
    ok("CompositionTemplate.data_viz has title, data, bar chart CSS")

# ComposerJob
composer = VectorComposer()
job = ComposerJob(composition_path="test.html", output_path="out.mp4", duration_seconds=5.0)
assert job.fps.to_ffmpeg_arg() == "30"
assert job.resolution == "landscape"
assert job.quality == "standard"
assert job.format == "mp4"
assert job.use_gpu is False
ok("ComposerJob defaults (30fps landscape standard mp4 cpu)")

# Website extractor
from core.video.website_to_video import (
    WebContentExtractor, build_composition_from_content, ExtractedContent
)

async def _test_extract():
    ex = WebContentExtractor()
    html = """
    <html><head>
    <title>VECTOR Intelligence</title>
    <meta property="og:description" content="Multi-agent autonomous AI">
    <meta property="og:image" content="https://example.com/og.png">
    </head><body><h1>VECTOR AI Platform</h1></body></html>
    """
    c = await ex.extract("https://vector.ai", html=html)
    return c

content = asyncio.run(_test_extract())
assert content.title == "VECTOR Intelligence"
assert "Multi-agent" in content.description
assert content.og_image == "https://example.com/og.png"
assert content.headline == "VECTOR AI Platform"
ok("WebContentExtractor (title, og:description, og:image, h1 headline)")

with tempfile.TemporaryDirectory() as tmp:
    comp = os.path.join(tmp, "comp.html")
    build_composition_from_content(content, None, comp)
    comp_html = open(comp, encoding="utf-8").read()
    # headline = h1 text "VECTOR AI Platform", title is fallback only
    assert "VECTOR AI Platform" in comp_html
    assert "Multi-agent" in comp_html
    assert "window.__vector" in comp_html
    assert "enableRenderMode" in comp_html
    assert "vector.ai" in comp_html.lower()
    ok("build_composition_from_content with __vector runtime + domain in url bar")

print()

# ── GROUP 4: Governor routing ─────────────────────────────────────────────────
print("GROUP 4 -- Governor routing")
from core.city.governor import DISTRICT_TASK_MAP

new_routes = {
    "website_to_video": "content",
    "url_capture":      "content",
    "title_card":       "content",
    "data_viz":         "content",
    "render_html":      "content",
    "remove_bg":        "content",
    "background_remove":"content",
}
for key, expected in new_routes.items():
    actual = DISTRICT_TASK_MAP.get(key)
    if actual == expected:
        ok(f"governor routes {key!r} -> {expected}")
    else:
        fail(f"governor routes {key!r}: expected {expected}, got {actual}")

print()

# ── GROUP 5: District agent ───────────────────────────────────────────────────
print("GROUP 5 -- District agent")
try:
    from districts.content.website_to_video import WebsiteToVideoAgent
    agent = WebsiteToVideoAgent()
    assert agent.health_points == 500
    assert agent.name == "WebsiteToVideoAgent"
    assert agent.district == "content"
    ok("WebsiteToVideoAgent init (HP=500, district=content)")
except Exception as e:
    fail(f"WebsiteToVideoAgent init: {e}")

# ── GROUP 6: No hyperframes refs ─────────────────────────────────────────────
print()
print("GROUP 6 -- Zero external repo references")
import re
check_dirs = ["core/video", "districts/content/website_to_video.py"]
banned = ["hyperframes", "heygen-com", "npx hyperframes"]
all_clean = True
for check in check_dirs:
    if os.path.isdir(check):
        for root, dirs, files in os.walk(check):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, encoding="utf-8") as fh:
                    src = fh.read()
                for b in banned:
                    if b in src:
                        fail(f"found {b!r} in {fpath}")
                        all_clean = False
    else:
        with open(check, encoding="utf-8") as fh:
            src = fh.read()
        for b in banned:
            if b in src:
                fail(f"found {b!r} in {check}")
                all_clean = False
if all_clean:
    ok("zero hyperframes/heygen-com/npx references in core/video/")

print()
# Summary
passed = sum(1 for r, _ in results if r == "PASS")
failed = sum(1 for r, _ in results if r == "FAIL")
print(f"RESULT: PASS={passed} FAIL={failed}")
if failed:
    print("FAILURES:")
    for r, m in results:
        if r == "FAIL":
            print(f"  - {m}")

sys.exit(1 if failed else 0)
