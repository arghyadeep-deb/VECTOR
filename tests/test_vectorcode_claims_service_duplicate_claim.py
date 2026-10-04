"""Regression for vectorcode/src/claims/_service.py's ClaimService.claim():

the duplicate-claim guard only checked `existing.status == ClaimStatus.active`,
but find_by_issue_id() returns the latest claim that is NOT in a terminal
status (completed/released/expired) -- i.e. any of pending_handoff,
in_review, paused, blocked, stealable also count as "already claimed".
Checking only the literal "active" status let a second claim() call
through while the existing claim sat in one of those other non-terminal
states, creating two live claims for the same issue_id and defeating the
mutual-exclusion this system exists to provide.

Live: real caller is vectorcode/src/swarm.py's SwarmAgent.start_task(),
which calls svc.claim(...) unconditionally. Same bug is present (unfixed)
in the now-dead, import-shadowed vectorcode/src/claims.py monolith --
not touched here since it is unreachable via `import vectorcode.src.claims`
(the claims/ package directory shadows it).
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.claims._persistence import ClaimRepository
from vectorcode.src.claims._service import ClaimService
from vectorcode.src.claims._types import Claimant, ClaimStatus


def _repo(tmp_path):
    return ClaimRepository(db_path=tmp_path / f"claims-{uuid.uuid4().hex}.db")


def test_claim_blocked_while_existing_is_blocked_status(tmp_path):
    svc = ClaimService(_repo(tmp_path))
    owner = Claimant(id="agent-a", type="agent", name="AgentA")
    other = Claimant(id="agent-b", type="agent", name="AgentB")

    first = svc.claim("issue-1", owner)
    assert first is not None

    assert svc.update_status("issue-1", ClaimStatus.blocked) is True

    second = svc.claim("issue-1", other)
    assert second is None, "a blocked (non-terminal) claim must still block a second claim()"

    claims_for_issue = [c for c in svc.repo.find_all() if c.issue_id == "issue-1"]
    assert len(claims_for_issue) == 1


def test_claim_allowed_after_release(tmp_path):
    svc = ClaimService(_repo(tmp_path))
    owner = Claimant(id="agent-a", type="agent", name="AgentA")
    other = Claimant(id="agent-b", type="agent", name="AgentB")

    first = svc.claim("issue-2", owner)
    assert first is not None
    assert svc.release("issue-2", owner.id) is True

    second = svc.claim("issue-2", other)
    assert second is not None, "a released (terminal) claim must allow a fresh claim()"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
