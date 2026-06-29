import pytest
from fastapi import HTTPException

from core.api import tasks as external_tasks


@pytest.mark.asyncio
async def test_legacy_external_tasks_fail_closed_without_internal_token(monkeypatch):
    monkeypatch.setattr(external_tasks, "_INTERNAL_TOKEN", "")

    with pytest.raises(HTTPException) as exc:
        await external_tasks.submit_task(
            external_tasks.TaskSubmission(action_type="respond", params={}),
            authorization=None,
        )

    assert exc.value.status_code == 503

