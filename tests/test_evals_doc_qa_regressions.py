"""Regression tests for the document-QA evaluation dataset."""

from vectorcode.src.evals.datasets.doc_qa import DocQADataset
from vectorcode.src.evals.datasets.security_scanner import SecurityScannerDataset


def _ids_by_question(seed: int) -> dict[str, str]:
    dataset = DocQADataset()
    dataset.load(seed=seed)
    return {
        record.metadata["question"]: record.record_id
        for record in dataset.iter_records()
    }


def test_record_ids_are_stable_across_shuffle_seeds() -> None:
    """A task's identity must not depend on its shuffled output position."""
    assert _ids_by_question(1) == _ids_by_question(2)


def _security_ids_by_project(seed: int) -> dict[tuple[tuple[str, str], ...], str]:
    dataset = SecurityScannerDataset()
    dataset.load(seed=seed)
    return {
        tuple(record.metadata["project_files"].items()): record.record_id
        for record in dataset.iter_records()
    }


def test_security_scanner_record_ids_are_stable_across_shuffle_seeds() -> None:
    """Security tasks need stable IDs for comparisons against their ground truth."""
    assert _security_ids_by_project(1) == _security_ids_by_project(2)


if __name__ == "__main__":
    test_record_ids_are_stable_across_shuffle_seeds()
    test_security_scanner_record_ids_are_stable_across_shuffle_seeds()
