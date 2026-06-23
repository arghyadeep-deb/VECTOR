"""
Closes docs/repo_analysis/_MASTER_TODO.md §3 item 12 -- a missing
core.research_engine.web package broke several real import chains
(ssrf_validator's NAT64 settings lookup, settings/manager.py,
content_fetcher.fetcher.ContentFetcher, research_library.services.
download_service). Confirmed via `ls core/research_engine/web` returning
nothing before this fix.

Root cause was two-fold:
1. settings/manager.py needed `..web.models.settings`'s 5 setting-category
   classes (BaseSetting/AppSetting/LLMSetting/SearchSetting/ReportSetting)
   -- plain dataclasses, not Flask-coupled. Rebuilt clean-room from the
   real usage contract in settings/manager.py::create_or_update_setting()
   (field-for-field match against database/models/settings.py::Setting,
   the real SQLAlchemy model) -- not copied from any original source,
   which doesn't exist in this checkout.
2. research_library/__init__.py unconditionally imported 4 Flask
   blueprints (library_bp/rag_bp/delete_bp/search_bp) needing
   `..web.auth.decorators` -- a parallel Flask web app VECTOR never needed
   (it has its own FastAPI app + HUD). Guarded, not rebuilt.

A third, unrelated, smaller gap found along the way: faiss was imported
unconditionally in library_rag_service.py despite never being declared in
requirements.txt/pyproject.toml -- guarded the same way as pdfplumber
earlier this session.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_web_models_settings_importable():
    from core.research_engine.web.models.settings import (
        BaseSetting, AppSetting, LLMSetting, SearchSetting, ReportSetting,
    )
    assert BaseSetting is not None


def test_setting_classes_default_name_to_key():
    from core.research_engine.web.models.settings import LLMSetting

    setting = LLMSetting(key="llm.model")
    assert setting.name == "llm.model"
    assert setting.value is None
    assert setting.visible is True
    assert setting.editable is True


def test_setting_classes_have_correct_type_default():
    from core.research_engine.web.models.settings import (
        AppSetting, LLMSetting, SearchSetting, ReportSetting,
    )
    from core.research_engine.database.models.settings import SettingType

    assert AppSetting(key="x").type == SettingType.APP
    assert LLMSetting(key="x").type == SettingType.LLM
    assert SearchSetting(key="x").type == SettingType.SEARCH
    assert ReportSetting(key="x").type == SettingType.REPORT


def test_setting_classes_accept_dict_unpacking_construction():
    """Matches settings/manager.py's real construction pattern:
    LLMSetting(**setting) where setting is a plain dict."""
    from core.research_engine.web.models.settings import LLMSetting

    raw = {"key": "llm.temperature", "value": 0.7, "category": "model"}
    setting = LLMSetting(**raw)
    assert setting.key == "llm.temperature"
    assert setting.value == 0.7
    assert setting.category == "model"


def test_settings_manager_module_importable():
    """The original live-crashing call site (ssrf_validator's NAT64 lookup)
    and every other settings/manager.py importer depend on this."""
    from core.research_engine.settings.manager import SettingsManager
    assert SettingsManager is not None


def test_research_library_package_importable_with_flask_blueprints_none():
    """The 4 Flask blueprints are guarded -- they import as None rather
    than crashing the whole package, since VECTOR never needed the
    parallel Flask web app they belonged to."""
    import core.research_engine.research_library as research_library

    assert research_library.DownloadService is not None
    assert research_library.LibraryService is not None
    assert research_library.LibraryRAGService is not None
    # library_bp etc. are either the real Flask blueprint (if Flask happens
    # to be installed and web.auth existed, which it doesn't) or None --
    # either way, importing the package must not raise.
    assert research_library.library_bp is None


def test_content_fetcher_importable_end_to_end():
    """The actual target this whole fix was for -- confirmed broken via
    direct import attempts earlier this session, now fixed."""
    from core.research_engine.content_fetcher.fetcher import ContentFetcher
    assert ContentFetcher is not None


def test_library_rag_service_faiss_guard_raises_clean_error_when_unavailable():
    from core.research_engine.research_library.services.library_rag_service import (
        LibraryRAGService, _FAISS_AVAILABLE,
    )
    if _FAISS_AVAILABLE:
        import pytest
        pytest.skip("faiss is installed in this environment -- guard path not exercised")

    service = LibraryRAGService.__new__(LibraryRAGService)
    try:
        service.load_or_create_faiss_index("fake-collection-id")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "faiss" in str(exc).lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
