"""Named profiles — switch between different VectorCode configurations."""
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

import json
import datetime
import os
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Optional


from loguru import logger
from pathlib import Path

@dataclass
class Profile:
    name: str
    model: str = "ollama/vector-focus"
    mode: str = "standard"            # cautious | standard | autonomous | read-only
    project_dir: str = "."
    toolset: str = "full"
    persona: str = "default"
    extra_env: dict = field(default_factory=dict)
    description: str = ""

# ── Built-in profiles (cannot be deleted) ───────────────────────────────────

DEFAULT_PROFILES: dict[str, Profile] = {
    "default": Profile(
        name="default",
        description="General-purpose default profile",
    ),
    "work": Profile(
        name="work",
        mode="cautious",
        toolset="coding",
        persona="professional",
        description="Cautious mode for work codebases",
    ),
    "research": Profile(
        name="research",
        mode="autonomous",
        toolset="research",
        persona="brief",
        description="Autonomous research mode",
    ),
    "readonly": Profile(
        name="readonly",
        mode="read-only",
        toolset="readonly",
        persona="default",
        description="Read-only — no writes or shell execution",
    ),
}

_BUILTIN_NAMES = frozenset(DEFAULT_PROFILES.keys())

_VALID_MODES = frozenset({"cautious", "standard", "autonomous", "read-only"})
_VALID_TOOLSETS = frozenset({"full", "coding", "research", "readonly"})

_profile_manager_instance: Optional["ProfileManager"] = None


class ProfilesCorruptedError(Exception):
    """profiles.json exists but could not be parsed. Distinct from
    "no custom profiles yet" -- treating a corrupted file as empty would
    make _save() silently overwrite it with just the built-ins on the very
    next write, permanently destroying every custom profile."""

class ProfileManager:
    """
    Manages named VectorCode profiles.
    Custom profiles are persisted to ~/.vector/profiles.json.
    Built-in profiles (default, work, research, readonly) cannot be deleted.
    """

    PROFILES_PATH = Path.home() / ".vector" / "profiles.json"
    ACTIVE_PATH   = Path.home() / ".vector" / "active_profile.txt"

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = dict(DEFAULT_PROFILES)
        self._active: str = "default"
        self._load()

    # ── Persistence ─────────────────────────────────────────────

    def _load(self) -> None:
        """Load custom profiles and active marker from disk.

        Raises ProfilesCorruptedError if profiles.json exists but isn't
        valid JSON -- silently proceeding with just the built-ins would
        make _save() overwrite the corrupted file with "no custom
        profiles" on the very next write.
        """
        if self.PROFILES_PATH.exists():
            try:
                raw = json.loads(self.PROFILES_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                raise ProfilesCorruptedError(
                    f"{self.PROFILES_PATH} exists but could not be parsed: {e}. "
                    "Refusing to treat this as an empty profile store to avoid "
                    "overwriting existing custom profiles."
                ) from e
            for name, data in raw.get("profiles", {}).items():
                if name not in _BUILTIN_NAMES:
                    self._profiles[name] = Profile(**{
                        k: v for k, v in data.items()
                        if k in Profile.__dataclass_fields__
                    })

        if self.ACTIVE_PATH.exists():
            try:
                active = self.ACTIVE_PATH.read_text(encoding="utf-8").strip()
                if active in self._profiles:
                    self._active = active
            except Exception as _sve:
                logger.debug("[VECTOR][cli.profiles] suppressed Exception: {}", _sve)

    def _save(self) -> None:
        """Durably persist custom profiles (not built-ins) to disk."""
        self.PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
        custom = {
            name: asdict(p)
            for name, p in self._profiles.items()
            if name not in _BUILTIN_NAMES
        }
        payload = {
            "profiles": custom,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.PROFILES_PATH.parent),
            prefix=f".{self.PROFILES_PATH.name}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.PROFILES_PATH)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        logger.debug(f"[VECTOR][profiles] Saved {len(custom)} custom profile(s)")

    def _save_active(self) -> None:
        """Persist active profile name to disk."""
        self.ACTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.ACTIVE_PATH.write_text(self._active, encoding="utf-8")

    # ── Public API ───────────────────────────────────────────────

    def create(self, name: str, **kwargs) -> Profile:
        """Create and save a new custom profile."""
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid profile name: {name!r}. Use alphanumeric + hyphens/underscores.")

        mode = kwargs.get("mode", "standard")
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode: {mode!r}. Choose from: {sorted(_VALID_MODES)}")

        toolset = kwargs.get("toolset", "full")
        if toolset not in _VALID_TOOLSETS:
            raise ValueError(f"Invalid toolset: {toolset!r}. Choose from: {sorted(_VALID_TOOLSETS)}")

        profile = Profile(name=name, **{
            k: v for k, v in kwargs.items()
            if k in Profile.__dataclass_fields__ and k != "name"
        })
        self._profiles[name] = profile
        self._save()
        logger.info(f"[VECTOR][profiles] Created profile '{name}'")
        return profile

    def delete(self, name: str) -> dict:
        """Delete a profile. Cannot delete built-in profiles."""
        if name in _BUILTIN_NAMES:
            return {"deleted": False, "error": f"Cannot delete built-in profile '{name}'"}
        if name not in self._profiles:
            return {"deleted": False, "error": f"Profile not found: '{name}'"}
        if self._active == name:
            self._active = "default"
            self._save_active()
        del self._profiles[name]
        self._save()
        logger.info(f"[VECTOR][profiles] Deleted profile '{name}'")
        return {"deleted": True, "name": name}

    def use(self, name: str) -> Profile:
        """Activate a profile by name. Returns the activated profile."""
        if name not in self._profiles:
            raise KeyError(f"Profile not found: '{name}'")
        self._active = name
        self._save_active()
        logger.info(f"[VECTOR][profiles] Activated profile '{name}'")
        return self._profiles[name]

    def current(self) -> Profile:
        """Return the currently active profile."""
        return self._profiles.get(self._active, self._profiles["default"])

    def list_profiles(self) -> list[Profile]:
        """Return all profiles (built-ins first, then custom alphabetically)."""
        builtin_order = [p for name in ("default", "work", "research", "readonly")
                         if (p := self._profiles.get(name))]
        custom = sorted(
            [p for name, p in self._profiles.items() if name not in _BUILTIN_NAMES],
            key=lambda p: p.name,
        )
        return builtin_order + custom

    def show(self, name: Optional[str] = None) -> dict:
        """Return full profile details as a dict. Defaults to active profile."""
        target = name or self._active
        if target not in self._profiles:
            raise KeyError(f"Profile not found: '{target}'")
        p = self._profiles[target]
        result = asdict(p)
        result["active"] = (target == self._active)
        result["builtin"] = (target in _BUILTIN_NAMES)
        return result

    def get(self, name: str) -> Optional[Profile]:
        """Return a profile by name or None."""
        return self._profiles.get(name)

def get_profile_manager() -> "ProfileManager":
    """Return singleton ProfileManager."""
    global _profile_manager_instance
    if _profile_manager_instance is None:
        _profile_manager_instance = ProfileManager()
    return _profile_manager_instance

# ── CLI helpers ──────────────────────────────────────────────────────────────

def _print_profiles_table(profiles: list[Profile], active_name: str) -> None:
    print(f"{'Name':<22}  {'Mode':<12}  {'Toolset':<10}  {'Model':<32}  Description")
    print("-" * 100)
    for p in profiles:
        marker = "▶" if p.name == active_name else " "
        builtin = " (built-in)" if p.name in _BUILTIN_NAMES else ""
        desc = p.description + builtin
        print(f"  {marker} {p.name:<20}  {p.mode:<12}  {p.toolset:<10}  {p.model:<32}  {desc}")

def handle_profile(args) -> None:
    """Dispatch profile subcommands from argparse args."""
    try:
        _handle_profile(args)
    except ProfilesCorruptedError as e:
        print(f"[VECTOR] {e}")
        print(f"[VECTOR] Inspect or restore {ProfileManager.PROFILES_PATH} manually before retrying.")


def _handle_profile(args) -> None:
    mgr = get_profile_manager()
    action = getattr(args, "profile_action", None)

    if action == "list":
        profiles = mgr.list_profiles()
        _print_profiles_table(profiles, mgr._active)

    elif action == "use":
        try:
            p = mgr.use(args.name)
            print(f"Active profile: {p.name}  (mode={p.mode}, model={p.model})")
        except KeyError as e:
            print(f"[VECTOR] {e}")

    elif action == "show":
        name = getattr(args, "name", None)
        try:
            details = mgr.show(name)
            for k, v in details.items():
                if k == "extra_env":
                    if v:
                        print(f"  extra_env:")
                        for ek, ev in v.items():
                            print(f"    {ek}={ev}")
                    continue
                print(f"  {k:<14}: {v}")
        except KeyError as e:
            print(f"[VECTOR] {e}")

    elif action == "create":
        name = args.name
        kwargs = {k: v for k, v in vars(args).items()
                  if k in Profile.__dataclass_fields__ and k != "name" and v}
        try:
            p = mgr.create(name, **kwargs)
            print(f"Created profile '{p.name}'.")
        except (ValueError, TypeError) as e:
            print(f"[VECTOR] {e}")

    elif action == "delete":
        result = mgr.delete(args.name)
        if result.get("deleted"):
            print(f"Deleted profile '{args.name}'.")
        else:
            print(f"[VECTOR] {result.get('error', 'Delete failed')}")

    else:
        print("Usage: vector profile <list|use|show|create|delete>")

# ── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mgr = ProfileManager()

    profiles = mgr.list_profiles()
    assert len(profiles) >= 4, f"Expected >= 4 profiles, got {len(profiles)}"

    names = [p.name for p in profiles]
    for builtin in ("default", "work", "research", "readonly"):
        assert builtin in names, f"Missing built-in profile: {builtin}"

    # current() returns default on init
    current = mgr.current()
    assert current.name == "default"

    # create + use + delete round-trip
    p = mgr.create("_smoke_test", mode="cautious", toolset="coding",
                   description="Smoke test profile")
    assert p.name == "_smoke_test"

    activated = mgr.use("_smoke_test")
    assert activated.name == "_smoke_test"
    assert mgr.current().name == "_smoke_test"

    details = mgr.show("_smoke_test")
    assert details["active"] is True
    assert details["builtin"] is False

    # Reset active before deleting
    mgr.use("default")
    result = mgr.delete("_smoke_test")
    assert result["deleted"] is True

    # Cannot delete built-in
    cant_delete = mgr.delete("default")
    assert cant_delete["deleted"] is False

    # show() with no argument returns active profile
    shown = mgr.show()
    assert shown["name"] == "default"

    # Clean up persisted test artefacts
    try:
        mgr.PROFILES_PATH.unlink(missing_ok=True)
        mgr.ACTIVE_PATH.unlink(missing_ok=True)
    except Exception as _sve:
        logger.debug("[VECTOR][cli.profiles] suppressed Exception: {}", _sve)

    print("✅ cli/profiles.py OK")
