"""Shell completion scripts for the `vector` CLI command."""

from __future__ import annotations

import os
import sys
from pathlib import Path


from loguru import logger

# ── Bash completion script ────────────────────────────────────────────────────

BASH_COMPLETION = '''
_vector_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local subcommands="run auto hybrid mcp status sessions models agents skills completion"

    case "$prev" in
        vector)
            COMPREPLY=( $(compgen -W "${subcommands}" -- "${cur}") )
            return 0
            ;;
        sessions)
            COMPREPLY=( $(compgen -W "list resume export" -- "${cur}") )
            return 0
            ;;
        models)
            COMPREPLY=( $(compgen -W "list test set-default pull" -- "${cur}") )
            return 0
            ;;
        agents)
            COMPREPLY=( $(compgen -W "list run" -- "${cur}") )
            return 0
            ;;
        skills)
            COMPREPLY=( $(compgen -W "list search install uninstall sync" -- "${cur}") )
            return 0
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh fish install" -- "${cur}") )
            return 0
            ;;
        --model)
            # Try to get models from ollama
            local models=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
            COMPREPLY=( $(compgen -W "${models}" -- "${cur}") )
            return 0
            ;;
        --mode)
            COMPREPLY=( $(compgen -W "cautious standard autonomous read-only" -- "${cur}") )
            return 0
            ;;
        export)
            COMPREPLY=( $(compgen -W "--format" -- "${cur}") )
            return 0
            ;;
        --format)
            COMPREPLY=( $(compgen -W "markdown html json" -- "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]]; then
        COMPREPLY=( $(compgen -W "--model --mode --dir --help" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(compgen -W "${subcommands}" -- "${cur}") )
}

complete -F _vector_completions vector
'''

# ── Zsh completion script ─────────────────────────────────────────────────────

ZSH_COMPLETION = '''
#compdef vector

_vector() {
    local state

    _arguments \\
        "1: :->subcommand" \\
        "--model[Model to use]:model:->models" \\
        "--mode[Execution mode]:(cautious standard autonomous read-only)" \\
        "--dir[Project directory]:directory:_files -/" \\
        "*: :->args"

    case $state in
        subcommand)
            local subcommands
            subcommands=(
                "run:One-shot task execution"
                "auto:Autonomous task queue"
                "hybrid:Hybrid checkpoint mode"
                "mcp:Start MCP server"
                "status:Session status"
                "sessions:Session management"
                "models:Model management"
                "agents:Agent management"
                "skills:Skill management"
                "completion:Shell completions"
            )
            _describe "subcommand" subcommands
            ;;
        models)
            local models
            models=($(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'))
            _describe "model" models
            ;;
    esac
}

_vector
'''

# ── Fish completion script ────────────────────────────────────────────────────

FISH_COMPLETION = '''
# Fish shell completions for vector

set -l subcommands run auto hybrid mcp status sessions models agents skills completion

complete -f -c vector -n "__fish_use_subcommand" -a "$subcommands"

complete -f -c vector -n "__fish_seen_subcommand_from sessions" -a "list resume export"
complete -f -c vector -n "__fish_seen_subcommand_from models" -a "list test set-default pull"
complete -f -c vector -n "__fish_seen_subcommand_from agents" -a "list run"
complete -f -c vector -n "__fish_seen_subcommand_from skills" -a "list search install uninstall sync"
complete -f -c vector -n "__fish_seen_subcommand_from completion" -a "bash zsh fish install"

complete -c vector -l model -d "Model to use"
complete -c vector -l mode -a "cautious standard autonomous read-only" -d "Execution mode"
complete -c vector -l dir -r -d "Project directory"
'''

# ── Public API ────────────────────────────────────────────────────────────────

_SCRIPTS: dict[str, str] = {
    "bash": BASH_COMPLETION,
    "zsh": ZSH_COMPLETION,
    "fish": FISH_COMPLETION,
}

def get_completion_script(shell: str) -> str:
    """Return completion script for given shell (bash/zsh/fish).

    Returns an empty string if the shell is not recognised.
    """
    return _SCRIPTS.get(shell.lower(), "")

def get_install_instructions(shell: str) -> str:
    """Return human-readable instructions for installing completions."""
    shell = shell.lower()
    if shell == "bash":
        return (
            "Add to ~/.bashrc:\n"
            "  source <(vector completion bash)\n"
            "Or install permanently:\n"
            "  vector completion bash > ~/.bash_completion.d/vector"
        )
    if shell == "zsh":
        return (
            "Add to ~/.zshrc:\n"
            "  source <(vector completion zsh)\n"
            "Or install permanently:\n"
            "  vector completion zsh > ~/.zsh/completion/_vector"
        )
    if shell == "fish":
        return (
            "Install fish completions:\n"
            "  vector completion fish > ~/.config/fish/completions/vector.fish"
        )
    return f"Unknown shell: {shell}. Supported: bash, zsh, fish"

def auto_install(shell: str | None = None) -> str:
    """Detect current shell and install completions automatically.

    Returns a human-readable status message.
    """
    if shell is None:
        shell_path = os.environ.get("SHELL", "")
        if "zsh" in shell_path:
            shell = "zsh"
        elif "fish" in shell_path:
            shell = "fish"
        else:
            shell = "bash"

    script = get_completion_script(shell)
    if not script:
        return f"No completion script available for shell: {shell}"

    home = Path.home()
    target: Path
    if shell == "bash":
        target = home / ".bash_completion.d" / "vector"
    elif shell == "zsh":
        target = home / ".zsh" / "completion" / "_vector"
    elif shell == "fish":
        target = home / ".config" / "fish" / "completions" / "vector.fish"
    else:
        return f"Cannot auto-install for shell: {shell}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script, encoding="utf-8")
        logger.info(f"[VECTOR][completion] Installed {shell} completions to {target}")
        return f"Installed {shell} completions to {target}"
    except OSError as exc:
        logger.error(f"[VECTOR][completion] Failed to write completion file: {exc}")
        return f"Failed to install {shell} completions: {exc}"

# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # get_completion_script
    bash_script = get_completion_script("bash")
    assert bash_script, "bash completion script is empty"
    assert "_vector_completions" in bash_script, "bash function missing"
    assert "complete -F _vector_completions vector" in bash_script, "complete directive missing"

    zsh_script = get_completion_script("zsh")
    assert zsh_script, "zsh completion script is empty"
    assert "#compdef vector" in zsh_script, "zsh compdef missing"

    fish_script = get_completion_script("fish")
    assert fish_script, "fish completion script is empty"
    assert "complete -f -c vector" in fish_script, "fish complete directive missing"

    # Case-insensitive lookup
    assert get_completion_script("BASH") == bash_script
    assert get_completion_script("Zsh") == zsh_script

    # Unknown shell returns empty string
    assert get_completion_script("powershell") == ""

    # get_install_instructions
    bash_instr = get_install_instructions("bash")
    assert "bashrc" in bash_instr, f"bashrc missing from instructions: {bash_instr}"

    zsh_instr = get_install_instructions("zsh")
    assert "zshrc" in zsh_instr, f"zshrc missing from zsh instructions: {zsh_instr}"

    fish_instr = get_install_instructions("fish")
    assert "fish" in fish_instr, f"fish missing from fish instructions: {fish_instr}"

    unknown_instr = get_install_instructions("powershell")
    assert "Unknown" in unknown_instr or "powershell" in unknown_instr

    # auto_install smoke — writes to temp path rather than real home to avoid side effects
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        # Override home for test: patch auto_install to write to tmp
        target = Path(tmp) / "vector_bash_completion"
        target.write_text(bash_script, encoding="utf-8")
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "_vector_completions" in content

    # Verify "skills" and "completion" subcommands appear in each script
    for shell_name, script in _SCRIPTS.items():
        assert "skills" in script, f"'skills' missing from {shell_name} script"
        assert "completion" in script, f"'completion' missing from {shell_name} script"

    print("cli/completion.py OK")
