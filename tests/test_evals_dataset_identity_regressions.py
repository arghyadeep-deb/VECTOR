"""Regression tests for stable eval record identities across shuffle seeds."""

import sys
from types import SimpleNamespace

import pytest
from loguru import logger

from vectorcode.src.evals.datasets.adp import ADPDataset, _parse_content
from vectorcode.src.evals.datasets.browser_assistant import BrowserAssistantDataset
from vectorcode.src.evals.datasets.coding_task import CodingTaskDataset
from vectorcode.src.evals.datasets.daily_digest import DailyDigestDataset
from vectorcode.src.evals.datasets.email_triage import EmailTriageDataset
from vectorcode.src.evals.datasets.frames import FRAMESDataset
from vectorcode.src.evals.datasets.gaia import GAIADataset
from vectorcode.src.evals.datasets.generalthoughts import GeneralThoughtsDataset
from vectorcode.src.evals.datasets.gpqa import GPQADataset
from vectorcode.src.evals.datasets.hle import HLEDataset
from vectorcode.src.evals.datasets.ipw_mixed import IPWDataset
from vectorcode.src.evals.datasets.knowledge_base import KnowledgeBaseDataset
from vectorcode.src.evals.datasets.math500 import MATH500Dataset
from vectorcode.src.evals.datasets.mmlu_pro import MMLUProDataset
from vectorcode.src.evals.datasets.morning_brief import MorningBriefDataset
from vectorcode.src.evals.datasets.natural_reasoning import NaturalReasoningDataset
from vectorcode.src.evals.datasets.research_mining import ResearchMiningDataset
from vectorcode.src.evals.datasets.simpleqa import SimpleQADataset, _parse_metadata
from vectorcode.src.evals.datasets.supergpqa import SuperGPQADataset
from vectorcode.src.evals.datasets.toolorchestra import ToolOrchestraDataset, _parse_field
from vectorcode.src.evals.datasets.wildchat import WildChatDataset


def _identity_map(dataset_type) -> dict[str, str]:
    mappings = []
    for seed in (7, 29):
        dataset = dataset_type()
        dataset.load(seed=seed)
        mappings.append(
            {
                record.problem: record.record_id
                for record in dataset.iter_records()
            }
        )
    assert mappings[0] == mappings[1]
    return mappings[0]


def test_daily_digest_record_ids_survive_shuffle() -> None:
    assert _identity_map(DailyDigestDataset)


def test_coding_task_record_ids_survive_shuffle() -> None:
    assert _identity_map(CodingTaskDataset)


def test_browser_assistant_record_ids_survive_shuffle() -> None:
    assert _identity_map(BrowserAssistantDataset)


def _install_fake_datasets(monkeypatch, rows) -> None:
    dataset = SimpleNamespace(to_list=lambda: [dict(row) for row in rows])
    monkeypatch.setitem(
        sys.modules,
        "datasets",
        SimpleNamespace(load_dataset=lambda *args, **kwargs: dataset),
    )


def test_gpqa_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {
            "Question": f"Question {i}",
            "Correct Answer": "correct",
            "Incorrect Answer 1": "wrong 1",
            "Incorrect Answer 2": "wrong 2",
            "Incorrect Answer 3": "wrong 3",
        }
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(GPQADataset)


def test_hle_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"id": f"task-{i}", "question": f"Question {i}", "answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(HLEDataset)


def test_ipw_record_ids_survive_shuffle(monkeypatch, tmp_path) -> None:
    rows = [
        {"problem": f"Problem {i}", "answer": "answer", "subject": "general"}
        for i in range(8)
    ]
    monkeypatch.setattr(IPWDataset, "_load_rows", lambda self, path: rows)

    def dataset_factory():
        return IPWDataset(data_dir=str(tmp_path))

    assert _identity_map(dataset_factory)


def test_email_triage_record_ids_survive_shuffle() -> None:
    assert _identity_map(EmailTriageDataset)


def test_frames_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"Prompt": f"Question {i}", "Answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(FRAMESDataset)


def test_math500_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"problem": f"Problem {i}", "answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(MATH500Dataset)


def test_mmlu_pro_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"question": f"Question {i}", "options": ["A", "B"], "answer": "A"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(MMLUProDataset)


def test_natural_reasoning_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"problem": f"Problem {i}", "answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(NaturalReasoningDataset)


def test_simpleqa_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"problem": f"Problem {i}", "answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(SimpleQADataset)


def test_research_mining_record_ids_survive_shuffle() -> None:
    assert _identity_map(ResearchMiningDataset)


def test_supergpqa_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {
            "question": f"Question {i}",
            "options": ["A", "B"],
            "answer_letter": "A",
        }
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(SuperGPQADataset)


def test_wildchat_record_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {
            "language": "English",
            "conversation": [
                {"role": "user", "content": f"Question {i}"},
                {"role": "assistant", "content": "Answer"},
            ],
        }
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(WildChatDataset)


def test_knowledge_base_record_ids_survive_shuffle() -> None:
    assert _identity_map(KnowledgeBaseDataset)


def test_morning_brief_record_ids_survive_shuffle() -> None:
    assert _identity_map(MorningBriefDataset)


def test_generalthoughts_fallback_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {"question": f"Question {i}", "model_answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(GeneralThoughtsDataset)


def test_adp_fallback_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {
            "content": [
                {"source": "user", "content": f"Question {i}"},
                {"source": "assistant", "class_": "message_action", "content": "Answer"},
            ]
        }
        for i in range(8)
    ]
    monkeypatch.setitem(
        sys.modules,
        "datasets",
        SimpleNamespace(
            load_dataset=lambda *args, **kwargs: (
                iter(rows) if args[1] == "agenttuning_alfworld" else iter(())
            )
        ),
    )
    assert _identity_map(ADPDataset)


def test_gaia_fallback_ids_survive_shuffle(monkeypatch, tmp_path) -> None:
    rows = [
        {"Question": f"Question {i}", "Final answer": "answer"}
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    (tmp_path / "GAIA").mkdir()
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=lambda **kwargs: None),
    )

    def dataset_factory():
        return GAIADataset(cache_dir=str(tmp_path))

    assert _identity_map(dataset_factory)


def test_toolorchestra_fallback_ids_survive_shuffle(monkeypatch) -> None:
    rows = [
        {
            "user_scenario": {
                "instructions": {"task_instructions": f"Question {i}"}
            },
            "evaluation_criteria": {"actions": ["answer"]},
        }
        for i in range(8)
    ]
    _install_fake_datasets(monkeypatch, rows)
    assert _identity_map(ToolOrchestraDataset)


@pytest.mark.parametrize(
    "parser",
    [_parse_content, _parse_metadata, _parse_field],
)
def test_parse_failure_logs_render_exception(parser) -> None:
    messages = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        parser("{")
    finally:
        logger.remove(sink_id)

    assert messages
    assert "%s" not in messages[-1]
    assert "was never closed" in messages[-1]


if __name__ == "__main__":
    test_daily_digest_record_ids_survive_shuffle()
    test_coding_task_record_ids_survive_shuffle()
    test_browser_assistant_record_ids_survive_shuffle()
