"""Structured logging — per-subsystem log levels, file rotation, JSON output."""
import sys
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional


from loguru import logger
from pathlib import Path


class LogLevel(IntEnum):
    TRACE    = 5
    DEBUG    = 10
    INFO     = 20
    SUCCESS  = 25
    WARNING  = 30
    ERROR    = 40
    CRITICAL = 50


@dataclass
class LogConfig:
    level: LogLevel = LogLevel.INFO
    file_rotation: str = "10 MB"       # loguru rotation spec
    file_retention: str = "7 days"
    json_format: bool = False
    log_dir: Optional[Path] = None     # defaults to ~/.vector/logs/

    def __post_init__(self) -> None:
        if self.log_dir is None:
            self.log_dir = Path.home() / ".vector" / "logs"


class VectorLogger:
    """
    Per-subsystem logger wrapping loguru.

    Usage::

        log = get_subsystem_logger("voice")
        log.info("STT started")   # → [VECTOR][voice] STT started

    Features:
    - Per-subsystem log levels (set "voice" to DEBUG, everything else INFO)
    - File rotation at ~/.vector/logs/vectorcode_{date}.log
    - Optional JSON structured format:
      {"ts": "...", "level": "INFO", "subsystem": "...", "msg": "..."}
    - Session ID injection if set
    """

    def __init__(self, subsystem: str, config: LogConfig) -> None:
        self.subsystem = subsystem
        self.config = config
        self._session_id: str = ""
        # Per-subsystem override (checked on every log call)
        self._level_override: Optional[LogLevel] = None

    # ── public interface ──────────────────────────────────────────────────────

    def set_session_id(self, session_id: str) -> None:
        """Inject session ID into all subsequent log messages."""
        self._session_id = session_id

    def set_level(self, level: LogLevel) -> None:
        """Override the effective log level for this subsystem."""
        self._level_override = level

    def _effective_level(self) -> LogLevel:
        return self._level_override if self._level_override is not None else self.config.level

    # ── log methods ───────────────────────────────────────────────────────────

    def trace(self, msg: str, **ctx) -> None:
        if self._effective_level() <= LogLevel.TRACE:
            self._log("TRACE", msg, **ctx)

    def debug(self, msg: str, **ctx) -> None:
        if self._effective_level() <= LogLevel.DEBUG:
            self._log("DEBUG", msg, **ctx)

    def info(self, msg: str, **ctx) -> None:
        if self._effective_level() <= LogLevel.INFO:
            self._log("INFO", msg, **ctx)

    def success(self, msg: str, **ctx) -> None:
        if self._effective_level() <= LogLevel.SUCCESS:
            self._log("SUCCESS", msg, **ctx)

    def warning(self, msg: str, **ctx) -> None:
        if self._effective_level() <= LogLevel.WARNING:
            self._log("WARNING", msg, **ctx)

    def error(self, msg: str, **ctx) -> None:
        if self._effective_level() <= LogLevel.ERROR:
            self._log("ERROR", msg, **ctx)

    def critical(self, msg: str, **ctx) -> None:
        self._log("CRITICAL", msg, **ctx)

    # ── core formatter ────────────────────────────────────────────────────────

    def _log(self, level: str, msg: str, **ctx) -> None:
        """Core logging.  Formats as [VECTOR][subsystem] msg or JSON."""
        if self.config.json_format:
            record: dict = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "subsystem": self.subsystem,
                "msg": msg,
                **ctx,
            }
            if self._session_id:
                record["session_id"] = self._session_id
            formatted = json.dumps(record, ensure_ascii=False)
        else:
            prefix = f"[VECTOR][{self.subsystem}]"
            if self._session_id:
                prefix += f"[{self._session_id[:8]}]"
            formatted = f"{prefix} {msg}"
            if ctx:
                formatted += "  " + " ".join(f"{k}={v}" for k, v in ctx.items())

        # Map to loguru levels (loguru uses "warning" not "WARN", etc.)
        level_lower = level.lower()
        log_fn = getattr(logger, level_lower, None)
        if log_fn is None:
            log_fn = logger.info
        log_fn(formatted)


class LogManager:
    """
    Central log manager.  Configures loguru sinks and manages per-subsystem loggers.

    This is intentionally a class with class-level state (singleton via class vars)
    so that configure() called once at startup affects all subsequent get_logger() calls.
    """

    _subsystem_levels: dict[str, LogLevel] = {}
    _loggers: dict[str, "VectorLogger"] = {}
    _config: LogConfig = LogConfig()
    _initialized: bool = False
    _file_sink_id: Optional[int] = None

    # ── configuration ─────────────────────────────────────────────────────────

    @classmethod
    def configure(cls, config: LogConfig) -> None:
        """
        Configure loguru:
        1. Remove default sink
        2. Add stderr sink at config.level
        3. Add rotating file sink at ~/.vector/logs/vectorcode_{time}.log
        4. Apply per-subsystem level overrides to existing loggers
        """
        cls._config = config

        # Remove all existing loguru sinks
        logger.remove()

        # Stderr sink
        if config.json_format:
            fmt = "{message}"  # VectorLogger already formats the JSON record
        else:
            fmt = "<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}"

        logger.add(
            sys.stderr,
            level=config.level.name,
            format=fmt,
            colorize=not config.json_format,
        )

        # File sink — rotating, retained for N days
        try:
            config.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = str(config.log_dir / "vectorcode_{time:YYYY-MM-DD}.log")
            cls._file_sink_id = logger.add(
                log_path,
                rotation=config.file_rotation,
                retention=config.file_retention,
                level=config.level.name,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"[VECTOR][logging] could not create file sink: {exc}")

        # Re-apply per-subsystem level overrides
        for subsystem, level in cls._subsystem_levels.items():
            if subsystem in cls._loggers:
                cls._loggers[subsystem].set_level(level)

        cls._initialized = True
        logger.debug("[VECTOR][logging] configured — level={level} json={json} dir={dir}",
                     level=config.level.name,
                     json=config.json_format,
                     dir=str(config.log_dir))

    @classmethod
    def set_subsystem_level(cls, subsystem: str, level: LogLevel) -> None:
        """Set log level for a specific subsystem."""
        cls._subsystem_levels[subsystem] = level
        if subsystem in cls._loggers:
            cls._loggers[subsystem].set_level(level)

    @classmethod
    def get_logger(cls, subsystem: str) -> "VectorLogger":
        """Get or create a logger for subsystem."""
        if subsystem not in cls._loggers:
            vl = VectorLogger(subsystem, cls._config)
            # Apply any pre-set level override
            if subsystem in cls._subsystem_levels:
                vl.set_level(cls._subsystem_levels[subsystem])
            cls._loggers[subsystem] = vl
        else:
            # Keep config reference current (handles post-configure calls)
            cls._loggers[subsystem].config = cls._config
        return cls._loggers[subsystem]

    @classmethod
    def reset(cls) -> None:
        """Reset state — useful in tests."""
        cls._subsystem_levels.clear()
        cls._loggers.clear()
        cls._initialized = False


# ── Public API ────────────────────────────────────────────────────────────────

def get_subsystem_logger(subsystem: str) -> VectorLogger:
    """Convenience: get logger for a subsystem."""
    return LogManager.get_logger(subsystem)


def configure_logging(
    level: str = "INFO",
    *,
    json_format: bool = False,
    log_dir: Optional[Path] = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """One-call logging setup.  Call at startup."""
    lvl = LogLevel[level.upper()]
    config = LogConfig(
        level=lvl,
        json_format=json_format,
        log_dir=log_dir or Path.home() / ".vector" / "logs",
        file_rotation=rotation,
        file_retention=retention,
    )
    LogManager.configure(config)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. configure_logging at INFO level — no crash
    configure_logging("INFO")

    # 2. Basic subsystem logger
    log = get_subsystem_logger("test")
    log.info("hello from test subsystem")
    log.warning("this is a warning", key="value")
    log.debug("this should be filtered out at INFO level")

    # 3. Voice logger — debug messages
    voice_log = get_subsystem_logger("voice")
    voice_log.debug("mic started")
    voice_log.info("wake word detected")

    # 4. Per-subsystem level override
    LogManager.set_subsystem_level("voice", LogLevel.DEBUG)
    voice_log2 = get_subsystem_logger("voice")
    voice_log2.debug("this debug should now appear for voice subsystem")

    # 5. Session ID injection
    session_log = get_subsystem_logger("session")
    session_log.set_session_id("abc123def456")
    session_log.info("session started")

    # 6. JSON format mode
    configure_logging("INFO", json_format=True)
    json_log = get_subsystem_logger("json_test")
    json_log.info("structured json log", user="arghyadeep", action="test")

    # 7. Verify LogLevel values are correct
    assert LogLevel.TRACE < LogLevel.DEBUG < LogLevel.INFO
    assert LogLevel.INFO < LogLevel.WARNING < LogLevel.ERROR < LogLevel.CRITICAL
    assert LogLevel["INFO"] == LogLevel.INFO

    # 8. VectorLogger respects level filter
    configure_logging("WARNING")
    filtered_log = get_subsystem_logger("filtered")
    filtered_log.debug("should be suppressed")
    filtered_log.info("should be suppressed too")
    filtered_log.warning("this warning should pass through")

    print("utils/logging.py OK")
