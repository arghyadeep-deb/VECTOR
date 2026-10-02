"""Regression for vectorcode/src/vector_cli/auth_cmd.py's create_key():

when "[server.auth]" was present in the config but no "api_key = ..." line
matched the update regex (a malformed or hand-edited section), re.sub
silently left the content unchanged -- the new key was never actually
written, but the command still printed "API key generated" / "Stored in"
as if it had been. Fixed to detect the zero-match case and append the
line instead of silently no-op'ing.
"""
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vector_cli import auth_cmd


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(auth_cmd, "DEFAULT_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(auth_cmd, "DEFAULT_CONFIG_PATH", config_path)
    return config_path


def test_create_key_writes_key_when_section_malformed(isolated_config):
    # Section header present, but no api_key line inside it (e.g. empty section).
    isolated_config.write_text("[server.auth]\n")
    runner = CliRunner()
    result = runner.invoke(auth_cmd.create_key, [])
    assert result.exit_code == 0
    content = isolated_config.read_text()
    assert 'api_key = "' in content
    # The printed key must actually be the one persisted.
    import re
    written_key = re.search(r'api_key\s*=\s*"([^"]*)"', content).group(1)
    assert written_key in result.output


def test_create_key_updates_existing_key(isolated_config):
    isolated_config.write_text('[server.auth]\napi_key = "old-key"\n')
    runner = CliRunner()
    result = runner.invoke(auth_cmd.create_key, [])
    assert result.exit_code == 0
    content = isolated_config.read_text()
    assert "old-key" not in content
    assert content.count("api_key") == 1


def test_create_key_creates_new_section(isolated_config):
    runner = CliRunner()
    result = runner.invoke(auth_cmd.create_key, [])
    assert result.exit_code == 0
    content = isolated_config.read_text()
    assert "[server.auth]" in content
    assert 'api_key = "' in content


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
