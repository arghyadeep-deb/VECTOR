"""
V.E.C.T.O.R. coding district.
Architect, code reviewer, git bot, test writer, bug hunter,
plus specialized reviewers: Python, FastAPI, Security.
"""
from loguru import logger

from .architect_bot import ArchitectBot
from .code_reviewer import CodeReviewer
from .git_bot import GitBot
from .test_writer import TestWriter
from .bug_hunter import BugHunter
from .gui_automation_agent import GUIAutomationAgent
from .code_conductor_agent import CodeConductorAgent
from .mlops_agent import MLOpsAgent
from .python_reviewer import PythonReviewer
from .fastapi_reviewer import FastAPIReviewer
from .security_reviewer import SecurityReviewer

logger.info("[VECTOR] coding district loaded")

__all__ = [
    "ArchitectBot",
    "CodeReviewer",
    "GitBot",
    "TestWriter",
    "BugHunter",
    "GUIAutomationAgent",
    "CodeConductorAgent",
    "MLOpsAgent",
    "PythonReviewer",
    "FastAPIReviewer",
    "SecurityReviewer",
]


def get_agent(name: str):
    agents = {
        "ArchitectBot":       ArchitectBot,
        "CodeReviewer":       CodeReviewer,
        "GitBot":             GitBot,
        "TestWriter":         TestWriter,
        "BugHunter":          BugHunter,
        "GUIAutomationAgent": GUIAutomationAgent,
        "gui_automation":     GUIAutomationAgent,
        "CodeConductorAgent": CodeConductorAgent,
        "code_conductor":     CodeConductorAgent,
        "PythonReviewer":     PythonReviewer,
        "python_reviewer":    PythonReviewer,
        "FastAPIReviewer":    FastAPIReviewer,
        "fastapi_reviewer":   FastAPIReviewer,
        "SecurityReviewer":   SecurityReviewer,
        "security_reviewer":  SecurityReviewer,
    }
    return agents.get(name)