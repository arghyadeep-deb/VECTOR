import pytest
from fastapi import HTTPException

from core.api import tasks as external_tasks


@pytest.mark.asyncio
async def test_legacy_external_tasks_fail_closed_without_internal_token(monkeypatch):
    # _internal_token() reads os.environ live (call-time, not import-time --
    # see core/api/tasks.py's own docstring on why), so patch the env var
    # rather than a module constant.
    monkeypatch.delenv("VECTOR_INTERNAL_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        await external_tasks.submit_task(
            external_tasks.TaskSubmission(action_type="respond", params={}),
            authorization=None,
        )

    assert exc.value.status_code == 503

