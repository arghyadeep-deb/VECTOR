"""Fix remaining \"hermes\" references in absorbed modules."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path("vectorcode/src")

# Files with known hermes references to fix
FILES_WITH_IMPORTS = [
    "vector_cli/env_loader.py",
    "providers/__init__.py",
    "providers/base.py",
    "agent/web_search_registry.py",
    "agent/web_search_provider.py",
    "vector_cli/security_advisories.py",
    "agent/plugin_llm.py",
    "vector_cli/eval_cmd.py",
]

# Specific replacements for each file type
REPLACEMENTS: list[tuple[str, str]] = [
    # Docstring/comment refs
    ("hermes tools", "vector tools"),
    ("hermes doctor", "vector doctor"),
    ("hermes setup", "vector setup"),
    ("hermes-cli", "vector-cli"),
    ("hermes/openclaw", "vector/openclaw"),
    ("hermes_constants", "vectorcode.src.vc_core.constants"),
    ("hermes_cli", "vectorcode.src.vector_cli"),
    # Method/function names
    ("load_hermes_dotenv", "load_vector_dotenv"),
    ("hermes_home", "vector_home"),
    ("get_vector_home", "get_vector_home"),  # already correct
    # UA strings
    ("hermes-cli", "vector-cli"),
    ("hermes", "vector"),
]

# But we need to be surgical — only in specific files
FILE_SPECIFIC_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "vector_cli/env_loader.py": [
        ("load_hermes_dotenv", "load_vector_dotenv"),
        ("hermes_home", "vector_home"),
        ("hermes_cli.config", "vectorcode.src.vector_cli.config"),
        ("hermes_cli", "vectorcode.src.vector_cli"),
        ("load_hermes_dotenv", "load_vector_dotenv"),
    ],
    "providers/__init__.py": [
        ("from hermes_constants import get_vector_home",
         "from vectorcode.src.vc_core.config import get_vector_home"),
        ("hermes_constants", "vectorcode.src.vc_core.constants"),
    ],
    "providers/base.py": [
        ("from hermes_cli import __version__",
         "try:\\n    from vectorcode.src.vector_cli import __version__ as _ver\\nexcept ImportError:\\n    _ver = '0.0.0'"),
        ("hermes-cli", "vector-cli"),
    ],
    "vector_cli/security_advisories.py": [
        ("from hermes_cli.config import load_config",
         "from vectorcode.src.vector_cli.config import load_config"),
        ("from hermes_constants import get_vector_home",
         "from vectorcode.src.vc_core.config import get_vector_home"),
        ("hermes doctor", "vector doctor"),
    ],
    "agent/web_search_registry.py": [
        ("from hermes_cli.config import load_config",
         "from vectorcode.src.vector_cli.config import load_config"),
    ],
    "agent/web_search_provider.py": [
        ("hermes tools", "vector tools"),
    ],
    "agent/plugin_llm.py": [
        ("from hermes_cli.config import load_config",
         "from vectorcode.src.vector_cli.config import load_config"),
        ("hermes_cli.config", "vectorcode.src.vector_cli.config"),
    ],
    "vector_cli/eval_cmd.py": [
        ("hermes", "vector"),
        ("hermes/openclaw", "vector/openclaw"),
    ],
}


def fix_file(rel_path: str) -> int:
    """Fix hermes refs in a single file. Returns number of changes."""
    fp = ROOT / rel_path
    if not fp.exists():
        return 0
    text = fp.read_text(encoding="utf-8")
    original = text
    replacements = FILE_SPECIFIC_REPLACEMENTS.get(rel_path, [])
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        fp.write_text(text, encoding="utf-8")
        return 1
    return 0


def main() -> int:
    total = 0
    for rel_path in FILES_WITH_IMPORTS:
        n = fix_file(rel_path)
        if n:
            total += 1
            print(f"  Fixed: {rel_path}")
    print(f"\n{total} files updated")
    return 0


if __name__ == "__main__":
    main()
