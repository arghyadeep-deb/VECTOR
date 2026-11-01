"""Canonical capability status vocabulary and evidence contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable


class CapabilityStatus(str, Enum):
    LIVE = "LIVE"
    NEEDS_CONFIG = "NEEDS_CONFIG"
    FAIL_CLOSED = "FAIL_CLOSED"
    RETIRED = "RETIRED"
    DEFERRED = "DEFERRED"
    FIX_QUEUE = "FIX_QUEUE"


_EVIDENCE_REQUIRED = frozenset(
    {
        CapabilityStatus.LIVE,
        CapabilityStatus.NEEDS_CONFIG,
        CapabilityStatus.FAIL_CLOSED,
        CapabilityStatus.RETIRED,
    }
)


@dataclass(frozen=True)
class CapabilityRecord:
    """One capability disposition in the closure matrix."""

    capability_id: str
    name: str
    status: CapabilityStatus | str
    owner: str = ""
    reason: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)
    exit_criteria: str = ""
    revisit_date: str = ""

    def normalized_status(self) -> CapabilityStatus:
        raw = self.status.value if isinstance(self.status, CapabilityStatus) else str(self.status)
        try:
            return CapabilityStatus(raw.upper())
        except ValueError as exc:
            allowed = ", ".join(status.value for status in CapabilityStatus)
            raise ValueError(f"unknown capability status {raw!r}; expected one of {allowed}") from exc

    def validate(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability_id is required")
        if not self.name.strip():
            raise ValueError(f"capability {self.capability_id!r} is missing a name")

        status = self.normalized_status()
        if status in _EVIDENCE_REQUIRED and not self.evidence:
            raise ValueError(f"capability {self.capability_id!r} requires evidence")
        if status == CapabilityStatus.DEFERRED:
            missing = [
                field_name
                for field_name, value in (
                    ("owner", self.owner),
                    ("reason", self.reason),
                    ("exit_criteria", self.exit_criteria),
                    ("revisit_date", self.revisit_date),
                )
                if not str(value).strip()
            ]
            if missing:
                raise ValueError(
                    f"deferred capability {self.capability_id!r} requires {', '.join(missing)}"
                )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.normalized_status().value
        data["evidence"] = list(self.evidence)
        return data


def validate_capability_records(records: Iterable[CapabilityRecord]) -> None:
    records = list(records)
    ids = [record.capability_id for record in records]
    duplicates = sorted({capability_id for capability_id in ids if ids.count(capability_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate capability ids: {', '.join(duplicates)}")
    for record in records:
        record.validate()


if __name__ == "__main__":
    sample = CapabilityRecord(
        "sample", "sample capability", CapabilityStatus.LIVE, evidence=("self-test",)
    )
    sample.validate()
    print(sample.to_dict())
