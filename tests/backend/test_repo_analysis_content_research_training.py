import asyncio
import json

import pytest

from core.training.alignment_dataset import build_dpo_pairs, build_sft_examples, export_jsonl
from core.video.provider_capabilities import get_media_provider, list_media_providers
from core.video.workflow_resolver import WorkflowResolutionError, resolve_workflow
from districts.content.asset_video_pipeline import AssetVideoPipelineAgent
from districts.research.paper_ingestion import PaperInput, ingest_paper, paper_card


def test_paper_ingestion_from_text_builds_artifact_and_card():
    artifact = ingest_paper(PaperInput(
        kind="text",
        title="Test Paper",
        value="# Abstract\nThis paper studies VECTOR.\n\n# Limitations\nMore evaluation is needed.",
        tags=["ai"],
    ))
    card = paper_card(artifact)

    assert artifact.title == "Test Paper"
    assert artifact.source.kind == "text"
    assert artifact.content_hash
    assert len(artifact.nodes) == 2
    assert artifact.embedding_text()
    assert card.content_hash == artifact.content_hash
    assert "Abstract" in card.key_sections


def test_paper_ingestion_hash_is_stable():
    first = ingest_paper({"kind": "text", "value": "same paper", "title": "A"})
    second = ingest_paper({"kind": "text", "value": "same paper", "title": "A"})

    assert first.content_hash == second.content_hash


def test_paper_ingestion_doi_is_deferred_not_crash_shape():
    with pytest.raises(ValueError, match="doi ingestion is deferred"):
        ingest_paper({"kind": "doi", "value": "10.0000/example"})


def test_asset_storyboard_generation_with_fake_assets(tmp_path):
    image = tmp_path / "launch_photo.jpg"
    video = tmp_path / "demo_clip.mp4"
    image.write_bytes(b"fake image")
    video.write_bytes(b"fake video")

    agent = AssetVideoPipelineAgent()
    storyboard = agent.build_storyboard(
        assets=[image, video],
        intent="show product progress",
        duration=20,
        title="Launch Update",
        orientation="16:9",
    )

    data = storyboard.to_dict()
    assert data["title"] == "Launch Update"
    assert len(data["assets"]) == 2
    assert len(data["scenes"]) == 2
    assert data["scenes"][0]["render_vars"]["orientation"] == "16:9"


def test_asset_storyboard_missing_asset_returns_error(tmp_path):
    agent = AssetVideoPipelineAgent()
    result = asyncio.run(agent.run({"params": {"assets": [str(tmp_path / "missing.jpg")]}}))

    assert result["status"] == "error"
    assert "asset not found" in result["error"]


def test_media_provider_registry_has_vector_composer():
    providers = list_media_providers()
    vector = get_media_provider("vector_composer")
    longcat = get_media_provider("longcat_external")

    assert providers
    assert vector is not None
    assert vector.configured is True
    assert vector.models[0].modalities
    assert longcat is not None
    assert longcat.configured is False


def test_workflow_resolver_loads_json_and_blocks_traversal(tmp_path):
    workflow = tmp_path / "local" / "demo.json"
    workflow.parent.mkdir()
    workflow.write_text(json.dumps({"ok": True}), encoding="utf-8")

    assert resolve_workflow("local", "demo", roots=[tmp_path]) == {"ok": True}
    with pytest.raises(WorkflowResolutionError):
        resolve_workflow("..", "demo", roots=[tmp_path])
    with pytest.raises(WorkflowResolutionError):
        resolve_workflow("local", "../secret", roots=[tmp_path])


def test_alignment_dataset_builds_sft_and_dpo_pairs(tmp_path):
    rows = [
        {"prompt": "plan", "output": "good plan", "reward": 0.9},
        {"prompt": "plan", "output": "bad plan", "reward": 0.1},
        {"prompt": "skip", "output": "weak", "reward": 0.2},
    ]

    sft = build_sft_examples(rows)
    dpo = build_dpo_pairs(rows)
    out = export_jsonl(dpo, tmp_path / "dpo.jsonl")

    assert len(sft) == 1
    assert len(dpo) == 1
    assert dpo[0]["chosen"] == "good plan"
    assert dpo[0]["rejected"] == "bad plan"
    assert (tmp_path / "dpo.jsonl").read_text(encoding="utf-8").strip()
    assert out.endswith("dpo.jsonl")
