"""
VECTOR Browser Auth Profiles — absorbed from auto-browser-main (2026-05-27).

Standalone named Playwright storage-state profile store.
Login once → save → reuse across sessions without re-authenticating.

Storage layout (under CONFIG["browser"]["auth_profiles_dir"]):
  {root}/
    {profile_name}/
      state.json      — Playwright storage state (cookies + localStorage)
      profile.json    — metadata (last_saved_at, url, title, …)

Playwright integration (caller's responsibility):
    state = await page.context.storage_state()       # → dict
    store = get_auth_store()
    store.save("github", state)                      # → saves to disk
    ...
    state = store.load("github")                     # → dict
    context = await browser.new_context(storage_state=state)

Replaces: nothing (VECTOR had no named auth profile system).
Reuses:   core/config.py CONFIG["browser"]["auth_profiles_dir"].
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from core.config import CONFIG
from loguru import logger

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
UTC = timezone.utc


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class BrowserAuthStore:
    """
    File-backed named browser auth profile store.
    Thread-safe for reads; caller must avoid concurrent writes to the same profile.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        cfg = CONFIG.get("browser", {})
        default_root = Path(cfg.get("auth_profiles_dir", str(Path.home() / ".vector" / "browser_auth")))
        self._root: Path = Path(root) if root else default_root

    # ── Public API ──────────────────────────────────────────────────────────

    def save(self, profile_name: str, state: dict[str, Any] | str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Persist a Playwright storage state under profile_name.

        state: dict from `await context.storage_state()` or its JSON string.
        Returns summary dict.
        """
        name = self.normalize_name(profile_name)
        profile_dir = self._profile_dir(name, create=True)

        state_data = state if isinstance(state, str) else json.dumps(state, indent=2)
        state_path = self._resolve_path(profile_dir, "state.json")
        state_path.write_text(state_data, encoding="utf-8")

        meta: dict[str, Any] = {
            "profile_name": name,
            "last_saved_at": _utc_now(),
        }
        if metadata:
            meta.update(metadata)
        meta_path = self._resolve_path(profile_dir, "profile.json")
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

        logger.info("[VECTOR][auth_profiles] saved profile '{}' → {}", name, state_path)
        return {"profile_name": name, "saved_to": str(state_path), "metadata": meta}

    def load(self, profile_name: str) -> dict[str, Any]:
        """
        Load a Playwright storage state dict by profile name.
        Raises KeyError if the profile does not exist.
        """
        name = self.normalize_name(profile_name)
        state_path = self._state_path(name)
        if not state_path.exists():
            raise KeyError(f"auth profile '{name}' not found")
        data = json.loads(state_path.read_text(encoding="utf-8"))
        logger.info("[VECTOR][auth_profiles] loaded profile '{}'", name)
        return data

    def get(self, profile_name: str) -> dict[str, Any]:
        """Return metadata + state-exists flag for a named profile."""
        name = self.normalize_name(profile_name)
        state_path = self._state_path(name)
        meta = self._read_metadata(name)
        if not state_path.exists() and not meta:
            raise KeyError(name)
        return {
            "profile_name": name,
            "state_exists": state_path.exists(),
            "metadata": meta,
        }

    def list(self) -> list[dict[str, Any]]:
        """List all profiles, sorted by last_saved_at descending."""
        if not self._root.exists():
            return []
        profiles: list[dict[str, Any]] = []
        for item in sorted(self._root.iterdir(), key=lambda p: p.name.lower()):
            if not item.is_dir():
                continue
            try:
                profiles.append(self.get(item.name))
            except (KeyError, ValueError):
                continue
        profiles.sort(
            key=lambda p: (p.get("metadata") or {}).get("last_saved_at", ""),
            reverse=True,
        )
        return profiles

    def delete(self, profile_name: str) -> bool:
        """Delete a profile. Returns True if deleted, False if not found."""
        name = self.normalize_name(profile_name)
        profile_dir = self._profile_dir(name, create=False)
        if not profile_dir.exists():
            return False
        shutil.rmtree(str(profile_dir))
        logger.info("[VECTOR][auth_profiles] deleted profile '{}'", name)
        return True

    def export(self, profile_name: str) -> dict[str, Any]:
        """Export a profile as a tar.gz archive in the same root directory."""
        name = self.normalize_name(profile_name)
        profile_dir = self._profile_dir(name, create=False)
        if not profile_dir.exists():
            raise FileNotFoundError(f"auth profile '{name}' not found")
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"{name}-{ts}.tar.gz"
        archive_path = self._resolve_path(self._root, archive_name)
        with tarfile.open(str(archive_path), "w:gz") as tar:
            tar.add(str(profile_dir), arcname=name)
        logger.info("[VECTOR][auth_profiles] exported '{}' → {}", name, archive_path)
        return {"profile_name": name, "archive_path": str(archive_path), "archive_name": archive_name}

    def import_profile(self, archive_name: str, *, overwrite: bool = False) -> dict[str, Any]:
        """Import a profile from a tar.gz archive located in the root directory."""
        safe_name = PurePosixPath(archive_name.replace("\\", "/")).name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.tar\.gz", safe_name):
            raise ValueError("archive name is invalid")
        src = self._resolve_path(self._root, safe_name)
        if not src.exists():
            raise FileNotFoundError(f"archive not found: {safe_name}")

        with tarfile.open(str(src), "r:gz") as tar:
            members = tar.getmembers()
            if not members:
                raise ValueError("archive is empty")
            safe_members: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
            top_level: str | None = None
            for member in members:
                if member.issym() or member.islnk() or member.isdev():
                    raise ValueError("archive contains unsafe member type")
                if not (member.isdir() or member.isfile()):
                    continue
                safe_path = self._safe_archive_member(member.name)
                if len(safe_path.parts) == 1 and not member.isdir():
                    raise ValueError("archive must contain a top-level profile directory")
                top = safe_path.parts[0]
                if top_level is None:
                    top_level = top
                elif top != top_level:
                    raise ValueError("archive must contain a single top-level profile directory")
                safe_members.append((member, safe_path))
            if top_level is None:
                raise ValueError("archive contains no importable files")

            profile_name = self.normalize_name(top_level)
            dest_dir = self._resolve_path(self._root, profile_name)
            if dest_dir.exists() and not overwrite:
                raise FileExistsError(f"profile '{profile_name}' already exists; pass overwrite=True")
            if dest_dir.exists():
                shutil.rmtree(str(dest_dir))
            for member, safe_path in safe_members:
                relative = Path(*safe_path.parts)
                target = self._resolve_path(self._root, relative)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                src_file = tar.extractfile(member)
                if src_file is None:
                    raise ValueError("archive member could not be read")
                with src_file, target.open("wb") as out:
                    shutil.copyfileobj(src_file, out)

        logger.info("[VECTOR][auth_profiles] imported profile '{}'", profile_name)
        return {"profile_name": profile_name, "profile_path": str(self._root / profile_name), "imported": True}

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def normalize_name(profile_name: str) -> str:
        name = profile_name.strip()
        if not name:
            raise ValueError("auth profile name is required")
        if not _NAME_RE.fullmatch(name):
            raise ValueError("auth profile names may contain letters, numbers, dots, underscores, and hyphens (max 120 chars)")
        return name

    def _profile_dir(self, name: str, *, create: bool) -> Path:
        root = self._root
        path = self._resolve_path(root, name)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _state_path(self, name: str) -> Path:
        return self._resolve_path(self._profile_dir(name, create=False), "state.json")

    def _read_metadata(self, name: str) -> dict[str, Any]:
        meta_path = self._resolve_path(self._profile_dir(name, create=False), "profile.json")
        if not meta_path.exists():
            return {}
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _resolve_path(self, root: Path, relative: str | Path) -> Path:
        root_real = os.path.realpath(os.fspath(root))
        candidate = os.path.realpath(os.path.join(root_real, os.fspath(relative)))
        root_prefix = root_real if root_real.endswith(os.sep) else root_real + os.sep
        if candidate != root_real and not candidate.startswith(root_prefix):
            raise PermissionError("path must stay inside auth profile root")
        return Path(candidate)

    @staticmethod
    def _safe_archive_member(member_name: str) -> PurePosixPath:
        candidate = PurePosixPath(member_name.replace("\\", "/"))
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("archive contains an unsafe path")
        return candidate


_store_singleton: BrowserAuthStore | None = None


def get_auth_store() -> BrowserAuthStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = BrowserAuthStore()
    return _store_singleton


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = BrowserAuthStore(root=tmp)

        # save / load round-trip
        state = {"cookies": [{"name": "session", "value": "abc123"}], "origins": []}
        store.save("github", state, metadata={"url": "https://github.com"})
        loaded = store.load("github")
        assert loaded["cookies"][0]["value"] == "abc123"

        # list
        profiles = store.list()
        assert any(p["profile_name"] == "github" for p in profiles)

        # duplicate save (overwrite)
        store.save("github", {"cookies": [], "origins": []})
        loaded2 = store.load("github")
        assert loaded2["cookies"] == []

        # missing raises KeyError
        try:
            store.load("nonexistent")
            assert False, "Should have raised KeyError"
        except KeyError:
            pass

        # invalid name raises ValueError
        try:
            store.normalize_name("../evil")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

        # path traversal raises PermissionError
        try:
            store._resolve_path(Path(tmp), "../outside")
            assert False, "Should have raised PermissionError"
        except PermissionError:
            pass

        # delete
        store.delete("github")
        assert store.list() == []

        print("OK - auth_profiles.py")
