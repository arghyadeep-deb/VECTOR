"""Regression tests for coding-assistant dataset identity stability."""

from vectorcode.src.evals.datasets.coding_assistant import CodingAssistantDataset


def _records_by_id(seed: int):
    dataset = CodingAssistantDataset()
    dataset.load(seed=seed)
    return {record.record_id: record for record in dataset.iter_records()}


def test_record_ids_remain_bound_to_same_task_across_shuffle_seeds():
    first = _records_by_id(1)
    second = _records_by_id(2)

    assert first.keys() == second.keys()
    assert len(first) == 30
    for record_id in first:
        assert first[record_id].metadata["bug_report"] == second[record_id].metadata[
            "bug_report"
        ]
        assert first[record_id].metadata["buggy_code"] == second[record_id].metadata[
            "buggy_code"
        ]


if __name__ == "__main__":
    test_record_ids_remain_bound_to_same_task_across_shuffle_seeds()
