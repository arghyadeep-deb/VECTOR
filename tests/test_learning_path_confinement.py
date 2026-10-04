"""Regression tests for untrusted distillation path identifiers."""

from pathlib import Path

import pytest

from vectorcode.src.learning.distillation.execute.appliers.agent import (
    EditFewShotExemplarsApplier,
    ReplaceSystemPromptApplier,
)
from vectorcode.src.learning.distillation.execute.base import ApplyContext
from vectorcode.src.learning.distillation.models import (
    Edit,
    EditOp,
    EditPillar,
    EditRiskTier,
)
from vectorcode.src.learning.distillation.pending_queue import PendingQueue


def _edit(op: EditOp, payload: dict) -> Edit:
    return Edit(
        id="edit-1",
        pillar=EditPillar.AGENT,
        op=op,
        target="agents.safe.system_prompt",
        payload=payload,
        rationale="regression",
        expected_improvement="cluster-1",
        risk_tier=EditRiskTier.AUTO,
    )


@pytest.mark.parametrize("method", ["get", "resolve"])
def test_pending_queue_rejects_path_traversal(tmp_path: Path, method: str) -> None:
    queue = PendingQueue(tmp_path / "queue")

    with pytest.raises(ValueError, match="escape"):
        getattr(queue, method)("../outside", "edit")


def test_pending_queue_enqueue_rejects_traversal_edit_id(tmp_path: Path) -> None:
    queue = PendingQueue(tmp_path / "queue")
    edit = _edit(EditOp.REPLACE_SYSTEM_PROMPT, {"new_content": "safe"})
    edit.id = "../outside"

    with pytest.raises(ValueError, match="escape"):
        queue.enqueue("session", edit)


@pytest.mark.parametrize(
    ("applier", "edit"),
    [
        (
            ReplaceSystemPromptApplier(),
            _edit(
                EditOp.REPLACE_SYSTEM_PROMPT,
                {"agent": "../../outside", "new_content": "overwritten"},
            ),
        ),
        (
            EditFewShotExemplarsApplier(),
            _edit(
                EditOp.EDIT_FEW_SHOT_EXEMPLARS,
                {"agent": "../../outside", "exemplars": []},
            ),
        ),
    ],
)
def test_agent_file_appliers_reject_path_traversal(
    tmp_path: Path, applier: object, edit: Edit
) -> None:
    ctx = ApplyContext(vector_home=tmp_path / "home", session_id="session")
    (ctx.agents_dir / "safe").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    result = applier.validate(edit, ctx)

    assert not result.ok
    assert "Invalid agent name" in result.reason
    with pytest.raises(ValueError, match="Invalid agent name"):
        applier.apply(edit, ctx)
    assert not (outside / "system_prompt.md").exists()
    assert not (outside / "few_shot.json").exists()
