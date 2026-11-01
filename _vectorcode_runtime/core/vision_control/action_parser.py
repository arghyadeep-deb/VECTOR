"""
VECTOR Vision Control — Action Parser
Python port of UI-TARS-desktop/packages/ui-tars/action-parser/src/actionParser.ts

Parses VLM model output text into structured action dicts with screen coordinates.

The VLM outputs text like:
    Thought: I see a login button on the right side.
    Action: click(start_box='<point>862 519</point>')

This parser converts it to:
    {
      "action_type": "click",
      "action_inputs": {"start_box": "[0.862, 0.519, 0.862, 0.519]"},
      "start_coords": (862, 519),   # absolute screen pixels
      "thought": "I see a login button on the right side.",
      "reflection": None,
    }

Usage:
    actions = action_parser("Thought: click submit\nAction: click(start_box='<point>500 300</point>')",
                             factors=[1000, 1000],
                             screen_ctx={"width": 1920, "height": 1080})
"""
from __future__ import annotations

__all__ = [
    "action_parser",
    "IMAGE_FACTOR",
    "MAX_PIXELS_V1_5",
    "MAX_RATIO",
    "MIN_PIXELS",
    "smart_resize_v15",
]


import json
import math
import re
import sys
from typing import Optional


# ── Constants (from @ui-tars/shared/types) ────────────────────────────────────
MAX_RATIO   = 200
IMAGE_FACTOR = 28
MIN_PIXELS   = 4 * 28 * 28      # 3136
MAX_PIXELS_V1_5 = 16384 * 28 * 28  # ~12.8M


# ── Smart resize helpers ──────────────────────────────────────────────────────

def _round_by(n: float, factor: int) -> int:
    return round(n / factor) * factor

def _floor_by(n: float, factor: int) -> int:
    return math.floor(n / factor) * factor

def _ceil_by(n: float, factor: int) -> int:
    return math.ceil(n / factor) * factor


def smart_resize_v15(
    height: int,
    width: int,
    max_ratio: int = MAX_RATIO,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS_V1_5,
) -> tuple[int, int] | None:
    """Compute resize dims for V1.5 model — maintains aspect ratio within pixel budget."""
    if max(height, width) / max(min(height, width), 1) > max_ratio:
        return None
    w_bar = max(factor, _round_by(width, factor))
    h_bar = max(factor, _round_by(height, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = _floor_by(height / beta, factor)
        w_bar = _floor_by(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / max(height * width, 1))
        h_bar = _ceil_by(height * beta, factor)
        w_bar = _ceil_by(width * beta, factor)
    return w_bar, h_bar


# ── Low-level action string parser ────────────────────────────────────────────

def _parse_action_str(action_str: str) -> dict | None:
    """
    Parse a function-call string like:
        click(start_box='<point>510 150</point>')
    into:
        {"function": "click", "args": {"start_box": "(510,150)"}}
    """
    try:
        # Normalize special box formats
        action_str = re.sub(r"<\|box_start\|>|<\|box_end\|>", "", action_str)
        # Order matters: replace qualified forms first so standalone point= doesn't double-replace
        action_str = action_str.replace("start_point=", "start_box=")
        action_str = action_str.replace("end_point=", "end_box=")
        # Replace bare point= (not already prefixed) → start_box=
        action_str = re.sub(r"\bpoint=", "start_box=", action_str)

        m = re.match(r"^(\w+)\((.*)\)$", action_str.strip(), re.DOTALL)
        if not m:
            return None
        fn_name, args_str = m.group(1), m.group(2)

        kwargs: dict[str, str] = {}
        if args_str.strip():
            # Split on commas not inside quotes
            pairs = re.findall(r"(?:[^,']|'[^']*')+", args_str)
            for pair in pairs:
                if "=" not in pair:
                    continue
                key, *val_parts = pair.split("=")
                val = "=".join(val_parts).strip().strip("'\"")

                # <bbox>x1 y1 x2 y2</bbox> → (x1,y1,x2,y2)
                if "<bbox>" in val:
                    val = re.sub(r"</?bbox>", "", val).strip()
                    val = "(" + re.sub(r"\s+", ",", val) + ")"

                # <point>x y</point> → (x,y)
                if "<point>" in val:
                    val = re.sub(r"</?point>", "", val).strip()
                    val = "(" + re.sub(r"\s+", ",", val) + ")"

                kwargs[key.strip()] = val

        return {"function": fn_name, "args": kwargs}
    except Exception:
        return None


# ── Main parser ───────────────────────────────────────────────────────────────

def action_parser(
    prediction: str,
    factors: list[int] | tuple[int, int] = (1000, 1000),
    screen_ctx: dict | None = None,    # {"width": int, "height": int}
    scale_factor: float = 1.0,
    mode: str = "bc",                  # "bc" (standard) or "o1" (reasoning)
    model_ver: str = "v1.0",           # "v1.0" or "v1.5"
) -> list[dict]:
    """
    Parse VLM prediction text into a list of structured action dicts.

    Each dict has:
      action_type   — "click", "type", "scroll", "hotkey", "drag", "wait",
                      "finished", "call_user", "error_env", ""
      action_inputs — raw parsed params (start_box, content, key, direction, …)
      start_coords  — (x, y) in absolute screen pixels (if screen_ctx given)
      end_coords    — (x, y) in absolute screen pixels for drag end
      thought       — VLM reasoning text
      reflection    — VLM self-correction text (optional)
    """
    factors = list(factors)
    reflection: str | None = None
    thought: str | None = None
    action_str = ""

    smart_resize = None
    if model_ver == "v1.5" and screen_ctx:
        smart_resize = smart_resize_v15(screen_ctx.get("height", 0), screen_ctx.get("width", 0))

    text = prediction.strip()

    # ── Extract thought / reflection ──────────────────────────────────────────
    if mode == "bc":
        if "Thought:" in text:
            m = re.search(r"Thought:([\s\S]+?)(?=\s*Action[:：]|$)", text)
            if m:
                thought = m.group(1).strip()
        elif text.startswith("Reflection:"):
            m = re.search(r"Reflection:([\s\S]+?)Action_Summary:([\s\S]+?)(?=\s*Action[:：]|$)", text)
            if m:
                reflection = m.group(1).strip()
                thought = m.group(2).strip()
        elif text.startswith("Action_Summary:"):
            m = re.search(r"Action_Summary:(.+?)(?=\s*Action[:：]|$)", text)
            if m:
                thought = m.group(1).strip()

        if not re.search(r"Action[:：]", text):
            action_str = text
        else:
            parts = re.split(r"Action[:：]", text)
            action_str = parts[-1]

    elif mode == "o1":
        m_thought = re.search(r"<Thought>\s*(.*?)\s*</Thought>", text, re.DOTALL)
        m_summary = re.search(r"\nAction_Summary:\s*(.*?)\s*Action:", text, re.DOTALL)
        m_action  = re.search(r"\nAction:\s*(.*?)\s*</Output>", text, re.DOTALL)
        thought = (
            f"{m_thought.group(1) if m_thought else ''}\n"
            f"<Action_Summary>\n{m_summary.group(1) if m_summary else ''}"
        )
        action_str = m_action.group(1) if m_action else ""

    # ── Parse each action block ───────────────────────────────────────────────
    raw_actions = action_str.split("\n\n")
    actions: list[dict] = []

    for raw in raw_actions:
        raw = raw.replace("\n", r"\n").strip()
        parsed = _parse_action_str(raw)
        action_type = ""
        action_inputs: dict = {}
        start_coords: tuple | None = None
        end_coords:   tuple | None = None

        if parsed:
            action_type = parsed["function"]
            params = parsed["args"]

            for param_name, param_val in params.items():
                if not param_val:
                    continue
                trimmed = param_val.strip()

                if "start_box" in param_name or "end_box" in param_name:
                    # Strip brackets/parens and split numbers
                    raw_nums = re.sub(r"[()[\]]", "", trimmed)
                    num_strs = [s for s in re.split(r"[,\s]+", raw_nums) if s]
                    try:
                        nums = [float(s) for s in num_strs]
                    except ValueError:
                        continue

                    # Scale to normalized [0,1]
                    scaled = []
                    for i, n in enumerate(nums):
                        fi = i % 2
                        if model_ver == "v1.5" and smart_resize:
                            scaled.append(n / smart_resize[fi])
                        else:
                            scaled.append(n / factors[fi])

                    # If only (x, y) provided, duplicate to (x1, y1, x2, y2)
                    if len(scaled) == 2:
                        scaled = scaled + scaled

                    action_inputs[param_name.strip()] = json.dumps(scaled)

                    # Compute absolute pixel coords if screen_ctx given
                    if screen_ctx and len(scaled) == 4:
                        x1, y1, x2, y2 = scaled
                        sw, sh = screen_ctx["width"], screen_ctx["height"]
                        cx = round(((x1 + x2) / 2) * sw * scale_factor)
                        cy = round(((y1 + y2) / 2) * sh * scale_factor)
                        if "start_box" in param_name:
                            start_coords = (cx, cy)
                        else:
                            end_coords = (cx, cy)
                else:
                    action_inputs[param_name.strip()] = trimmed

        actions.append({
            "action_type":   action_type,
            "action_inputs": action_inputs,
            "start_coords":  start_coords,
            "end_coords":    end_coords,
            "thought":       thought or "",
            "reflection":    reflection,
        })

    return actions


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    screen = {"width": 1920, "height": 1080}

    tests = [
        ("click point", "Thought: Click the button.\nAction: click(start_box='<point>862 519</point>')", "click"),
        ("type text",   "Action: type(content='hello world')", "type"),
        ("hotkey",      "Action: hotkey(key='ctrl c')", "hotkey"),
        ("scroll",      "Action: scroll(start_box='<point>500 400</point>', direction='down')", "scroll"),
        ("drag",        "Action: drag(start_box='<point>100 200</point>', end_box='<point>300 400</point>')", "drag"),
        ("finished",    "Action: finished()", "finished"),
        ("bbox format", "Action: click(start_box='<bbox>850 510 874 528</bbox>')", "click"),
    ]

    for name, pred, expected_type in tests:
        result = action_parser(pred, factors=[1000, 1000], screen_ctx=screen)
        assert result, f"Empty result for {name}"
        assert result[0]["action_type"] == expected_type, f"{name}: expected {expected_type}, got {result[0]['action_type']}"
        if expected_type in ("click", "scroll", "drag"):
            assert result[0]["start_coords"] is not None, f"{name}: no start_coords"
        print(f"  OK {name}: {result[0]['action_type']} coords={result[0].get('start_coords')}")

    print("OK action_parser.py")
