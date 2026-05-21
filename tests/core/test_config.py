"""Tests for VectorSettings configuration validation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from pydantic import SecretStr


class TestVectorSettings:
    """Test that VectorSettings validates types correctly."""

    @pytest.mark.asyncio
    async def test_defaults_loaded(self):
        from core.config import VectorSettings
        cfg = VectorSettings()
        assert hasattr(cfg, "VECTOR_ENV")
        assert hasattr(cfg, "OLLAMA_HOST")
        assert isinstance(cfg.VECTOR_ENV, str)

    @pytest.mark.asyncio
    async def test_secret_str_masks_repr(self):
        from core.config import VectorSettings
        cfg = VectorSettings()
        if cfg.VECTOR_OFP_SECRET:
            assert isinstance(cfg.VECTOR_OFP_SECRET, SecretStr)
            assert "****" in repr(cfg.VECTOR_OFP_SECRET)

    @pytest.mark.asyncio
    async def test_config_global_dict_keys(self):
        from core.config import CONFIG
        assert "version" in CONFIG
        assert "allowed_origins" in CONFIG
