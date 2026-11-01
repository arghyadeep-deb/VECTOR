"""Clean-room rebuild of the missing core.research_engine.web.models.settings
module (docs/repo_analysis/_MASTER_TODO.md §3 item 12).

This was a real, separate structural gap, not a Flask UI dependency: the
absorbed research_engine subsystem references `..web.models.settings` from
`settings/manager.py`, but no `web` package ever existed in this checkout.
The rest of `..web.*` (auth, themes, socket service, PDF export) belongs to
a parallel Flask web app VECTOR never needed (it has its own FastAPI app +
HUD) and is deliberately NOT rebuilt here.

These 5 classes are plain settings-category schemas, not Flask-coupled --
confirmed by reading every real usage in settings/manager.py::create_or_update_setting():
only `.key`/`.value`/`.type`/`.name`/`.description`/`.category`/`.ui_element`/
`.options`/`.min_value`/`.max_value`/`.step`/`.visible`/`.editable` are ever
read, mirroring core/research_engine/database/models/settings.py::Setting
(the real SQLAlchemy model) field-for-field. Built from that usage contract,
not copied from any original source (which doesn't exist in this checkout).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.research_engine.database.models.settings import SettingType

__all__ = ["BaseSetting", "AppSetting", "LLMSetting", "ReportSetting", "SearchSetting"]


@dataclass
class BaseSetting:
    key: str
    value: Any = None
    type: SettingType = SettingType.APP
    name: str = ""
    description: Optional[str] = None
    category: Optional[str] = None
    ui_element: str = "text"
    options: Optional[list] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    visible: bool = True
    editable: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.key


@dataclass
class AppSetting(BaseSetting):
    type: SettingType = SettingType.APP


@dataclass
class LLMSetting(BaseSetting):
    type: SettingType = SettingType.LLM


@dataclass
class SearchSetting(BaseSetting):
    type: SettingType = SettingType.SEARCH


@dataclass
class ReportSetting(BaseSetting):
    type: SettingType = SettingType.REPORT
