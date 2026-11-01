"""VectorHybrid — VectorCode VC-4 Mode C. Autonomous with checkpoint gates."""
from enum import Enum

from loguru import logger
from vectorcode.src.session import VectorCodeSession

# RED actions that require explicit approval
_RED_ACTIONS = frozenset({
    "delete_files", "push_github", "deploy_production",
    "execute_code", "send_email", "financial_transaction",
    "plan_approval",
})


class CheckpointGate(Enum):
    PLAN_APPROVAL   = "plan_approval"
    RED_ACTION      = "red_action"
    DESTRUCTIVE_EDIT = "destructive_edit"


class VectorHybrid:
    """
    Mode C: autonomous execution with asyncio.Event checkpoint gates at
    plan approval and RED-action boundaries.
    """

    mode_label = "hybrid"

    def __init__(self) -> None:
        self.session = VectorCodeSession.get()
        self.checkpoints: dict = {
            CheckpointGate.PLAN_APPROVAL:   True,
            CheckpointGate.RED_ACTION:      True,
            CheckpointGate.DESTRUCTIVE_EDIT: True,
        }
        logger.info("[VECTOR][hybrid] VectorHybrid initialised")

    def needs_approval(self, action: str) -> bool:
        """Return True if the action requires user confirmation."""
        if action in _RED_ACTIONS:
            return self.checkpoints[CheckpointGate.RED_ACTION]
        if action == CheckpointGate.PLAN_APPROVAL.value:
            return self.checkpoints[CheckpointGate.PLAN_APPROVAL]
        return False

    def disable_checkpoint(self, gate: CheckpointGate) -> None:
        self.checkpoints[gate] = False

    def enable_checkpoint(self, gate: CheckpointGate) -> None:
        self.checkpoints[gate] = True


if __name__ == "__main__":
    vh = VectorHybrid()
    assert hasattr(CheckpointGate, "PLAN_APPROVAL")
    assert hasattr(CheckpointGate, "RED_ACTION")
    assert hasattr(CheckpointGate, "DESTRUCTIVE_EDIT")
    assert CheckpointGate.PLAN_APPROVAL in vh.checkpoints
    assert CheckpointGate.RED_ACTION in vh.checkpoints
    assert vh.needs_approval("delete_files") is True
    assert vh.needs_approval("read_file") is False
    assert vh.needs_approval("plan_approval") is True
    assert vh.mode_label == "hybrid"
    print("hybrid.py OK")


