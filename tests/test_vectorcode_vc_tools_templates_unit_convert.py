"""Regression test: unit_convert.toml must actually convert between units.

The template's expression was ``str(float(value))`` -- it ignored from_unit/
to_unit entirely and just echoed the numeric value back, the same
"doesn't do what it claims" bug class already fixed in base64_encode,
hash_compute, regex_extract, and date_info this audit cycle.
"""

from __future__ import annotations

from pathlib import Path

from vectorcode.src.vc_tools.templates.loader import load_template

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "vectorcode"
    / "src"
    / "vc_tools"
    / "templates"
    / "builtin"
    / "unit_convert.toml"
)


def test_unit_convert_length() -> None:
    tool = load_template(_TEMPLATE_PATH)
    result = tool.execute(value=1, from_unit="km", to_unit="m")
    assert result.success is True
    assert float(result.content) == 1000.0


def test_unit_convert_temperature() -> None:
    tool = load_template(_TEMPLATE_PATH)
    result = tool.execute(value=100, from_unit="c", to_unit="f")
    assert result.success is True
    assert float(result.content) == 212.0


def test_unit_convert_mass_round_trip() -> None:
    tool = load_template(_TEMPLATE_PATH)
    result = tool.execute(value=2.2046226218, from_unit="lb", to_unit="kg")
    assert result.success is True
    assert abs(float(result.content) - 1.0) < 1e-6


def test_unit_convert_rejects_unknown_unit() -> None:
    tool = load_template(_TEMPLATE_PATH)
    result = tool.execute(value=1, from_unit="parsecs", to_unit="m")
    assert result.success is False
