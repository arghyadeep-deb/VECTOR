"""MCP voice profile tools."""

from loguru import logger

from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call


def add_voice_profile_tools(mcp) -> None:
    """Expose voice profile management to MCP clients (voicebox absorption)."""
    try:
        from core.voice.voice_profiles import get_profile_store  # noqa: F401
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] voice profile tools unavailable: {e}")
        return

    @mcp.tool
    def list_voice_profiles() -> str:
        """List all stored VECTOR voice profiles (name, type, engine, is_default)."""
        if not _mcp_secure_call("list_voice_profiles", "voice", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            store = get_profile_store()
            return _safe_json({"profiles": [p.to_dict() for p in store.list_all()]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def speak_as(profile_name: str, text: str) -> str:
        """Speak `text` using the named voice profile (cloned local voice if available,
        otherwise the profile's configured engine). Returns status JSON."""
        if not _mcp_secure_call("speak_as", "voice", {"profile": profile_name}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        if not text or not text.strip():
            return _safe_json({"error": "text is empty; nothing to speak"})
        try:
            from core.voice.tts import VoiceTTS
            tts = VoiceTTS()
            tts.speak(text, profile_name=profile_name)
            return _safe_json({"status": "spoken", "profile": profile_name})
        except Exception as e:
            return _safe_json({"error": str(e)})
