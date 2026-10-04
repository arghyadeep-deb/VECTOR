"""Skills hub -- install, sync, search, and uninstall skill packs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


from loguru import logger

# ── SkillPack dataclass ───────────────────────────────────────────────────────

@dataclass
class SkillPack:
    name: str
    source: str              # git URL or local path
    install_path: Path
    installed_at: str = ""
    version: str = ""
    skill_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "install_path": str(self.install_path),
            "installed_at": self.installed_at,
            "version": self.version,
            "skill_count": self.skill_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillPack":
        return cls(
            name=data["name"],
            source=data.get("source", ""),
            install_path=Path(data["install_path"]),
            installed_at=data.get("installed_at", ""),
            version=data.get("version", ""),
            skill_count=int(data.get("skill_count", 0)),
        )

# ── SkillsHub ─────────────────────────────────────────────────────────────────

class SkillsHub:
    """
    Manages skill packs: install from git/local, sync (git pull),
    search by keyword, list, uninstall.

    Registry stored at ~/.vector/skills_registry.json.
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".vector" / "skills"
        self.base_dir: Path = base_dir
        self.registry_path: Path = base_dir.parent / "skills_registry.json"
        self._packs: Dict[str, SkillPack] = {}
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    # ── Public API ─────────────────────────────────────────────────────────

    def install(self, source: str, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Install a skill pack.

        - If source starts with "http" or "git@": clone with subprocess git clone.
        - If source is a local path: symlink or copy to base_dir/name/.
        - Counts .md files found, registers in registry.

        Returns {"name": name, "skill_count": N, "path": str(install_path), "success": True}
        """
        # Derive pack name from source if not given
        if not name:
            name = self._derive_name(source)

        install_path = self.base_dir / name

        if install_path.exists():
            logger.warning(f"[VECTOR][skills_hub] Pack '{name}' already installed at {install_path}. Re-installing.")
            shutil.rmtree(install_path, ignore_errors=True)

        is_remote = source.startswith("http") or source.startswith("git@")

        if is_remote:
            logger.info(f"[VECTOR][skills_hub] Cloning {source} -> {install_path}")
            self._git_clone(source, install_path)
        else:
            local_path = Path(source).expanduser().resolve()
            if not local_path.exists():
                raise FileNotFoundError(f"Local skill source not found: {local_path}")
            # Try symlink first; fall back to copy (Windows may need elevated perms)
            try:
                install_path.symlink_to(local_path)
                logger.info(f"[VECTOR][skills_hub] Symlinked {local_path} -> {install_path}")
            except (OSError, NotImplementedError):
                shutil.copytree(str(local_path), str(install_path))
                logger.info(f"[VECTOR][skills_hub] Copied {local_path} -> {install_path}")

        skill_count = self._count_skills(install_path)
        version = self._get_git_version(install_path)
        installed_at = datetime.now(timezone.utc).isoformat()

        pack = SkillPack(
            name=name,
            source=source,
            install_path=install_path,
            installed_at=installed_at,
            version=version,
            skill_count=skill_count,
        )
        self._packs[name] = pack
        self._save_registry()

        logger.info(f"[VECTOR][skills_hub] Installed '{name}': {skill_count} skills")
        return {
            "name": name,
            "skill_count": skill_count,
            "path": str(install_path),
            "success": True,
        }

    def uninstall(self, name: str) -> Dict[str, Any]:
        """Remove skill pack directory and registry entry."""
        if name not in self._packs:
            logger.warning(f"[VECTOR][skills_hub] Pack '{name}' not found in registry")
            return {"success": False, "error": f"Pack '{name}' not installed"}

        pack = self._packs[name]
        if pack.install_path.exists():
            # Remove symlink or directory
            if pack.install_path.is_symlink():
                pack.install_path.unlink()
            else:
                shutil.rmtree(pack.install_path, ignore_errors=True)
            logger.info(f"[VECTOR][skills_hub] Removed {pack.install_path}")
        else:
            logger.warning(f"[VECTOR][skills_hub] Install path missing: {pack.install_path}")

        del self._packs[name]
        self._save_registry()
        return {"success": True, "removed": name}

    def sync(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Git pull on installed pack(s).
        If name is None, sync all.
        Returns {"synced": [pack_names], "errors": [...]}.
        """
        targets: List[SkillPack]
        if name is not None:
            if name not in self._packs:
                return {"synced": [], "errors": [f"Pack '{name}' not installed"]}
            targets = [self._packs[name]]
        else:
            targets = list(self._packs.values())

        synced: List[str] = []
        errors: List[str] = []

        for pack in targets:
            if not pack.install_path.exists():
                errors.append(f"{pack.name}: install path missing")
                continue
            if pack.install_path.is_symlink():
                logger.info(f"[VECTOR][skills_hub] Skipping sync for symlinked pack '{pack.name}'")
                synced.append(pack.name)  # treat as already in sync
                continue
            try:
                result = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=str(pack.install_path),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    pack.version = self._get_git_version(pack.install_path)
                    pack.skill_count = self._count_skills(pack.install_path)
                    self._packs[pack.name] = pack
                    synced.append(pack.name)
                    logger.info(f"[VECTOR][skills_hub] Synced '{pack.name}'")
                else:
                    err_msg = result.stderr.strip() or result.stdout.strip()
                    errors.append(f"{pack.name}: {err_msg}")
                    logger.warning(f"[VECTOR][skills_hub] Sync failed for '{pack.name}': {err_msg}")
            except subprocess.TimeoutExpired:
                errors.append(f"{pack.name}: git pull timed out")
                logger.warning(f"[VECTOR][skills_hub] Sync timed out for '{pack.name}'")
            except FileNotFoundError:
                errors.append(f"{pack.name}: git not found in PATH")
                logger.warning(f"[VECTOR][skills_hub] git not available for sync")

        if synced:
            self._save_registry()

        return {"synced": synced, "errors": errors}

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search skill files across all installed packs.
        Reads frontmatter from SKILL.md files looking for 'name' and 'description' fields.
        Returns list of {"pack": name, "skill": skill_name, "description": ..., "path": ...}
        """
        keywords = [kw.lower() for kw in re.split(r"\W+", query) if len(kw) > 1]
        if not keywords:
            return self.list_skills()

        results: List[Dict[str, Any]] = []
        for pack in self._packs.values():
            if not pack.install_path.exists():
                continue
            for skill_info in self._iter_skills(pack):
                haystack = (
                    skill_info.get("skill", "") + " " + skill_info.get("description", "")
                ).lower()
                if any(kw in haystack for kw in keywords):
                    results.append(skill_info)

        return results

    def list_packs(self) -> List[SkillPack]:
        """Return all installed packs."""
        return list(self._packs.values())

    def list_skills(self, pack_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all skills across all packs (or a specific pack)."""
        packs: List[SkillPack]
        if pack_name is not None:
            if pack_name not in self._packs:
                logger.warning(f"[VECTOR][skills_hub] Pack '{pack_name}' not found")
                return []
            packs = [self._packs[pack_name]]
        else:
            packs = list(self._packs.values())

        results: List[Dict[str, Any]] = []
        for pack in packs:
            if not pack.install_path.exists():
                continue
            results.extend(self._iter_skills(pack))

        return results

    # ── Private helpers ────────────────────────────────────────────────────

    def _save_registry(self) -> None:
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            data = {name: pack.to_dict() for name, pack in self._packs.items()}
            self.registry_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug(f"[VECTOR][skills_hub] Registry saved: {len(self._packs)} packs")
        except Exception as exc:
            logger.error(f"[VECTOR][skills_hub] Failed to save registry: {exc}")

    def _load_registry(self) -> None:
        if not self.registry_path.exists():
            self._packs = {}
            return
        try:
            raw = self.registry_path.read_text(encoding="utf-8")
            data: Dict[str, Any] = json.loads(raw)
            self._packs = {name: SkillPack.from_dict(info) for name, info in data.items()}
            logger.debug(f"[VECTOR][skills_hub] Registry loaded: {len(self._packs)} packs")
        except Exception as exc:
            logger.warning(f"[VECTOR][skills_hub] Could not load registry: {exc}")
            self._packs = {}

    def _count_skills(self, pack_dir: Path) -> int:
        """Count .md files recursively in directory."""
        if not pack_dir.exists():
            return 0
        count = 0
        for root, _dirs, files in os.walk(pack_dir):
            for f in files:
                if f.lower().endswith(".md"):
                    count += 1
        return count

    @staticmethod
    def _derive_name(source: str) -> str:
        """Derive a pack name from a git URL or local path."""
        # Strip trailing slashes and .git suffix
        name = source.rstrip("/").rstrip("\\")
        if name.endswith(".git"):
            name = name[:-4]
        name = Path(name).name
        # Sanitize: keep alphanumerics, hyphens, underscores
        name = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")
        return name or "unknown-pack"

    @staticmethod
    def _git_clone(url: str, dest: Path) -> None:
        """Clone a git repo to dest. Raises on failure."""
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", url, str(dest)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(f"git clone failed: {err}")
        except FileNotFoundError as exc:
            raise RuntimeError("git not found in PATH -- cannot clone remote pack") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"git clone timed out for {url}") from exc

    @staticmethod
    def _get_git_version(pack_dir: Path) -> str:
        """Return short git SHA or empty string if not a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(pack_dir),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as _sve:
            logger.debug("[VECTOR][skills.hub] suppressed Exception: {}", _sve)
        return ""

    @staticmethod
    def _parse_frontmatter_simple(content: str) -> Dict[str, Any]:
        """
        Parse YAML frontmatter with simple regex -- no external yaml dependency.
        Handles: name, description, triggers fields.
        """
        fm: Dict[str, Any] = {}
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return fm
        block = match.group(1)
        for line in block.split("\n"):
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                fm[key] = value
        return fm

    def _iter_skills(self, pack: SkillPack) -> List[Dict[str, Any]]:
        """Walk a pack directory and return skill metadata dicts."""
        skills: List[Dict[str, Any]] = []
        if not pack.install_path.exists():
            return skills
        for root, _dirs, files in os.walk(pack.install_path):
            for fname in files:
                if not fname.lower().endswith(".md"):
                    continue
                fpath = Path(root) / fname
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    fm = self._parse_frontmatter_simple(content)
                    skill_name = fm.get("name") or fpath.stem
                    description = fm.get("description", "")
                    triggers_raw = fm.get("triggers", "")
                    triggers = (
                        [t.strip().strip("\"'") for t in triggers_raw.strip("[]").split(",")]
                        if triggers_raw
                        else []
                    )
                    skills.append(
                        {
                            "pack": pack.name,
                            "skill": skill_name,
                            "description": description,
                            "triggers": triggers,
                            "path": str(fpath),
                        }
                    )
                except Exception as exc:
                    logger.debug(f"[VECTOR][skills_hub] Could not read {fpath}: {exc}")
        return skills

# ── Singleton ─────────────────────────────────────────────────────────────────

_hub_instance: Optional[SkillsHub] = None

def get_skills_hub() -> SkillsHub:
    """Return the process-level singleton SkillsHub."""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = SkillsHub()
    return _hub_instance

# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        hub = SkillsHub(base_dir=Path(tmp) / "skills")

        # list_packs -- empty
        packs = hub.list_packs()
        assert packs == [], f"Expected empty packs, got {packs}"

        # list_skills -- empty, should not crash
        skills = hub.list_skills()
        assert skills == [], f"Expected empty skills, got {skills}"

        # search -- empty
        results = hub.search("memory")
        assert results == [], f"Expected empty search results, got {results}"

        # Install from a local directory with a SKILL.md file
        local_pack = Path(tmp) / "my_test_pack"
        local_pack.mkdir()
        skill_md = local_pack / "SKILL.md"
        skill_md.write_text(
            "---\nname: test-skill\ndescription: A unit test skill\ntriggers: [test, unit]\n---\n# Test Skill\nDoes testing.",
            encoding="utf-8",
        )
        readme = local_pack / "README.md"
        readme.write_text("# My Test Pack", encoding="utf-8")

        result = hub.install(str(local_pack), name="test-pack")
        assert result["success"] is True, f"Install failed: {result}"
        assert result["name"] == "test-pack"
        assert result["skill_count"] == 2  # SKILL.md + README.md

        # list_packs after install
        packs = hub.list_packs()
        assert len(packs) == 1, f"Expected 1 pack, got {packs}"
        assert packs[0].name == "test-pack"

        # list_skills after install
        skills = hub.list_skills()
        assert len(skills) > 0, "Expected skills after install"
        assert any(s["skill"] == "test-skill" for s in skills), f"test-skill not found: {skills}"

        # search
        results = hub.search("unit test")
        assert any(r["skill"] == "test-skill" for r in results), f"Search failed: {results}"

        # sync -- a copied (non-git) directory is fine: it will appear in errors
        # (not a git repo), but the call must not raise an exception
        sync_result = hub.sync("test-pack")
        assert isinstance(sync_result, dict), f"sync returned non-dict: {sync_result}"
        assert "synced" in sync_result and "errors" in sync_result, f"Unexpected sync keys: {sync_result}"
        # non-git copy goes to errors, which is acceptable
        assert (
            "test-pack" in sync_result["synced"] or
            any("test-pack" in e for e in sync_result["errors"])
        ), f"test-pack not accounted for in sync result: {sync_result}"

        # uninstall
        uninstall_result = hub.uninstall("test-pack")
        assert uninstall_result["success"] is True, f"Uninstall failed: {uninstall_result}"
        assert len(hub.list_packs()) == 0

        # _derive_name tests
        assert SkillsHub._derive_name("https://github.com/user/my-pack.git") == "my-pack"
        assert SkillsHub._derive_name("/local/path/to/skills") == "skills"
        assert SkillsHub._derive_name("git@github.com:org/pack-name.git") == "pack-name"

        # get_skills_hub singleton
        hub1 = get_skills_hub()
        hub2 = get_skills_hub()
        assert hub1 is hub2, "Singleton broken"

    print("skills/hub.py OK")
