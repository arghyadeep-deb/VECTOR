"""
VECTOR Code Conductor
Multi-agent AI coding orchestrator — port of codebuff's base2 architecture.

Beats single-model coding approaches by coordinating specialized sub-agents:
  1. File picker + code searcher (parallel)
  2. Context builder → planner → editor (sequential)
  3. Reviewer

Core tools:
  str_replace  — surgical exact-string replacement (the key precision editing tool)
  write_file   — create/overwrite files
  read_files   — multi-file reading with gitignore + truncation
  apply_patch  — unified diff application

Code intelligence:
  CodeMap      — AST-based symbol indexing (functions, classes, imports)

Eval:
  GitEvalRunner — measure coding accuracy by reconstructing git commits

Usage:
    from core.code_conductor import CodingOrchestrator, str_replace, CodeMap

    # Single precision edit
    result = str_replace("core/config.py", "old_code_here", "new_code_here")

    # Full multi-agent coding task
    orch = CodingOrchestrator(cwd="/path/to/project")
    result = asyncio.run(orch.run("Add rate limiting to all API endpoints"))
    logger.info(result["summary"])


    # Code intelligence
    cm = CodeMap("/path/to/project")
    cm.build()
    logger.info(cm.query("GUIAgent"))   # find all definitions

"""
__version__ = "1.0.0"

from core.code_conductor.str_replace import str_replace, write_file, apply_patch, read_files
from core.code_conductor.code_map import CodeMap, Symbol
from core.code_conductor.agent_steps import run_steps, StepResult, bash_steps, read_and_edit_steps
from core.code_conductor.orchestrator import CodingOrchestrator
from core.code_conductor.git_eval import GitEvalRunner

__all__ = [
    # Precision editing tools
    "str_replace",
    "write_file",
    "apply_patch",
    "read_files",
    # Code intelligence
    "CodeMap",
    "Symbol",
    # Agent step pattern
    "run_steps",
    "StepResult",
    "bash_steps",
    "read_and_edit_steps",
    # Orchestrator
    "CodingOrchestrator",
    # Evaluation
    "GitEvalRunner",
]
