"""
CADEngine — FreeCAD geometric analysis wrapper.
Lazy-imports FreeCAD; degrades to analytical geometry if not installed.
Architecture invariant: loop must never crash on ImportError.
"""

import math
from typing import Any
from loguru import logger
from core.config import CONFIG


class CADEngine:
    """
    Geometric solid analysis via FreeCAD Part module.
    Degrades to analytical geometry if FreeCAD is not installed.
    """

    def __init__(self):
        self._freecad_available: bool | None = None
        self._Part = None
        logger.info("[VECTOR][cad] CADEngine ready")

    def _check_freecad(self) -> bool:
        if self._freecad_available is None:
            try:
                import FreeCAD  # noqa: F401
                import Part
                self._Part = Part
                self._freecad_available = True
                logger.debug("[VECTOR][cad] FreeCAD available")
            except ImportError:
                self._freecad_available = False
                logger.debug("[VECTOR][cad] FreeCAD not installed — analytical mode")
        return self._freecad_available

    # ── public API ────────────────────────────────────────────────────────────
    def analyze_box(self, length: float, width: float, height: float) -> dict:
        """Return volume, surface area, diagonal of a rectangular box."""
        if self._check_freecad():
            return self._freecad_box(length, width, height)
        return self._analytical_box(length, width, height)

    def analyze_cylinder(self, radius: float, height: float) -> dict:
        """Return volume and surface area of a cylinder."""
        if self._check_freecad():
            return self._freecad_cylinder(radius, height)
        return self._analytical_cylinder(radius, height)

    def analyze_sphere(self, radius: float) -> dict:
        """Return volume and surface area of a sphere."""
        vol = (4 / 3) * math.pi * radius ** 3
        area = 4 * math.pi * radius ** 2
        return {
            "radius": radius,
            "volume": round(vol, 6),
            "surface_area": round(area, 6),
            "method": "analytical",
        }

    def get_capabilities(self) -> dict:
        return {
            "freecad_available": self._check_freecad(),
            "mode": "freecad" if self._check_freecad() else "analytical",
            "shapes": ["box", "cylinder", "sphere"],
        }

    # ── FreeCAD implementation ────────────────────────────────────────────────
    def _freecad_box(self, l: float, w: float, h: float) -> dict:
        try:
            box = self._Part.makeBox(l, w, h)
            return {
                "length": l, "width": w, "height": h,
                "volume": round(box.Volume, 6),
                "surface_area": round(box.Area, 6),
                "diagonal": round(math.sqrt(l**2 + w**2 + h**2), 6),
                "method": "freecad",
            }
        except Exception as e:
            logger.warning("[VECTOR][cad] FreeCAD box failed: {}", e)
            return self._analytical_box(l, w, h)

    def _freecad_cylinder(self, r: float, h: float) -> dict:
        try:
            cyl = self._Part.makeCylinder(r, h)
            return {
                "radius": r, "height": h,
                "volume": round(cyl.Volume, 6),
                "surface_area": round(cyl.Area, 6),
                "method": "freecad",
            }
        except Exception as e:
            logger.warning("[VECTOR][cad] FreeCAD cylinder failed: {}", e)
            return self._analytical_cylinder(r, h)

    # ── analytical fallbacks ──────────────────────────────────────────────────
    def _analytical_box(self, l: float, w: float, h: float) -> dict:
        return {
            "length": l, "width": w, "height": h,
            "volume": round(l * w * h, 6),
            "surface_area": round(2 * (l*w + l*h + w*h), 6),
            "diagonal": round(math.sqrt(l**2 + w**2 + h**2), 6),
            "method": "analytical",
        }

    def _analytical_cylinder(self, r: float, h: float) -> dict:
        vol = math.pi * r**2 * h
        area = 2 * math.pi * r * (r + h)
        return {
            "radius": r, "height": h,
            "volume": round(vol, 6),
            "surface_area": round(area, 6),
            "method": "analytical",
        }


if __name__ == "__main__":
    eng = CADEngine()
    caps = eng.get_capabilities()
    print(f"  mode={caps['mode']} freecad={caps['freecad_available']}")

    box = eng.analyze_box(3.0, 4.0, 5.0)
    assert abs(box["volume"] - 60.0) < 0.01, f"Box volume wrong: {box['volume']}"
    assert abs(box["surface_area"] - 94.0) < 0.01, f"Box SA wrong: {box['surface_area']}"

    cyl = eng.analyze_cylinder(2.0, 5.0)
    assert abs(cyl["volume"] - math.pi * 4 * 5) < 0.01, f"Cylinder volume wrong: {cyl['volume']}"

    sph = eng.analyze_sphere(3.0)
    assert abs(sph["volume"] - (4/3)*math.pi*27) < 0.01, f"Sphere volume wrong: {sph['volume']}"

    print(f"OK cad_engine -- box_vol={box['volume']} cyl_vol={cyl['volume']:.3f} method={box['method']}")
