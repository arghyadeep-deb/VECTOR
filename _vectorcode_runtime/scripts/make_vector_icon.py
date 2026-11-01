"""Generate the VECTOR desktop icon (matches HUD brand: #00CFFF orb on near-black).

Renders a glowing cyan orb with a stylized 'V' at 512px, then writes a
multi-resolution .ico (16/32/48/64/128/256) next to this script.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "vector.ico"
S = 512  # master render size

ACCENT = (0, 207, 255)        # #00CFFF
ACCENT_SOFT = (127, 230, 255)  # #7fe6ff
CORE = (234, 252, 255)        # near-white orb core


def _radial_glow(size: int) -> Image.Image:
    """Dark disc with a soft cyan radial glow."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    max_r = size * 0.46
    # paint concentric rings from outside in: transparent-dark -> glowing cyan
    steps = 120
    for i in range(steps, 0, -1):
        t = i / steps
        r = max_r * t
        # colour blends near-black (outer) -> accent-deep -> accent (inner)
        if t > 0.55:
            k = (t - 0.55) / 0.45
            col = (
                int(5 + (0 - 5) * (1 - k)),
                int(8 + (60) * (1 - k)),
                int(14 + (120) * (1 - k)),
                255,
            )
        else:
            k = t / 0.55
            col = (
                int(ACCENT[0] * (0.15 + 0.85 * (1 - k)) + CORE[0] * (k * 0.0)),
                int(ACCENT[1] * (0.35 + 0.65 * (1 - k))),
                int(ACCENT[2] * (0.5 + 0.5 * (1 - k))),
                255,
            )
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    return img


def main() -> None:
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # outer glow halo
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse([S * 0.10, S * 0.10, S * 0.90, S * 0.90], fill=(*ACCENT, 120))
    halo = halo.filter(ImageFilter.GaussianBlur(S * 0.06))
    base = Image.alpha_composite(base, halo)

    orb = _radial_glow(S)
    base = Image.alpha_composite(base, orb)

    # thin bright rim
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    r = S * 0.44
    rd.ellipse([S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r], outline=(*ACCENT_SOFT, 230), width=int(S * 0.012))
    rim = rim.filter(ImageFilter.GaussianBlur(S * 0.004))
    base = Image.alpha_composite(base, rim)

    # stylized 'V' — two tapered strokes meeting at the bottom
    v = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    vd = ImageDraw.Draw(v)
    w = int(S * 0.055)
    apex = (S * 0.50, S * 0.70)
    vd.line([(S * 0.34, S * 0.32), apex], fill=(*CORE, 255), width=w)
    vd.line([(S * 0.66, S * 0.32), apex], fill=(*CORE, 255), width=w)
    # round the joints
    for pt in [(S * 0.34, S * 0.32), (S * 0.66, S * 0.32), apex]:
        vd.ellipse([pt[0] - w / 2, pt[1] - w / 2, pt[0] + w / 2, pt[1] + w / 2], fill=(*CORE, 255))
    glow_v = v.filter(ImageFilter.GaussianBlur(S * 0.02))
    base = Image.alpha_composite(base, glow_v)
    base = Image.alpha_composite(base, v)

    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(OUT, format="ICO", sizes=sizes)
    # also drop a 256 png preview for quick eyeballing
    base.resize((256, 256), Image.LANCZOS).save(OUT.with_suffix(".png"))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes) + preview png")


if __name__ == "__main__":
    main()
