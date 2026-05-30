
import pytest


@pytest.fixture
def tmp_vault(tmp_path):
    for folder in ["Daily", "Reflections", "00 Notes", "01 Journals"]:
        (tmp_path / folder).mkdir()
    return tmp_path


def test_write_note_creates_file(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync
    sync = ObsidianSync(vault_path=tmp_vault)
    path = sync.write_note("Test Note", "Hello VECTOR", "Daily", ["test"])
    assert path.exists()
    assert "Hello VECTOR" in path.read_text(encoding="utf-8")


def test_write_note_has_frontmatter(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync
    sync = ObsidianSync(vault_path=tmp_vault)
    path = sync.write_note("FM Test", "body text", "Daily", ["tag1"])
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---")
    assert "source: vector" in content
    assert "tag1" in content


def test_write_note_atomic_no_tmp(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync
    sync = ObsidianSync(vault_path=tmp_vault)
    sync.write_note("Atomic", "content", "Daily", [])
    tmp_files = list(tmp_vault.glob("**/*.tmp"))
    assert tmp_files == []


def test_append_to_note_grows_file(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync
    sync = ObsidianSync(vault_path=tmp_vault)
    sync.write_note("Append Test", "initial", "Reflections", [])
    sync.append_to_note("Append Test", "appended block", "Reflections")
    content = (tmp_vault / "Reflections" / "Append Test.md").read_text(encoding="utf-8")
    assert "initial" in content
    assert "appended block" in content


def test_write_note_personal_folder_raises_without_gateway(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync, PermissionDeniedError
    sync = ObsidianSync(vault_path=tmp_vault)
    with pytest.raises(PermissionDeniedError):
        sync.write_note("Journal", "text", "01 Journals", [], _bypass_gateway=False)


def test_write_note_personal_folder_allowed_with_flag(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync
    sync = ObsidianSync(vault_path=tmp_vault)
    path = sync.write_note("Journal", "text", "01 Journals", [], _bypass_gateway=True)
    assert path.exists()


def test_write_note_protected_path_always_raises(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync, PermissionDeniedError
    sync = ObsidianSync(vault_path=tmp_vault)
    (tmp_vault / "CLAUDE.md").write_text("protected")
    with pytest.raises(PermissionDeniedError):
        sync.write_note("CLAUDE", "evil content", ".", [], _bypass_gateway=True)


def test_write_note_overwrite_existing_personal_raises(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync, PermissionDeniedError
    sync = ObsidianSync(vault_path=tmp_vault)
    sync.write_note("Note", "v1", "00 Notes", [], _bypass_gateway=True)
    with pytest.raises(PermissionDeniedError):
        sync.write_note("Note", "v2", "00 Notes", [], overwrite=True, _bypass_gateway=False)


def test_is_protected_path(tmp_vault):
    from core.memory.obsidian_sync import ObsidianSync
    sync = ObsidianSync(vault_path=tmp_vault)
    assert sync._is_protected(tmp_vault / "CLAUDE.md")
    assert sync._is_protected(tmp_vault / "VECTOR" / "arch.md")
    assert not sync._is_protected(tmp_vault / "Daily" / "note.md")


def test_get_vault_context_returns_string():
    import asyncio
    from core.loop.context_engine import ContextEngine
    ce = ContextEngine()
    result = asyncio.run(ce.get_vault_context("VECTOR goals"))
    assert isinstance(result, str)  # returns "" gracefully if LightRAG not ready
