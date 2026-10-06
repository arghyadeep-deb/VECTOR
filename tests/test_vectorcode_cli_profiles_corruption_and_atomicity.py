"""Regression for vectorcode/src/cli/profiles.py:

_load() caught any JSON parse failure on profiles.json and silently kept
only the built-in profiles in memory -- indistinguishable from "no custom
profiles exist yet". The next call to _save() (e.g. creating any new
profile) would then overwrite the corrupted file with just the built-ins
plus whatever was created, permanently destroying every other previously
saved custom profile. Same "fail-open destroys data" bug class already
fixed in vectorcode/src/cli/auth.py this cycle.

Also: _save() wrote directly to the final path with no atomicity, so a
crash mid-write could itself produce exactly the corrupted file this fix
now protects against.
"""
from __future__ import annotations

import json

import pytest

from vectorcode.src.cli import profiles as profiles_mod


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    profiles_path = tmp_path / "profiles.json"
    active_path = tmp_path / "active_profile.txt"
    monkeypatch.setattr(profiles_mod.ProfileManager, "PROFILES_PATH", profiles_path)
    monkeypatch.setattr(profiles_mod.ProfileManager, "ACTIVE_PATH", active_path)
    monkeypatch.setattr(profiles_mod, "_profile_manager_instance", None)
    yield profiles_path, active_path
    monkeypatch.setattr(profiles_mod, "_profile_manager_instance", None)


def test_corrupted_profiles_file_raises_instead_of_silently_emptying(isolated_paths):
    profiles_path, _ = isolated_paths
    profiles_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(profiles_mod.ProfilesCorruptedError):
        profiles_mod.ProfileManager()


def test_create_does_not_destroy_existing_custom_profiles_on_corrupted_load(
    isolated_paths, capsys
):
    profiles_path, _ = isolated_paths
    # Simulate a real custom profile that was saved previously, now corrupted.
    profiles_path.write_text("not json at all {{{", encoding="utf-8")

    class _Args:
        profile_action = "create"
        name = "newone"
        mode = None
        toolset = None
        model = None
        project_dir = None
        persona = None
        description = None
        extra_env = None

    profiles_mod.handle_profile(_Args())

    # The corrupted file must be left untouched -- not silently overwritten
    # with just the newly "created" profile.
    assert profiles_path.read_text(encoding="utf-8") == "not json at all {{{"
    out = capsys.readouterr().out
    assert "could not be parsed" in out


def test_save_is_atomic_and_leaves_no_tmp_file_on_success(isolated_paths):
    profiles_path, _ = isolated_paths
    mgr = profiles_mod.ProfileManager()
    mgr.create("realprofile", mode="cautious", toolset="coding", description="x")

    saved = json.loads(profiles_path.read_text(encoding="utf-8"))
    assert "realprofile" in saved["profiles"]
    assert list(profiles_path.parent.glob(".profiles.json.*.tmp")) == []
