"""
Arc reactor banner — JARVIS style with VECTOR text in core.

Used by both `vector` (Python REPL) and `vector-tui` (Node TUI) for visual parity.
Produces ANSI-colored Unicode art representing an arc reactor symbol.
"""
from __future__ import annotations

# Color codes
_DIM = "\x1b[2;36m"      # dim cyan (outer ring)
_CYN = "\x1b[36m"        # cyan (mid ring)
_CYB = "\x1b[96m"        # bright cyan (inner ring)
_WHB = "\x1b[97;1m"      # bright white bold (core text)
_R = "\x1b[0m"


def arc_reactor_medium(show_text: bool = True) -> str:
    """Return a multi-line arc reactor (~22 cols × 8 rows)."""
    v_e_c = f"{_WHB}V·E·C{_R}" if show_text else "     "
    t_o_r = f"{_WHB}T·O·R{_R}" if show_text else "     "
    rows = [
        f"      {_DIM}╱─────────────╲{_R}      ",
        f"    {_DIM}╱{_R}  {_CYN}╱─────────╲{_R}  {_DIM}╲{_R}    ",
        f"   {_DIM}│{_R}  {_CYN}│{_R} {_CYB}╭─────╮{_R} {_CYN}│{_R}  {_DIM}│{_R}   ",
        f"   {_DIM}│{_R}  {_CYN}│{_R} {_CYB}│{_R} {v_e_c} {_CYB}│{_R} {_CYN}│{_R}  {_DIM}│{_R}   ",
        f"   {_DIM}│{_R}  {_CYN}│{_R} {_CYB}│{_R} {t_o_r} {_CYB}│{_R} {_CYN}│{_R}  {_DIM}│{_R}   ",
        f"   {_DIM}│{_R}  {_CYN}│{_R} {_CYB}╰─────╯{_R} {_CYN}│{_R}  {_DIM}│{_R}   ",
        f"    {_DIM}╲{_R}  {_CYN}╲─────────╱{_R}  {_DIM}╱{_R}    ",
        f"      {_DIM}╲─────────────╱{_R}      ",
    ]
    return "\n".join(rows)


def arc_reactor_small() -> str:
    """One-line inline reactor glyph for prompts/status bars."""
    return f"{_CYN}⟨{_R}{_WHB}◉{_R}{_CYN}⟩{_R}"


def arc_reactor_large(show_text: bool = True) -> str:
    """Splash-screen-sized reactor (~36 cols × 11 rows)."""
    vec = f"{_WHB}V · E · C{_R}" if show_text else "         "
    core = f"{_WHB}⟨▶⟩  CORE{_R}" if show_text else "         "
    tor = f"{_WHB}T · O · R{_R}" if show_text else "         "
    rows = [
        f"          {_DIM}▄▄▄▄▄▄▄▄▄▄▄▄▄{_R}          ",
        f"       {_DIM}▄{_R}{_CYN}██████▀▀▀▀▀▀▀██████{_R}{_DIM}▄{_R}       ",
        f"     {_DIM}▄{_R}{_CYN}███▀{_R}{_CYB}  ╭─────────╮  {_R}{_CYN}▀███{_R}{_DIM}▄{_R}     ",
        f"    {_CYN}██▀{_R}{_CYB}   ╭─────────╮   {_R}{_CYN}▀██{_R}    ",
        f"   {_CYN}██{_R}{_CYB}    │ {_R}{vec}{_CYB} │    {_R}{_CYN}██{_R}   ",
        f"  {_CYN}██{_R}{_CYB}     │ {_R}{core}{_CYB} │     {_R}{_CYN}██{_R}  ",
        f"   {_CYN}██{_R}{_CYB}    │ {_R}{tor}{_CYB} │    {_R}{_CYN}██{_R}   ",
        f"    {_CYN}██▄{_R}{_CYB}   ╰─────────╯   {_R}{_CYN}▄██{_R}    ",
        f"     {_DIM}▀{_R}{_CYN}███▄{_R}{_CYB}  ╰─────────╯  {_R}{_CYN}▄███{_R}{_DIM}▀{_R}     ",
        f"       {_DIM}▀{_R}{_CYN}██████▄▄▄▄▄▄▄██████{_R}{_DIM}▀{_R}       ",
        f"          {_DIM}▀▀▀▀▀▀▀▀▀▀▀▀▀{_R}          ",
    ]
    return "\n".join(rows)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print()
    print("── small ──")
    print(arc_reactor_small())
    print()
    print("── medium ──")
    print(arc_reactor_medium())
    print()
    print("── large ──")
    print(arc_reactor_large())
    print()
