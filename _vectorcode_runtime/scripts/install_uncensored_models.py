"""Verify and install VECTOR's isolated uncensored Ollama text aliases.

The command never deletes or overwrites the production ``vector-*`` aliases.
It verifies the sibling model-staging manifest before invoking ``ollama
create`` and uses argument arrays rather than a shell command string.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from loguru import logger


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AssetVerificationError(RuntimeError):
    """Raised when a required staged GGUF is missing or has the wrong digest."""


class InstallerUnavailableError(RuntimeError):
    """Raised when the Ollama CLI is not available for a real install."""


class InstallError(RuntimeError):
    """Raised when Ollama rejects an alias creation command."""


@dataclass(frozen=True)
class RoleSpec:
    role: str
    alias: str
    production_alias: str
    manifest_role: str
    directory: str
    filename: str
    template_name: str


@dataclass(frozen=True)
class InstallResult:
    role: str
    alias: str
    command: list[str]
    modelfile_path: Path
    created: bool


ROLE_SPECS: dict[str, RoleSpec] = {
    "focus": RoleSpec(
        role="focus",
        alias="vector-uncensored-focus",
        production_alias="vector-focus",
        manifest_role="focus",
        directory="gemma4-e4b",
        filename="gemma-4-E4B-it-ultra-uncensored-heretic-Q4_K_M.gguf",
        template_name="vector-uncensored-focus.modelfile",
    ),
    "coder": RoleSpec(
        role="coder",
        alias="vector-uncensored-coder",
        production_alias="vector-coder",
        manifest_role="coder-text-only",
        directory="omnicoder-qwen35-9b",
        filename="OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf",
        template_name="vector-uncensored-coder.modelfile",
    ),
    "reasoning": RoleSpec(
        role="reasoning",
        alias="vector-uncensored-reasoning",
        production_alias="vector-reasoning",
        manifest_role="reasoning-text-only",
        directory="defiant-fable-qwen35-9b",
        filename="Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-Q4_K_M.gguf",
        template_name="vector-uncensored-reasoning.modelfile",
    ),
    "r1": RoleSpec(
        role="r1",
        alias="vector-uncensored-r1",
        production_alias="vector-r1",
        manifest_role="r1",
        directory="deepseek-r1-qwen-14b",
        filename="DeepSeek-R1-Distill-Qwen-14B-abliterated-v2.Q4_K_M.gguf",
        template_name="vector-uncensored-r1.modelfile",
    ),
}


def default_staging_root() -> Path:
    """Locate the shared model-staging directory from either repo layout."""
    candidates = (
        PROJECT_ROOT.parent / "model-staging" / "huggingface-q4",
        PROJECT_ROOT.parent.parent / "model-staging" / "huggingface-q4",
    )
    for candidate in candidates:
        if (candidate / "download-manifest.json").is_file():
            return candidate
    return candidates[0]


def _load_manifest(staging_root: Path) -> dict:
    manifest_path = Path(staging_root).resolve() / "download-manifest.json"
    if not manifest_path.is_file():
        raise AssetVerificationError(f"manifest not found: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetVerificationError(f"invalid model manifest: {manifest_path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise AssetVerificationError(f"manifest has no models list: {manifest_path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(staging_root: Path | None = None) -> dict[str, Path]:
    """Verify all four text candidates and return their resolved paths."""
    root = Path(staging_root or default_staging_root()).resolve()
    manifest = _load_manifest(root)
    records = {
        str(record.get("role", "")): record
        for record in manifest["models"]
        if isinstance(record, dict)
    }
    verified: dict[str, Path] = {}

    for role, spec in ROLE_SPECS.items():
        record = records.get(spec.manifest_role)
        if record is None:
            raise AssetVerificationError(
                f"{role}: manifest role {spec.manifest_role!r} is missing"
            )
        files = record.get("files") or []
        file_record = next(
            (item for item in files if isinstance(item, dict) and item.get("name") == spec.filename),
            None,
        )
        if file_record is None:
            raise AssetVerificationError(f"{role}: manifest file {spec.filename!r} is missing")

        asset_path = root / spec.directory / spec.filename
        if not asset_path.is_file():
            raise AssetVerificationError(f"{role}: asset not found: {asset_path}")

        expected_size = file_record.get("size")
        if expected_size is not None and asset_path.stat().st_size != int(expected_size):
            raise AssetVerificationError(
                f"{role}: size mismatch for {asset_path.name}"
            )
        expected_hash = str(file_record.get("sha256", "")).lower()
        actual_hash = _sha256(asset_path)
        if not expected_hash or actual_hash != expected_hash:
            raise AssetVerificationError(
                f"{role}: SHA-256 mismatch for {asset_path.name}"
            )
        verified[role] = asset_path

    return verified


def _template_path(role: str) -> Path:
    return PROJECT_ROOT / "modelfiles" / ROLE_SPECS[role].template_name


def render_modelfile(role: str, asset_path: Path) -> str:
    """Render a temporary absolute-path Modelfile for one verified asset."""
    spec = ROLE_SPECS.get(role)
    if spec is None:
        raise ValueError(f"unknown role: {role}")
    template_path = _template_path(role)
    if not template_path.is_file():
        raise AssetVerificationError(f"Modelfile template not found: {template_path}")

    lines = template_path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("FROM "):
        raise AssetVerificationError(f"Modelfile template has no FROM line: {template_path}")
    lines[0] = f"FROM {Path(asset_path).resolve()}"
    lines.insert(1, f"# VECTOR_ALIAS: {spec.alias}")
    rendered = "\n".join(lines).rstrip() + "\n"
    if spec.production_alias in rendered:
        raise AssetVerificationError(
            f"{role}: rendered Modelfile mentions production alias {spec.production_alias}"
        )
    return rendered


def build_create_command(
    role: str,
    modelfile_path: Path,
    *,
    ollama_executable: str = "ollama",
) -> list[str]:
    """Build a non-shell Ollama command for one isolated alias."""
    spec = ROLE_SPECS.get(role)
    if spec is None:
        raise ValueError(f"unknown role: {role}")
    return [ollama_executable, "create", spec.alias, "-f", str(Path(modelfile_path).resolve())]


def install_roles(
    roles: Iterable[str] | None = None,
    *,
    staging_root: Path | None = None,
    dry_run: bool = False,
    ollama_executable: str | None = None,
    timeout_seconds: float = 900.0,
) -> list[InstallResult]:
    """Verify assets and create only the requested uncensored text aliases."""
    selected = tuple(roles or ROLE_SPECS)
    unknown = [role for role in selected if role not in ROLE_SPECS]
    if unknown:
        raise ValueError(f"unknown role(s): {', '.join(unknown)}")
    assets = verify_assets(staging_root)

    executable = ollama_executable or "ollama"
    if not dry_run and shutil.which(executable) is None:
        raise InstallerUnavailableError(
            f"Ollama CLI {executable!r} is not on PATH; run this on the host with Ollama installed"
        )

    results: list[InstallResult] = []
    with tempfile.TemporaryDirectory(prefix="vector-uncensored-modelfiles-") as temp_dir:
        temp_root = Path(temp_dir)
        for role in selected:
            spec = ROLE_SPECS[role]
            modelfile_path = temp_root / f"{role}.Modelfile"
            modelfile_path.write_text(render_modelfile(role, assets[role]), encoding="utf-8")
            command = build_create_command(role, modelfile_path, ollama_executable=executable)
            if dry_run:
                logger.info("[VECTOR][uncensored-installer] dry-run: {}", command)
                results.append(InstallResult(role, spec.alias, command, modelfile_path, False))
                continue

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "ollama create failed").strip()
                raise InstallError(f"{role}/{spec.alias}: {detail[:500]}")
            logger.info("[VECTOR][uncensored-installer] created {}", spec.alias)
            results.append(InstallResult(role, spec.alias, command, modelfile_path, True))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify-assets", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--install", action="store_true")
    parser.add_argument("--role", action="append", choices=tuple(ROLE_SPECS))
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    args = parser.parse_args(argv)

    if args.verify_assets or not (args.dry_run or args.install):
        verified = verify_assets(args.staging_root)
        logger.info("[VECTOR][uncensored-installer] verified {} assets", len(verified))
        if not (args.dry_run or args.install):
            return 0

    install_roles(
        roles=args.role,
        staging_root=args.staging_root,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
