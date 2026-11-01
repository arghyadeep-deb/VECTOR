"""
VECTOR Vision Control
VLM-powered GUI automation — natural language → screenshot → action → repeat.

Architecture:
  action_parser    — parse VLM output text into typed action dicts
  vision_operator  — execute actions on the local PC (wraps pc_controller + mss)
  gui_agent        — the agent loop: screenshot → VLM → parse → execute → repeat
  browser_controller — VLM-driven Playwright browser automation

Usage:
    from core.vision_control import GUIAgent, VisionOperator
    agent = GUIAgent()
    result = asyncio.run(agent.run("Open Notepad and type Hello"))
"""
__version__ = "1.0.0"

from core.vision_control.action_parser import action_parser  # noqa: F401
from core.vision_control.vision_operator import ACTION_SPACE  # noqa: F401
from core.vision_control.vision_operator import VisionOperator
from core.vision_control.gui_agent import GUIAgent, GUIStatus
from core.vision_control.browser_controller import BrowserController

__all__ = [
    "GUIAgent",
    "GUIStatus",
    "VisionOperator",
    "BrowserController",
    "action_parser",
    "ACTION_SPACE",
]
