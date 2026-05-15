"""Generate VECTOR desktop app icons.

Produces a bold "V" monogram on a deep navy/cyan gradient background, in all
sizes Tauri needs:
  - 32x32.png, 128x128.png, 128x128@2x.png  (PNG, RGBA)
  - icon.ico                                 (Windows multi-res)
  - icon.icns                                (macOS — generated if `iconutil` present)
  - vector-source.png (1024x1024 master)

Also writes a small Square*Logo.png set for the Microsoft Store bundle.

Run:
    pip install Pillow
    python scripts/generate_vector_icons.py

Outputs to: desktop/src-tauri/icons/
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run:  pip install Pillow")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "desktop" / "src-tauri" / "icons"
ICONS.mkdir(parents=True, exist_ok=True)


# ── Style ────────────────────────────────────────────────────────────────────

# VECTOR brand: deep navy → cyan gradient, bright cyan V monogram with subtle glow
NAVY = (10, 14, 38, 255)
DEEP_CYAN = (16, 78, 130, 255)
BRIGHT_CYAN = (88, 211, 255, 255)
WHITE = (255, 255, 255, 255)


def _radial_gradient(size: int, inner: tuple, outer: tuple) -> Image.Image:
    """Radial gradient from inner color (center) to outer color (edges)."""
    img = Image.new("RGBA", (size, size), outer)
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    max_r = math.hypot(cx, cy)
    # Draw concentric circles from outer edge inward
    steps = 64
    for i in range(steps, -1, -1):
        t = i / steps
        # interpolate
        c = tuple(
            int(outer[k] * t + inner[k] * (1 - t)) for k in range(4)
        )
        r = max_r * t
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    return img


def _draw_vector_v(canvas: Image.Image, size: int) -> None:
    """Draw a stylized V monogram with subtle glow."""
    draw = ImageDraw.Draw(canvas, "RGBA")

    # V geometry — bold strokes
    margin = size * 0.18
    stroke_w = size * 0.16
    top_y = margin
    bot_y = size - margin
    left_x = margin
    right_x = size - margin
    cx = size / 2
    cy_bottom = bot_y - stroke_w * 0.05  # tip of V

    # Two stroke lines forming the V
    # Stroke 1: top-left to bottom-center
    draw.line(
        [(left_x, top_y), (cx, cy_bottom)],
        fill=BRIGHT_CYAN, width=int(stroke_w),
    )
    # Stroke 2: bottom-center to top-right
    draw.line(
        [(cx, cy_bottom), (right_x, top_y)],
        fill=BRIGHT_CYAN, width=int(stroke_w),
    )

    # Round caps via small circles at endpoints
    cap_r = stroke_w / 2
    for (x, y) in [(left_x, top_y), (cx, cy_bottom), (right_x, top_y)]:
        draw.ellipse(
            [x - cap_r, y - cap_r, x + cap_r, y + cap_r],
            fill=BRIGHT_CYAN,
        )

    # Soft glow — render the V on a separate layer, blur, composite under
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.line([(left_x, top_y), (cx, cy_bottom)], fill=(88, 211, 255, 110), width=int(stroke_w * 1.6))
    gd.line([(cx, cy_bottom), (right_x, top_y)], fill=(88, 211, 255, 110), width=int(stroke_w * 1.6))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=size * 0.04))
    canvas.alpha_composite(glow)

    # Re-draw the sharp V on top so it stays crisp
    draw.line([(left_x, top_y), (cx, cy_bottom)], fill=BRIGHT_CYAN, width=int(stroke_w))
    draw.line([(cx, cy_bottom), (right_x, top_y)], fill=BRIGHT_CYAN, width=int(stroke_w))
    for (x, y) in [(left_x, top_y), (cx, cy_bottom), (right_x, top_y)]:
        draw.ellipse(
            [x - cap_r, y - cap_r, x + cap_r, y + cap_r],
            fill=WHITE,  # bright white core
        )


def _make_master(size: int = 1024) -> Image.Image:
    """Render the 1024x1024 master icon."""
    bg = _radial_gradient(size, DEEP_CYAN, NAVY)
    # Optional rounded-square mask for iOS/macOS aesthetic
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.22, fill=255)
    bg.putalpha(mask)
    _draw_vector_v(bg, size)
    return bg


def _make_round_master(size: int = 1024) -> Image.Image:
    """Render a circular variant for tray / Linux."""
    bg = _radial_gradient(size, DEEP_CYAN, NAVY)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, size - 1, size - 1], fill=255)
    bg.putalpha(mask)
    _draw_vector_v(bg, size)
    return bg


# ── Output writers ───────────────────────────────────────────────────────────


def _write_pngs(master: Image.Image) -> None:
    sizes = {
        "32x32.png":      32,
        "128x128.png":    128,
        "128x128@2x.png": 256,
        "icon.png":       512,
    }
    for name, sz in sizes.items():
        master.resize((sz, sz), Image.Resampling.LANCZOS).save(ICONS / name, "PNG")
        print(f"  ✓ {name}  ({sz}x{sz})")


def _write_ico(master: Image.Image) -> None:
    """Windows .ico — multi-resolution."""
    out = ICONS / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [master.resize((s, s), Image.Resampling.LANCZOS) for s in sizes]
    images[-1].save(
        out, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    print(f"  ✓ icon.ico  (multi-res {sizes})")


def _write_icns(master: Image.Image) -> None:
    """macOS .icns. Use iconutil if available; otherwise write a stub PNG."""
    out = ICONS / "icon.icns"
    if sys.platform != "darwin" or not shutil.which("iconutil"):
        # On Windows/Linux, just write the largest PNG renamed — Tauri build only
        # actually consumes .icns when targeting macOS. For cross-bundling, the
        # PNGs above are sufficient.
        master.resize((1024, 1024), Image.Resampling.LANCZOS).save(out.with_suffix(".png"), "PNG")
        print(f"  ⚠ icon.icns skipped (need macOS + iconutil) — stored {out.with_suffix('.png').name} as fallback")
        return

    # macOS path: build .iconset, then iconutil
    iconset_dir = ICONS / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)
    macos_sizes = [
        ("16x16", 16), ("16x16@2x", 32),
        ("32x32", 32), ("32x32@2x", 64),
        ("128x128", 128), ("128x128@2x", 256),
        ("256x256", 256), ("256x256@2x", 512),
        ("512x512", 512), ("512x512@2x", 1024),
    ]
    for label, sz in macos_sizes:
        master.resize((sz, sz), Image.Resampling.LANCZOS).save(
            iconset_dir / f"icon_{label}.png", "PNG",
        )
    subprocess.run(
        ["iconutil", "-c", "icns", "-o", str(out), str(iconset_dir)],
        check=True,
    )
    shutil.rmtree(iconset_dir, ignore_errors=True)
    print("  ✓ icon.icns")


def _write_microsoft_store(master: Image.Image) -> None:
    """Windows Store / MSIX requires a few SquareLogo sizes."""
    sizes = {
        "Square30x30Logo.png":   30,
        "Square44x44Logo.png":   44,
        "Square71x71Logo.png":   71,
        "Square89x89Logo.png":   89,
        "Square107x107Logo.png": 107,
        "Square142x142Logo.png": 142,
        "Square150x150Logo.png": 150,
        "Square284x284Logo.png": 284,
        "Square310x310Logo.png": 310,
        "StoreLogo.png":         50,
    }
    for name, sz in sizes.items():
        master.resize((sz, sz), Image.Resampling.LANCZOS).save(ICONS / name, "PNG")
    print(f"  ✓ {len(sizes)} Microsoft Store SquareLogo sizes")


def _write_master(master: Image.Image) -> None:
    """Save the high-res master next to the script for re-use."""
    out = ROOT / "desktop" / "src-tauri" / "vector-source.png"
    master.save(out, "PNG")
    print(f"  ✓ vector-source.png (1024x1024 master)")


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    print(f"VECTOR icon generator")
    print(f"  Output: {ICONS}")
    print()

    print("Rendering master 1024x1024…")
    master = _make_master(1024)
    _write_master(master)

    print()
    print("Writing PNG set…")
    _write_pngs(master)

    print()
    print("Writing Windows .ico…")
    _write_ico(master)

    print()
    print("Writing macOS .icns (best-effort)…")
    _write_icns(master)

    print()
    print("Writing Microsoft Store square logos…")
    _write_microsoft_store(master)

    print()
    print(f"All icons written to: {ICONS}")
    print(f"Now you can run:  cd desktop/src-tauri && cargo tauri build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
