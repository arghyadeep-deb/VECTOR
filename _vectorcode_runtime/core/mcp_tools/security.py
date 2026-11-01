"""Security wrapper for VECTOR MCP tool calls."""

from __future__ import annotations

from loguru import logger


def mcp_secure_call(tool_name: str, source_district: str, params: dict) -> bool:
    """Classify, rate-limit, and audit an MCP tool call. Returns True if allowed."""
    try:
        import time as _time
        from core.security.mcp_security import ToolCallRecord, get_mcp_security

        mw = get_mcp_security()
        risk = mw.classify_tool(tool_name)
        allowed = mw.check_rate_limit(source_district, tool_name)
        anomalous = mw.detect_anomalous_call(tool_name, source_district, params)
        if anomalous:
            logger.warning(
                "[VECTOR][mcp_sec] anomalous call: {} from {}",
                tool_name,
                source_district,
            )
        mw.audit_call(
            ToolCallRecord(
                tool_name=tool_name,
                source_district=source_district,
                params=params,
                timestamp=_time.time(),
                allowed=allowed,
                risk_level=risk,
            )
        )
        if not allowed:
            logger.warning(
                "[VECTOR][mcp_sec] rate-limit blocked {} from {}",
                tool_name,
                source_district,
            )
        return allowed
    except Exception as exc:
        logger.debug("[VECTOR][mcp_sec] security check failed (allowing): {}", exc)
        return True
