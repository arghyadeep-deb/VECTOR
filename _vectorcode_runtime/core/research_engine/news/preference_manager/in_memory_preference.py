from typing import Dict, Any, Optional

from loguru import logger

from .base_preference import BasePreferenceManager


class InMemoryPreferenceManager(BasePreferenceManager):
    """In-memory implementation of BasePreferenceManager.

    Stores user preferences in a dict. Useful for development, testing,
    and single-user deployments without a database.
    """

    def __init__(self, storage_backend: Optional[Any] = None):
        super().__init__(storage_backend)
        self._store: Dict[str, Dict[str, Any]] = {}

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        if user_id not in self._store:
            self._store[user_id] = self.get_default_preferences()
            logger.info("Created default preferences for user {}", user_id)
        return dict(self._store[user_id])

    def update_preferences(self, user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
        self._store[user_id] = preferences
        return dict(self._store[user_id])


__all__ = ["InMemoryPreferenceManager"]
