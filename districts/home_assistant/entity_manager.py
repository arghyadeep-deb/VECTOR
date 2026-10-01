from __future__ import annotations

import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


@dataclass
class HAEntity:
    entity_id: str
    state: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    last_changed: str = ""
    domain: str = ""
    area: Optional[str] = None

    def __post_init__(self):
        if not self.domain and "." in self.entity_id:
            self.domain = self.entity_id.split(".")[0]
        if self.area is None:
            self.area = self.attributes.get("area") or self.attributes.get("area_id")

    @property
    def friendly_name(self) -> str:
        return self.attributes.get("friendly_name", self.entity_id)


class EntityRegistry:
    def __init__(self):
        self._entities: Dict[str, HAEntity] = {}

    def add(self, entity: HAEntity):
        self._entities[entity.entity_id] = entity

    def remove(self, entity_id: str):
        self._entities.pop(entity_id, None)

    def get(self, entity_id: str) -> Optional[HAEntity]:
        return self._entities.get(entity_id)

    def all(self) -> List[HAEntity]:
        return list(self._entities.values())

    def get_by_domain(self, domain: str) -> List[HAEntity]:
        return [e for e in self._entities.values() if e.domain == domain]

    def get_by_area(self, area: str) -> List[HAEntity]:
        area_lower = area.lower()
        return [
            e for e in self._entities.values()
            if (e.area and e.area.lower() == area_lower)
            or (area_lower in e.friendly_name.lower())
        ]

    def clear(self):
        self._entities.clear()

    @property
    def count(self) -> int:
        return len(self._entities)


class EntityCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires = entry
        if time.monotonic() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any):
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()


class EntityMatcher:
    def __init__(self, registry: EntityRegistry):
        self._registry = registry

    def match(self, phrase: str, domain: Optional[str] = None) -> List[Tuple[HAEntity, float]]:
        phrase_lower = phrase.lower().strip()
        results: List[Tuple[HAEntity, float]] = []

        candidates = self._registry.all()
        if domain:
            candidates = [e for e in candidates if e.domain == domain]

        for entity in candidates:
            score = self._score(entity, phrase_lower)
            if score > 0:
                results.append((entity, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _score(self, entity: HAEntity, phrase_lower: str) -> float:
        name_lower = entity.friendly_name.lower()
        entity_id_lower = entity.entity_id.lower()

        if name_lower == phrase_lower or entity_id_lower == phrase_lower:
            return 1.0

        alias = entity.attributes.get("aliases", [])
        if isinstance(alias, str):
            alias = [alias]
        for a in alias:
            if a.lower() == phrase_lower:
                return 0.9

        if entity.area and entity.area.lower() == phrase_lower:
            return 0.7

        if phrase_lower in name_lower or phrase_lower in entity_id_lower:
            base = 0.6
            ratio = SequenceMatcher(None, phrase_lower, name_lower).ratio()
            return base + (ratio * 0.3)

        if entity.domain and entity.domain == phrase_lower:
            return 0.5

        ratio = SequenceMatcher(None, phrase_lower, name_lower).ratio()
        if ratio > 0.6:
            return ratio * 0.5

        return 0.0


class EntityManager:
    def __init__(self):
        self._registry = EntityRegistry()
        self._cache = EntityCache()
        self._matcher = EntityMatcher(self._registry)

    @property
    def registry(self) -> EntityRegistry:
        return self._registry

    @property
    def cache(self) -> EntityCache:
        return self._cache

    @property
    def matcher(self) -> EntityMatcher:
        return self._matcher

    async def discover(self, connector) -> int:
        cached = self._cache.get("all_states")
        if cached:
            return len(cached)
        try:
            states = await connector.rest.get_states()
        except Exception as e:
            logger.error("[HA EntityManager] Discovery failed: {}", e)
            return 0

        for s in states:
            entity = HAEntity(
                entity_id=s.get("entity_id", ""),
                state=s.get("state", ""),
                attributes=s.get("attributes", {}),
                last_changed=s.get("last_changed", ""),
            )
            self._registry.add(entity)

        self._cache.set("all_states", states)
        logger.info("[HA EntityManager] Discovered {} entities", self._registry.count)
        return self._registry.count

    def get_entity(self, entity_id: str) -> Optional[HAEntity]:
        return self._registry.get(entity_id)

    def get_by_domain(self, domain: str) -> List[HAEntity]:
        return self._registry.get_by_domain(domain)

    def get_by_area(self, area: str) -> List[HAEntity]:
        return self._registry.get_by_area(area)

    def handle_state_change(self, entity_id: str, state: str, attributes: Optional[Dict[str, Any]] = None):
        existing = self._registry.get(entity_id)
        if existing:
            existing.state = state
            if attributes:
                existing.attributes.update(attributes)
        else:
            entity = HAEntity(entity_id=entity_id, state=state, attributes=attributes or {})
            self._registry.add(entity)
        self._cache.invalidate("all_states")
