from __future__ import annotations

import asyncio
import inspect
import uuid
from pathlib import Path


def test_fincept_base_points_to_absorbed_vector_finagent_tree() -> None:
    from districts.investment import finagent_agent

    assert finagent_agent._FINCEPT_BASE.name == "vector_finagent"
    assert finagent_agent._FINCEPT_BASE.exists()
    assert (finagent_agent._FINCEPT_BASE / "agents" / "TraderInvestorsAgent").exists()
    assert finagent_agent._load_investor_personas()


def test_voice_tts_accepts_profile_name_keyword() -> None:
    from core.voice.tts import VoiceTTS

    signature = inspect.signature(VoiceTTS.speak)
    assert "profile_name" in signature.parameters
    tts = VoiceTTS()
    assert "profile_name" in tts.speak.__code__.co_varnames


def test_voice_profile_reference_storage_uses_local_driver(tmp_path: Path) -> None:
    from core.collections.storage import FileStorage, LocalDriver
    from core.voice.voice_profiles import ProfileType, VoiceProfile, VoiceProfileStore

    store = VoiceProfileStore(storage=FileStorage(LocalDriver(tmp_path)))
    name = f"AuditVoice_{uuid.uuid4().hex[:8]}"
    profile = VoiceProfile(name=name, type=ProfileType.CLONED)
    store.create(profile)

    key = store.upload_reference(name, b"RIFFfake-wave", "reference.wav")

    assert key.startswith(f"voice_profiles/{name}/")
    assert store.get_reference_bytes(name) == b"RIFFfake-wave"


def test_comfyui_adapter_exposes_operational_sidecar_methods() -> None:
    from districts.content.comfyui_adapter import ComfyUIAdapter

    adapter = ComfyUIAdapter()
    for method in (
        "get_system_stats",
        "get_node_info",
        "list_model_types",
        "list_models_by_type",
        "get_history",
        "get_jobs",
        "interrupt",
        "free_memory",
        "upload_image",
    ):
        assert hasattr(adapter, method)


def test_comfyui_upload_image_rejects_missing_file() -> None:
    from districts.content.comfyui_adapter import ComfyUIAdapter

    result = asyncio.run(ComfyUIAdapter().upload_image("does-not-exist.png"))

    assert result["status"] == "error"
    assert "image not found" in result["error"]
