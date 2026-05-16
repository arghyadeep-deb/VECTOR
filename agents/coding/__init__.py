"""
V.E.C.T.O.R. coding district.
Architect, code reviewer, git bot, test writer, bug hunter.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from .architect_bot import ArchitectBot
from .code_reviewer import CodeReviewer
from .git_bot import GitBot
from .test_writer import TestWriter
from .bug_hunter import BugHunter

logger.info("[VECTOR] coding district loaded")

__all__ = ["ArchitectBot", "CodeReviewer", "GitBot", "TestWriter", "BugHunter"]