"""Regression for vectorcode/src/agent/lsp/cli.py's _cmd_which().

_recipe_pkg_for() maps a handful of registry server_ids to a DIFFERENT
INSTALL_RECIPES key (e.g. "astro-language-server" -> "@astrojs/language-server",
"dockerfile-ls" -> "dockerfile-language-server-nodejs", "typescript" ->
"typescript-language-server"). Every other subcommand (_cmd_status, _cmd_list,
_cmd_install, _cmd_install_all) looks up the recipe through this alias map.
_cmd_which() did not -- it called INSTALL_RECIPES.get(server_id) directly with
the raw, un-aliased server_id, which misses the recipe entirely for these
servers and falls back to using the server_id itself as the binary name.

That binary name is wrong (astro-language-server's real installed binary is
"astro-ls", not "astro-language-server"), so `vector lsp which <server_id>`
queried the wrong name and reported "not installed" even when the server was
correctly installed under its real binary name.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from agent.lsp import cli as lsp_cli


def _which_queried_name(server_id: str, tmp_path) -> str | None:
    """Run _cmd_which with staging-dir/PATH lookups mocked out, and return
    the binary name it actually queried shutil.which with (or None if it
    found a staged binary before reaching that call)."""
    calls: list[str] = []

    def fake_which(name):
        calls.append(name)
        return None

    with patch("agent.lsp.install.vector_lsp_bin_dir", return_value=tmp_path), \
         patch("shutil.which", side_effect=fake_which):
        lsp_cli._cmd_which(server_id)
    return calls[0] if calls else None


def test_which_resolves_astro_alias_to_real_binary_name(tmp_path):
    assert _which_queried_name("astro-language-server", tmp_path) == "astro-ls"


def test_which_resolves_dockerfile_ls_alias_to_real_binary_name(tmp_path):
    assert _which_queried_name("dockerfile-ls", tmp_path) == "docker-langserver"


def test_which_resolves_typescript_alias_to_real_binary_name(tmp_path):
    assert _which_queried_name("typescript", tmp_path) == "typescript-language-server"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
