"""
V.E.C.T.O.R. coding district.
Architect, code reviewer, git bot, test writer, bug hunter.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger

from .architect_bot import ArchitectBot
from .code_reviewer import CodeReviewer
from .git_bot import GitBot
from .test_writer import TestWriter
from .bug_hunter import BugHunter
from .gui_automation_agent import GUIAutomationAgent
from .code_conductor_agent import CodeConductorAgent

logger.info("[VECTOR] coding district loaded")

__all__ = ["ArchitectBot", "CodeReviewer", "GitBot", "TestWriter", "BugHunter", "GUIAutomationAgent", "CodeConductorAgent"]


def get_agent(name: str):
    agents = {
        "ArchitectBot":       ArchitectBot,
        "CodeReviewer":       CodeReviewer,
        "GitBot":             GitBot,
        "TestWriter":         TestWriter,
        "BugHunter":          BugHunter,
        "GUIAutomationAgent": GUIAutomationAgent,
        "gui_automation":     GUIAutomationAgent,
    }
    return agents.get(name)