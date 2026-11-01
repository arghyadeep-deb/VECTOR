"""
Base storage interfaces for the news system.
"""

from abc import ABC, abstractmethod

__all__ = [
    "BaseStorage",
    "CardStorage",
    "PreferenceStorage",
    "RatingStorage",
    "SubscriptionStorage",
]

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


class BaseStorage(ABC):
    """Abstract base class for all storage interfaces"""

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> str:
        """Create a new record and return its ID"""
        raise NotImplementedError("BaseStorage.create must be implemented by subclass")

    @abstractmethod
    def get(self, id: str) -> Optional[Dict[str, Any]]:
        """Get a record by ID"""
        raise NotImplementedError("BaseStorage.get must be implemented by subclass")

    @abstractmethod
    def update(self, id: str, data: Dict[str, Any]) -> bool:
        """Update a record, return True if successful"""
        raise NotImplementedError("BaseStorage.update must be implemented by subclass")

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Delete a record, return True if successful"""
        raise NotImplementedError("BaseStorage.delete must be implemented by subclass")

    @abstractmethod
    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List records with optional filtering"""
        raise NotImplementedError("BaseStorage.list must be implemented by subclass")

    def generate_id(self) -> str:
        """Generate a unique ID"""
        return str(uuid.uuid4())


class CardStorage(BaseStorage):
    """Interface for news card storage"""

    @abstractmethod
    def get_by_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get cards for a specific user"""
        raise NotImplementedError("CardStorage.get_by_user must be implemented by subclass")

    @abstractmethod
    def get_latest_version(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of a card"""
        raise NotImplementedError("CardStorage.get_latest_version must be implemented by subclass")

    @abstractmethod
    def add_version(self, card_id: str, version_data: Dict[str, Any]) -> str:
        """Add a new version to a card"""
        raise NotImplementedError("CardStorage.add_version must be implemented by subclass")

    @abstractmethod
    def update_latest_info(
        self, card_id: str, version_data: Dict[str, Any]
    ) -> bool:
        """Update the denormalized latest version info on the card"""
        raise NotImplementedError("CardStorage.update_latest_info must be implemented by subclass")

    @abstractmethod
    def archive_card(self, card_id: str) -> bool:
        """Archive a card"""
        raise NotImplementedError("CardStorage.archive_card must be implemented by subclass")

    @abstractmethod
    def pin_card(self, card_id: str, pinned: bool = True) -> bool:
        """Pin or unpin a card"""
        raise NotImplementedError("CardStorage.pin_card must be implemented by subclass")


class SubscriptionStorage(BaseStorage):
    """Interface for subscription storage"""

    @abstractmethod
    def get_active_subscriptions(
        self, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all active subscriptions, optionally filtered by user"""
        raise NotImplementedError("SubscriptionStorage.get_active_subscriptions must be implemented by subclass")

    @abstractmethod
    def get_due_subscriptions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get subscriptions that are due for refresh"""
        raise NotImplementedError("SubscriptionStorage.get_due_subscriptions must be implemented by subclass")

    @abstractmethod
    def update_refresh_time(
        self,
        subscription_id: str,
        last_refresh: datetime,
        next_refresh: datetime,
    ) -> bool:
        """Update refresh timestamps after processing"""
        raise NotImplementedError("SubscriptionStorage.update_refresh_time must be implemented by subclass")

    @abstractmethod
    def increment_stats(self, subscription_id: str, results_count: int) -> bool:
        """Increment refresh count and update results count"""
        raise NotImplementedError("SubscriptionStorage.increment_stats must be implemented by subclass")

    @abstractmethod
    def pause_subscription(self, subscription_id: str) -> bool:
        """Pause a subscription"""
        raise NotImplementedError("SubscriptionStorage.pause_subscription must be implemented by subclass")

    @abstractmethod
    def resume_subscription(self, subscription_id: str) -> bool:
        """Resume a paused subscription"""
        raise NotImplementedError("SubscriptionStorage.resume_subscription must be implemented by subclass")

    @abstractmethod
    def expire_subscription(self, subscription_id: str) -> bool:
        """Mark a subscription as expired"""
        raise NotImplementedError("SubscriptionStorage.expire_subscription must be implemented by subclass")


class RatingStorage(BaseStorage):
    """Interface for rating storage"""

    @abstractmethod
    def get_user_rating(
        self, user_id: str, item_id: str, rating_type: str
    ) -> Optional[Dict[str, Any]]:
        """Get a user's rating for a specific item"""
        raise NotImplementedError("RatingStorage.get_user_rating must be implemented by subclass")

    @abstractmethod
    def upsert_rating(
        self,
        user_id: str,
        item_id: str,
        rating_type: str,
        rating_value: str,
        item_type: str = "card",
    ) -> str:
        """Create or update a rating"""
        raise NotImplementedError("RatingStorage.upsert_rating must be implemented by subclass")

    @abstractmethod
    def get_ratings_summary(
        self, item_id: str, item_type: str = "card"
    ) -> Dict[str, Any]:
        """Get aggregated ratings for an item"""
        raise NotImplementedError("RatingStorage.get_ratings_summary must be implemented by subclass")

    @abstractmethod
    def get_user_ratings(
        self, user_id: str, rating_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all ratings by a user"""
        raise NotImplementedError("RatingStorage.get_user_ratings must be implemented by subclass")


class PreferenceStorage(BaseStorage):
    """Interface for user preference storage"""

    @abstractmethod
    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get preferences for a user"""
        raise NotImplementedError("PreferenceStorage.get_user_preferences must be implemented by subclass")

    @abstractmethod
    def upsert_preferences(
        self, user_id: str, preferences: Dict[str, Any]
    ) -> str:
        """Create or update user preferences"""
        raise NotImplementedError("PreferenceStorage.upsert_preferences must be implemented by subclass")

    @abstractmethod
    def add_liked_item(
        self, user_id: str, item_id: str, item_type: str = "news"
    ) -> bool:
        """Add an item to liked list"""
        raise NotImplementedError("PreferenceStorage.add_liked_item must be implemented by subclass")

    @abstractmethod
    def add_disliked_item(
        self, user_id: str, item_id: str, item_type: str = "news"
    ) -> bool:
        """Add an item to disliked list"""
        raise NotImplementedError("PreferenceStorage.add_disliked_item must be implemented by subclass")

    @abstractmethod
    def update_preference_embedding(
        self, user_id: str, embedding: List[float]
    ) -> bool:
        """Update the user's preference embedding"""
        raise NotImplementedError("PreferenceStorage.update_preference_embedding must be implemented by subclass")
