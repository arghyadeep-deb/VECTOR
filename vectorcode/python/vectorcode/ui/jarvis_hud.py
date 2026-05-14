"""
VectorCode JARVIS HUD — circular reactor splash for the `vector` Python CLI.

Renders the same 74×26 grid as the Ink TUI version, but as a static frame
(can be animated by calling repeatedly with incrementing tick).

Design: 4 concentric rings (outer with sweeping arc, tick marks, dashed middle,
inner dots), center V.E.C.T.O.R. text, corner blueprint schematics, status bar.
"""
from __future__ import annotations

import math
import sys

# ─── Grid Constants ───────────────────────────────────────────────────────────
COLS = 74
GRID_ROWS = 26
CX = 37
CY = 13
ASPECT = 0.48
OUTER_R = 11.5
TICK_R = 10.5
MID_R = 8.8
INNER_R = 6.5

# ─── ANSI 24-bit color codes ──────────────────────────────────────────────────
def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\x1b[38;2;{r};{g};{b}m"

C = {
    "yellow":     _rgb("#ffd700"),
    "cyan":       _rgb("#00e5ff"),
    "cyanBright": _rgb("#40ffff"),
    "cyanMid":    _rgb("#00aacc"),
    "cyanDim":    _rgb("#006688"),
    "cyanDark":   _rgb("#003344"),
    "bgDot":      _rgb("#0d2233"),
    "white":      _rgb("#e8f8ff"),
    "dimWhite":   _rgb("#7aabb8"),
    "green":      _rgb("#00ff88"),
    "gray":       _rgb("#445566"),
}
BOLD = "\x1b[1m"
RESET = "\x1b[0m"


def _is_blueprint_dot(r: int, c: int) -> bool:
    dx = (c - CX) * ASPECT
    dy = r - CY
    dist = math.sqrt(dx * dx + dy * dy)
    if dist >= OUTER_R - 2:
        return False
    return c % 4 == 1 and r % 2 == 0


def _build_frame(tick: int) -> list[list[tuple[str, str, bool]]]:
    """Build a 2D grid of (char, color, bold) cells."""
    grid = [[(" ", C["bgDot"], False) for _ in range(COLS)] for _ in range(GRID_ROWS)]

    def put(r, c, ch, color, bold=False):
        if 0 <= r < GRID_ROWS and 0 <= c < COLS:
            grid[r][c] = (ch, color, bold)

    # Blueprint background dots
    for r in range(GRID_ROWS):
        for c in range(COLS):
            if _is_blueprint_dot(r, c):
                put(r, c, "·", C["bgDot"])

    # Rings
    for r in range(GRID_ROWS):
        for c in range(COLS):
            dx = (c - CX) * ASPECT
            dy = r - CY
            dist = math.sqrt(dx * dx + dy * dy)
            angle = (math.degrees(math.atan2(dy, dx)) + 360) % 360

            # Outer ring — yellow arc + dim cyan dots
            if abs(dist - OUTER_R) < 0.82:
                arc_start = (tick * 2.5) % 360
                arc_len = 85
                arc_end = (arc_start + arc_len) % 360
                in_arc = (
                    angle >= arc_start and angle <= arc_end
                    if arc_start <= arc_end
                    else angle >= arc_start or angle <= arc_end
                )
                if in_arc:
                    put(r, c, "●", C["yellow"])
                else:
                    put(r, c, "·", C["cyanDim"])

            # Tick marks
            elif abs(dist - TICK_R) < 0.55:
                if angle % 45 < 6:
                    put(r, c, "◆", C["cyan"], True)
                elif angle % 15 < 4:
                    put(r, c, "◇", C["cyanMid"])
                else:
                    put(r, c, "·", C["cyanDark"])

            # Middle dashed
            elif abs(dist - MID_R) < 0.52:
                seg = (int(angle) // 5) % 3
                if seg == 0:
                    put(r, c, "─", C["cyanDim"])
                elif seg == 1:
                    put(r, c, "·", C["cyanDark"])

            # Inner dots
            elif abs(dist - INNER_R) < 0.5:
                put(r, c, "·", C["gray"])

    # Center text
    top_label = "── V.E.C.T.O.R. ──"
    top_row = round(CY) - 1
    top_start = round(CX - len(top_label) / 2)
    for i, ch in enumerate(top_label):
        put(top_row, top_start + i, ch, C["cyanBright"], True)

    titles = [
        "Virtual Entity for",
        "Cognitive Tasks and",
        "Operational Reasoning",
    ]
    m_row = round(CY)
    for offset, txt in enumerate(titles):
        start = round(CX - len(txt) / 2)
        for i, ch in enumerate(txt):
            put(m_row + offset, start + i, ch, C["dimWhite"])

    ver = "[ v0.1.0 ]"
    ver_row = round(CY) + 4
    ver_start = round(CX - len(ver) / 2)
    for i, ch in enumerate(ver):
        put(ver_row, ver_start + i, ch, C["cyanDim"])

    # Scanning dot
    scan_angle = (tick * 3) % 360
    scan_r = round(CY + (MID_R + 1.5) * math.sin(math.radians(scan_angle)))
    scan_c = round(CX + (MID_R + 1.5) / ASPECT * math.cos(math.radians(scan_angle)))
    put(scan_r, scan_c, "◉", C["cyanBright"], True)

    # Corner blueprint
    corners = [
        (0, 0), (0, 2), (1, 0),
        (0, COLS - 1), (0, COLS - 3), (1, COLS - 1),
        (GRID_ROWS - 1, 0), (GRID_ROWS - 2, 0), (GRID_ROWS - 1, 2),
        (GRID_ROWS - 1, COLS - 1), (GRID_ROWS - 2, COLS - 1), (GRID_ROWS - 1, COLS - 3),
    ]
    for r, c in corners:
        put(r, c, "┼", C["cyanDark"])

    for i in range(3, 10):
        put(0, i, "─", C["cyanDark"])
        put(0, COLS - 1 - i, "─", C["cyanDark"])
        put(GRID_ROWS - 1, i, "─", C["cyanDark"])
        put(GRID_ROWS - 1, COLS - 1 - i, "─", C["cyanDark"])
    for i in range(2, 5):
        put(i, 0, "│", C["cyanDark"])
        put(i, COLS - 1, "│", C["cyanDark"])
        put(GRID_ROWS - 1 - i, 0, "│", C["cyanDark"])
        put(GRID_ROWS - 1 - i, COLS - 1, "│", C["cyanDark"])

    # Data readouts
    top_right = f"Cu:{(tick % 100):02d}"
    bot_left = f"At:{((tick * 3) % 100):02d}"
    bot_right = f"No:{((tick * 7) % 100):02d}"
    for i, ch in enumerate(top_right):
        put(1, COLS - 10 + i, ch, C["gray"])
    for i, ch in enumerate(bot_left):
        put(GRID_ROWS - 2, 1 + i, ch, C["gray"])
    for i, ch in enumerate(bot_right):
        put(GRID_ROWS - 2, COLS - 10 + i, ch, C["gray"])

    return grid


def _grid_to_string(grid) -> str:
    out = []
    for row in grid:
        line_parts = []
        for ch, color, bold in row:
            if ch == " ":
                line_parts.append(" ")
            else:
                if bold:
                    line_parts.append(f"{BOLD}{color}{ch}{RESET}")
                else:
                    line_parts.append(f"{color}{ch}{RESET}")
        out.append("".join(line_parts))
    return "\n".join(out)


def _status_bar(model: str, n_models: int, has_vectormd: bool, blink: bool = True) -> str:
    """Render the status bar below the HUD."""
    sep = f"{C['cyanDark']}{'─' * COLS}{RESET}"

    online_dot = (
        f"{BOLD}{C['green']}● online{RESET}"
        if blink
        else f"{C['cyanDark']}● online{RESET}"
    )

    # Status row
    status_line = (
        f"{C['cyanDim']}Model{RESET} {BOLD}{C['cyan']}{model}{RESET}   "
        f"{C['gray']}·{RESET}   "
        f"{C['cyanDim']}Status{RESET} {online_dot}   "
        f"{C['gray']}·{RESET}   "
        f"{C['white']}{n_models}{RESET} {C['cyanDim']}models{RESET}"
    )
    # Pad to center
    visible = f"Model {model}   ·   Status ● online   ·   {n_models} models"
    pad = max(0, (COLS - len(visible)) // 2)
    status_line = " " * pad + status_line

    # Commands row
    cmds = [("/help", "list commands"), ("@<file>", "attach files"),
            ("/sparc", "run pipeline"), ("/quit", "exit")]
    cmd_parts = [f"{BOLD}{C['cyan']}{c}{RESET}{C['gray']} {d}{RESET}" for c, d in cmds]
    cmd_line = "  ".join(cmd_parts)
    visible_cmd = "  ".join(f"{c} {d}" for c, d in cmds)
    pad = max(0, (COLS - len(visible_cmd)) // 2)
    cmd_line = " " * pad + cmd_line

    # Footer
    md_status = (
        f"{C['green']}● VECTOR.md loaded{RESET}"
        if has_vectormd
        else f"{C['cyanDark']}○ No VECTOR.md  ·  /init{RESET}"
    )
    footer = f"{md_status}  {C['gray']}repl · {model}{RESET}"
    visible_footer = ("● VECTOR.md loaded" if has_vectormd else "○ No VECTOR.md  ·  /init") + f"  repl · {model}"
    pad = max(0, (COLS - len(visible_footer)) // 2)
    footer = " " * pad + footer

    return f"{sep}\n{status_line}\n{cmd_line}\n{sep}\n{footer}"


def render_hud(
    model: str = "vector-focus",
    n_models: int = 0,
    has_vectormd: bool = False,
    tick: int = 0,
) -> str:
    """Return the full HUD as a single string (ready to print)."""
    grid = _build_frame(tick)
    hud_str = _grid_to_string(grid)
    status = _status_bar(model, n_models, has_vectormd, blink=(tick % 16 < 10))
    return f"{hud_str}\n{status}"


def print_hud(
    model: str = "vector-focus",
    n_models: int = 0,
    has_vectormd: bool = False,
    tick: int = 0,
    file=None,
) -> None:
    """Print the HUD to stderr (or specified file)."""
    if file is None:
        file = sys.stderr
    print(render_hud(model, n_models, has_vectormd, tick), file=file)


# ─── Demo / animation loop ────────────────────────────────────────────────────
def animate(duration_seconds: float = 5.0, fps: int = 18,
            model: str = "vector-focus", n_models: int = 0,
            has_vectormd: bool = False) -> None:
    """Animate the HUD for a fixed duration. Clears + redraws each frame."""
    import time
    tick = 0
    n_frames = int(duration_seconds * fps)
    for _ in range(n_frames):
        # Move cursor home + clear screen below
        sys.stderr.write("\x1b[H\x1b[2J")
        print_hud(model, n_models, has_vectormd, tick)
        sys.stderr.flush()
        tick += 1
        time.sleep(1.0 / fps)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "--animate":
        animate(5.0, 18, "vector-focus", 21)
    else:
        print_hud("vector-focus", 21, False, tick=42)
