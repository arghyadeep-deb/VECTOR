"""Tests for VectorSettings configuration validation."""


import pytest
from pydantic import SecretStr


def test_models_config_vision_and_cloud_orchestrator_defaults():
    from core.config import ModelsConfig

    cfg = ModelsConfig()
    assert cfg.vision == "qwen2.5vl:7b"
    assert cfg.cloud_orchestrator == "vector-r1"


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

    def test_models_config_r1_and_cloud_coder_defaults(self):
        from core.config import ModelsConfig
        config = ModelsConfig()
        assert config.r1 == "vector-r1"
        assert config.cloud_coder == "vector-dev"
