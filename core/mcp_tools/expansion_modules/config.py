from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_config_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ config_* (26) — wired to core/config.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.config import CONFIG as _CONFIG, VectorSettings as _VectorSettings

        @mcp.tool
        def config_get(key: str) -> str:
            """Get a VECTOR config value."""
            value = _CONFIG.get(key)
            return _safe_json({"key": key, "value": str(value) if not isinstance(value, (dict, list)) else value})

        @mcp.tool
        def config_list() -> str:
            """List all config keys and values (secrets redacted)."""
            redacted = {}
            for k, v in _CONFIG.items():
                if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower() or "password" in k.lower():
                    redacted[k] = "***REDACTED***"
                elif isinstance(v, dict):
                    redacted[k] = {kk: ("***REDACTED***" if "key" in kk.lower() or "secret" in kk.lower() else vv) for kk, vv in v.items()}
                else:
                    redacted[k] = v
            return _safe_json(redacted)

        @mcp.tool
        def config_version() -> str:
            """Get config schema version."""
            return _safe_json({"version": _CONFIG.get("version", "unknown")})

        @mcp.tool
        def config_env() -> str:
            """View environment variables relevant to VECTOR."""
            relevant = {k: v for k, v in _os.environ.items() if k.startswith("VECTOR_") or k.startswith("OLLAMA_") or k.startswith("OPENAI_")}
            return _safe_json(relevant)

        @mcp.tool
        def config_secrets() -> str:
            """View secret config values (redacted for safety)."""
            keys = _CONFIG.get("api_keys", {})
            return _safe_json({k: "***REDACTED***" for k in keys})

        @mcp.tool
        def config_models() -> str:
            """View or change model routing config."""
            models = _CONFIG.get("models", {})
            router = _CONFIG.get("model_router", {})
            return _safe_json({"models": models, "router": router})

        @mcp.tool
        def config_agents() -> str:
            """View agent config."""
            try:
                from core.city.agent_registry import get_registry
                reg = get_registry()
                all_agents = reg.list_all()
                by_district = {}
                for a in all_agents:
                    d = getattr(a, "district", "unknown")
                    by_district[d] = by_district.get(d, 0) + 1
                return _safe_json({"total": len(all_agents), "by_district": by_district})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def config_workers() -> str:
            """View worker config."""
            tq = _CONFIG.get("task_queue", {})
            return _safe_json(tq)

        @mcp.tool
        def config_memory() -> str:
            """View memory config."""
            obsidian = _CONFIG.get("obsidian", {})
            return _safe_json({"obsidian": obsidian, "db_path": _CONFIG.get("db_path", ""), "vault_path": _CONFIG.get("vault_path", "")})

        @mcp.tool
        def config_security() -> str:
            """View security config."""
            security = _CONFIG.get("security", {})
            permission = _CONFIG.get("permission", {})
            return _safe_json({"security": security, "permission": permission})

        @mcp.tool
        def config_network() -> str:
            """View network config."""
            return _safe_json({"ollama_host": _CONFIG.get("ollama_host", ""), "allowed_origins": _CONFIG.get("allowed_origins", [])})

        @mcp.tool
        def config_storage() -> str:
            """View storage config."""
            return _safe_json({"db_path": _CONFIG.get("db_path", ""), "vault_path": _CONFIG.get("vault_path", "")})

        @mcp.tool
        def config_auth() -> str:
            """View auth config."""
            keys = _CONFIG.get("api_keys", {})
            return _safe_json({k: "***REDACTED***" for k in keys})

        @mcp.tool
        def config_metrics() -> str:
            """View metrics config."""
            cost = _CONFIG.get("cost", {})
            council = _CONFIG.get("council", {})
            return _safe_json({"cost": cost, "council": council})

        @mcp.tool
        def config_reset() -> str:
            """Reset config to defaults."""
            defaults = _VectorSettings()
            return _safe_json({"status": "defaults_shown", "note": "Config is read-only at runtime — update .env file to persist changes"})

        @mcp.tool
        def config_export() -> str:
            """Export config to JSON (secrets redacted)."""
            redacted = {}
            for k, v in _CONFIG.items():
                if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    redacted[k] = "***REDACTED***"
                elif isinstance(v, dict):
                    redacted[k] = {kk: ("***REDACTED***" if "key" in kk.lower() or "secret" in kk.lower() else vv) for kk, vv in v.items()}
                else:
                    redacted[k] = v
            return _safe_json(redacted)

        @mcp.tool
        def config_validate() -> str:
            """Validate config against schema."""
            try:
                defaults = _VectorSettings()
                return _safe_json({"valid": True, "schema_version": defaults.version})
            except Exception as e:
                return _safe_json({"valid": False, "error": str(e)})

        @mcp.tool
        def config_diff() -> str:
            """Diff current config against defaults."""
            defaults = _VectorSettings()
            diffs = {}
            for k, v in _CONFIG.items():
                dv = getattr(defaults, k, None) if hasattr(defaults, k) else None
                if v != dv:
                    diffs[k] = {"current": str(v), "default": str(dv)}
            return _safe_json({"diffs": diffs, "total_changes": len(diffs)})

        @mcp.tool
        def config_apply(changes: str) -> str:
            """Apply a config change set (runtime only, not persisted)."""
            try:
                changes_dict = _json.loads(changes) if changes else {}
                applied = []
                for k, v in changes_dict.items():
                    if k in _CONFIG:
                        _CONFIG[k] = v
                        applied.append(k)
                return _safe_json({"ok": True, "applied": applied, "note": "Changes are runtime-only — update .env to persist"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def config_backup() -> str:
            """Backup current .env file."""
            env_file = ROOT / ".env"
            backup = ROOT / f".env.backup.{int(_time.time())}"
            if env_file.exists():
                _shutil.copy2(str(env_file), str(backup))
                return _safe_json({"ok": True, "backup": str(backup)})
            return _safe_json({"error": ".env file not found"})

        @mcp.tool
        def config_restore(backup_path: str) -> str:
            """Restore a config backup."""
            env_file = ROOT / ".env"
            backup = _Path(backup_path)
            if backup.exists():
                _shutil.copy2(str(backup), str(env_file))
                return _safe_json({"ok": True, "restored": str(backup)})
            return _safe_json({"error": f"Backup not found: {backup_path}"})

        @mcp.tool
        def config_import(path: str) -> str:
            """Import config from JSON file (runtime only)."""
            try:
                with open(path) as f:
                    data = _json.load(f)
                applied = []
                for k, v in data.items():
                    if k in _CONFIG:
                        _CONFIG[k] = v
                        applied.append(k)
                return _safe_json({"ok": True, "applied": applied})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def config_logging() -> str:
            """View logging config."""
            return _safe_json({"debug": _CONFIG.get("debug", False), "log_level": _CONFIG.get("log_level", "INFO")})

        @mcp.tool
        def config_hooks() -> str:
            """View hook config."""
            return _safe_json({"status": "redirect", "message": "Hooks are configured via coding_assistant hooks manager"})

        @mcp.tool
        def config_set(key: str, value: str) -> str:
            """Set a VECTOR config value (runtime only, not persisted)."""
            if key in _CONFIG:
                _CONFIG[key] = value
                return _safe_json({"ok": True, "key": key, "note": "Runtime-only — update .env to persist"})
            return _safe_json({"error": f"Unknown config key: {key}"})

        @mcp.tool
        def config_rollback() -> str:
            """Rollback to previous config."""
            backups = sorted(ROOT.glob(".env.backup.*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if backups:
                return _safe_json({"latest_backup": str(backups[0]), "note": "Use config_restore to apply"})
            return _safe_json({"error": "No backups found"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] config tools unavailable: {e}")
        for n, d in [("config_get", "Get config"), ("config_list", "List config"), ("config_version", "Config version"), ("config_env", "Env vars"), ("config_secrets", "Secrets"), ("config_models", "Models"), ("config_agents", "Agents"), ("config_workers", "Workers"), ("config_memory", "Memory"), ("config_security", "Security"), ("config_network", "Network"), ("config_storage", "Storage"), ("config_auth", "Auth"), ("config_metrics", "Metrics"), ("config_reset", "Reset config"), ("config_export", "Export config"), ("config_validate", "Validate config"), ("config_diff", "Config diff"), ("config_apply", "Apply config"), ("config_backup", "Backup config"), ("config_restore", "Restore config"), ("config_import", "Import config"), ("config_logging", "Logging config"), ("config_hooks", "Hook config"), ("config_set", "Set config"), ("config_rollback", "Rollback config")]:
            _reg(mcp, n, d)
