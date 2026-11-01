"""Voice profile store for the VECTOR voice pipeline.

Python reimplementation of voicebox's profiles service (backend/services/profiles.py):
stores named voice profiles (cloned / preset / designed) with per-profile effect chains,
engine selection, personality hints, and a default flag. Metadata persists via VECTOR's
Collections Engine; reference audio samples persist via FileStorage — both absorbed from
PocketBase. Falls back to a lightweight in-memory store when the collections engine is
unavailable so the voice pipeline never fails to import.
"""

from __future__ import annotations

import sys
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


from loguru import logger
from core.config import CONFIG

__all__ = [
    "ProfileType",
    "VoiceProfile",
    "VoiceProfileStore",
    "get_profile_store",
]


class ProfileType(str, Enum):
    CLONED = "cloned"       # zero-shot local clone from a reference clip
    PRESET = "preset"       # fixed voice id (ElevenLabs CONTENT_VOICES or Kokoro)
    DESIGNED = "designed"   # no reference; generated purely via engine + effects


@dataclass
class VoiceProfile:
    name: str
    type: ProfileType = ProfileType.PRESET
    engine: str = "kokoro"                  # kokoro | piper | pyttsx3 | elevenlabs | chatterbox
    reference_key: str = ""                 # FileStorage key for the reference .wav clip (cloned only)
    voice_id: str = ""                      # Kokoro voice name or ElevenLabs voice_id
    effects: list[dict] = field(default_factory=list)   # chain for AudioEffects.apply()
    personality: str = ""                   # short hint injected into context before speaking
    is_default: bool = False
    metadata: dict = field(default_factory=dict)        # arbitrary extra metadata

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["effects"] = json.dumps(self.effects)         # store as JSON string in collection
        d["metadata"] = json.dumps(self.metadata)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "VoiceProfile":
        d = dict(d)
        d["type"] = ProfileType(d.get("type", ProfileType.PRESET.value))
        raw_effects = d.get("effects", "[]")
        d["effects"] = json.loads(raw_effects) if isinstance(raw_effects, str) else (raw_effects or [])
        raw_meta = d.get("metadata", "{}")
        d["metadata"] = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Collection schema definition ──────────────────────────────────────────────

_COLLECTION_NAME = "voice_profiles"

_PROFILE_FIELDS = [
    {"name": "name",          "type": "text",   "required": True},
    {"name": "type",          "type": "text",   "required": True},
    {"name": "engine",        "type": "text",   "required": False},
    {"name": "reference_key", "type": "text",   "required": False},
    {"name": "voice_id",      "type": "text",   "required": False},
    {"name": "effects",       "type": "json",   "required": False},
    {"name": "personality",   "type": "text",   "required": False},
    {"name": "is_default",    "type": "bool",   "required": False},
    {"name": "metadata",      "type": "json",   "required": False},
]


# ── Fallback in-memory store (used when collections engine unavailable) ────────

class _InMemoryStore:
    """Minimal dict-backed store — no persistence, never crashes."""
    def __init__(self):
        self._data: dict[str, dict] = {}

    def create(self, payload: dict) -> dict:
        name = payload["name"]
        self._data[name] = dict(payload)
        return self._data[name]

    def get_by_name(self, name: str) -> dict | None:
        return self._data.get(name)

    def list_all(self) -> list[dict]:
        return list(self._data.values())

    def update(self, name: str, payload: dict) -> dict:
        if name not in self._data:
            raise KeyError(name)
        self._data[name].update(payload)
        return self._data[name]

    def delete(self, name: str) -> None:
        self._data.pop(name, None)


# ── Main store ────────────────────────────────────────────────────────────────

class VoiceProfileStore:
    """
    Persist and retrieve VoiceProfiles. Uses the Collections Engine + FileStorage
    when available; falls back to in-memory so the voice pipeline never fails.

    Usage::

        store = VoiceProfileStore()
        store.create(VoiceProfile(name="myvoice", type=ProfileType.CLONED, engine="chatterbox"))
        profile = store.get("myvoice")
        store.set_default("myvoice")
        store.upload_reference("myvoice", audio_bytes, "ref.wav")
    """

    def __init__(
        self,
        engine=None,          # CollectionEngine instance (optional — injected or auto-discovered)
        storage=None,         # FileStorage instance (optional)
    ):
        self._engine = engine
        self._storage = storage
        self._mem = _InMemoryStore()    # fallback
        self._collection_ready = False
        self._storage_ready = False
        self._bootstrap()

    # ── init ──────────────────────────────────────────────────────────────────

    def _bootstrap(self):
        self._bootstrap_engine()
        self._bootstrap_storage()

    def _bootstrap_engine(self):
        if self._engine is not None:
            self._ensure_collection(self._engine)
            return
        try:
            from core.collections import CollectionEngine
            self._engine = CollectionEngine()
            self._ensure_collection(self._engine)
        except Exception as e:
            logger.warning(
                "[VECTOR][voice] collections engine unavailable — profiles stored in-memory: {}", e
            )

    def _ensure_collection(self, engine):
        try:
            from core.collections import Collection
            col = engine.get_collection(_COLLECTION_NAME)
            if col is None:
                engine.create_collection(Collection(name=_COLLECTION_NAME, fields=_PROFILE_FIELDS))
                logger.info("[VECTOR][voice] created voice_profiles collection")
            self._collection_ready = True
        except Exception as e:
            logger.warning("[VECTOR][voice] could not ensure voice_profiles collection: {}", e)

    def _bootstrap_storage(self):
        if self._storage is not None:
            self._storage_ready = True
            return
        try:
            from core.collections import FileStorage, LocalDriver
            cfg = CONFIG.get("collections", {}) or {}
            storage_cfg = cfg.get("storage", {}) or {}
            base = Path(storage_cfg.get("base_path", "./data/storage")) / "voice_refs"
            # FileStorage needs a StorageDriver, not a path string (was the bug)
            self._storage = FileStorage(LocalDriver(base))
            self._storage_ready = True
            logger.info("[VECTOR][voice] reference sample storage ready at {}", base)
        except Exception as e:
            logger.warning("[VECTOR][voice] FileStorage unavailable — reference samples stored as path only: {}", e)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, profile: VoiceProfile) -> VoiceProfile:
        """Persist a new profile. Raises ValueError if name already exists."""
        if self.get(profile.name) is not None:
            raise ValueError(f"Voice profile {profile.name!r} already exists")
        payload = profile.to_dict()
        if self._collection_ready and self._engine is not None:
            try:
                self._engine.create_record(_COLLECTION_NAME, payload)
                logger.info("[VECTOR][voice] profile created: {}", profile.name)
                return profile
            except Exception as e:
                logger.warning("[VECTOR][voice] collection create failed, using in-memory: {}", e)
        self._mem.create(payload)
        logger.info("[VECTOR][voice] profile created (in-memory): {}", profile.name)
        return profile

    def get(self, name: str) -> VoiceProfile | None:
        """Return a profile by name, or None if not found."""
        if self._collection_ready and self._engine is not None:
            try:
                result = self._engine.list_records(
                    _COLLECTION_NAME, filter=f"name='{name}'", per_page=1
                )
                items = result.get("items", [])
                if items:
                    return VoiceProfile.from_dict(items[0])
                return None
            except Exception as e:
                logger.debug("[VECTOR][voice] collection get failed, checking in-memory: {}", e)
        raw = self._mem.get_by_name(name)
        return VoiceProfile.from_dict(raw) if raw else None

    def list_all(self) -> list[VoiceProfile]:
        """Return all stored profiles."""
        if self._collection_ready and self._engine is not None:
            try:
                result = self._engine.list_records(_COLLECTION_NAME, per_page=200)
                return [VoiceProfile.from_dict(r) for r in result.get("items", [])]
            except Exception as e:
                logger.debug("[VECTOR][voice] collection list failed, using in-memory: {}", e)
        return [VoiceProfile.from_dict(r) for r in self._mem.list_all()]

    def update(self, name: str, **kwargs) -> VoiceProfile:
        """Update fields on an existing profile."""
        profile = self.get(name)
        if profile is None:
            raise KeyError(f"Voice profile {name!r} not found")
        for k, v in kwargs.items():
            if hasattr(profile, k):
                setattr(profile, k, v)
        payload = profile.to_dict()
        if self._collection_ready and self._engine is not None:
            try:
                result = self._engine.list_records(
                    _COLLECTION_NAME, filter=f"name='{name}'", per_page=1
                )
                items = result.get("items", [])
                if items:
                    rec_id = items[0].get("id")
                    if rec_id:
                        self._engine.update_record(_COLLECTION_NAME, rec_id, payload)
                        return profile
            except Exception as e:
                logger.debug("[VECTOR][voice] collection update failed, falling through: {}", e)
        self._mem.update(name, payload)
        return profile

    def delete(self, name: str) -> None:
        """Remove a profile and its reference sample if any."""
        profile = self.get(name)
        if profile is not None and profile.reference_key and self._storage_ready:
            try:
                self._storage.delete(profile.reference_key)
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
        if self._collection_ready and self._engine is not None:
            try:
                result = self._engine.list_records(
                    _COLLECTION_NAME, filter=f"name='{name}'", per_page=1
                )
                items = result.get("items", [])
                if items:
                    rec_id = items[0].get("id")
                    if rec_id:
                        self._engine.delete_record(_COLLECTION_NAME, rec_id)
                        logger.info("[VECTOR][voice] profile deleted: {}", name)
                        return
            except Exception as e:
                logger.debug("[VECTOR][voice] collection delete failed, using in-memory: {}", e)
        self._mem.delete(name)

    # ── default management ────────────────────────────────────────────────────

    def get_default(self) -> VoiceProfile | None:
        """Return the profile marked is_default=True, or None."""
        for p in self.list_all():
            if p.is_default:
                return p
        return None

    def set_default(self, name: str) -> VoiceProfile:
        """Mark profile `name` as default; clears is_default on all others."""
        profiles = self.list_all()
        for p in profiles:
            if p.is_default and p.name != name:
                try:
                    self.update(p.name, is_default=False)
                except Exception:
                    logger.warning("[VECTOR] silent swallow")
                    pass
        return self.update(name, is_default=True)

    # ── reference sample storage ──────────────────────────────────────────────

    def upload_reference(self, name: str, audio_bytes: bytes, filename: str = "reference.wav") -> str:
        """
        Store a reference audio clip for a cloned profile. Returns the storage key.
        The profile's reference_key field is updated automatically.
        """
        if not self._storage_ready or self._storage is None:
            logger.warning("[VECTOR][voice] FileStorage unavailable — reference sample not saved")
            return ""
        key = f"voice_profiles/{name}/{filename}"
        self._storage.put(key, audio_bytes, content_type="audio/wav")
        self.update(name, reference_key=key)
        logger.info("[VECTOR][voice] reference sample stored: {}", key)
        return key

    def get_reference_bytes(self, name: str) -> bytes | None:
        """Return the raw bytes of the reference clip, or None."""
        profile = self.get(name)
        if profile is None or not profile.reference_key:
            return None
        if not self._storage_ready or self._storage is None:
            return None
        try:
            return self._storage.get(profile.reference_key)
        except Exception as e:
            logger.warning("[VECTOR][voice] could not retrieve reference sample: {}", e)
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: VoiceProfileStore | None = None


def get_profile_store() -> VoiceProfileStore:
    global _store
    if _store is None:
        _store = VoiceProfileStore()
    return _store


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sqlite3 as _sqlite3
    sys.stdout.reconfigure(encoding="utf-8")

    # Use a fresh in-memory CollectionEngine so no persistent DB state leaks
    from core.collections import CollectionEngine as _CE
    _conn = _sqlite3.connect(":memory:", check_same_thread=False)
    store = VoiceProfileStore(engine=_CE(conn=_conn), storage=None)

    # create
    p = VoiceProfile(
        name="test_profile",
        type=ProfileType.CLONED,
        engine="chatterbox",
        voice_id="",
        effects=[{"type": "gain", "params": {"db": 3.0}}],
        personality="calm and focused",
    )
    store.create(p)
    assert store.get("test_profile") is not None

    # duplicate raises
    try:
        store.create(p)
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass

    # list
    all_p = store.list_all()
    assert len(all_p) == 1

    # create second, set default
    store.create(VoiceProfile(name="preset_voice", type=ProfileType.PRESET, engine="kokoro", voice_id="bf_emma"))
    store.set_default("preset_voice")
    assert store.get_default().name == "preset_voice"

    # changing default moves the flag
    store.create(VoiceProfile(name="designed_voice", type=ProfileType.DESIGNED, engine="pyttsx3"))
    store.set_default("designed_voice")
    assert store.get_default().name == "designed_voice"
    assert store.get("preset_voice").is_default is False

    # update
    store.update("test_profile", personality="energetic")
    assert store.get("test_profile").personality == "energetic"

    # delete
    store.delete("test_profile")
    assert store.get("test_profile") is None
    assert len(store.list_all()) == 2

    # effects round-trip through from_dict/to_dict
    p2 = VoiceProfile(name="fx_test", effects=[{"type": "reverb", "params": {"room_size": 0.7}}])
    d = p2.to_dict()
    p2b = VoiceProfile.from_dict(d)
    assert p2b.effects == [{"type": "reverb", "params": {"room_size": 0.7}}], p2b.effects

    print("✅ voice_profiles.py OK")