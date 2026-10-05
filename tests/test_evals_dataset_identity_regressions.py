"""Regression tests for stable eval record identities across shuffle seeds."""

from vectorcode.src.evals.datasets.browser_assistant import BrowserAssistantDataset
from vectorcode.src.evals.datasets.coding_task import CodingTaskDataset
from vectorcode.src.evals.datasets.daily_digest import DailyDigestDataset


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


if __name__ == "__main__":
    test_daily_digest_record_ids_survive_shuffle()
    test_coding_task_record_ids_survive_shuffle()
    test_browser_assistant_record_ids_survive_shuffle()
