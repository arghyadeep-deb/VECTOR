from fastapi.testclient import TestClient

from core.api import create_app
from core.loop.permission_gateway import GatewayResult
from core.runtime.missions import (
    MISSION_JOBS,
    MISSION_STORE,
    MissionJob,
    MissionJobStore,
    MissionPlanAdvisor,
    MissionRunner,
    MissionStore,
    ObjectiveDecomposer,
)


class FakeGateway:
    def __init__(self, results):
        self.results = list(results)
        self.seen = []

    def _classify(self, action_type: str) -> str:
        if self.results:
            return self.results[0].level
        return "GREEN"

    async def execute(self, action):
        self.seen.append(action)
        if self.results:
            return self.results.pop(0)
        return GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")


class MappingGateway(FakeGateway):
    def __init__(self, levels):
        super().__init__([])
        self.levels = levels

    def _classify(self, action_type: str) -> str:
        return self.levels.get(action_type, "UNKNOWN")


def _csrf_client(app):
    client = TestClient(app, client=("127.0.0.1", 50002))
    token = client.get("/csrf-token").json()["csrf_token"]
    return client, {"X-CSRF-Token": token}


def setup_function() -> None:
    MISSION_STORE.clear()
    MISSION_JOBS.clear()


def test_mission_runner_completes_all_verified_steps() -> None:
    gateway = FakeGateway(
        [
            GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"),
            GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"),
        ]
    )
    runner = MissionRunner(permission_gateway=gateway)
    mission = runner.plan(
        "say two things",
        steps=[
            {"action_type": "respond", "params": {"message": "one"}},
            {"action_type": "respond", "params": {"message": "two"}},
        ],
    )

    import asyncio

    result = asyncio.run(runner.run(mission))

    assert result.status == "completed"
    assert [step.status for step in result.steps] == ["executed", "executed"]
    assert [a.params["message"] for a in gateway.seen] == ["one", "two"]
    assert any(event.type == "completed" for event in result.events)
    assert result.artifacts


def test_mission_runner_stops_on_blocked_step() -> None:
    gateway = FakeGateway(
        [
            GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"),
            GatewayResult(False, "UNKNOWN", False, {}, "Unknown action"),
            GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"),
        ]
    )
    runner = MissionRunner(permission_gateway=gateway)
    mission = runner.plan(
        "stop safely",
        steps=[
            {"action_type": "respond", "params": {"message": "one"}},
            {"action_type": "unknown_action", "params": {}},
            {"action_type": "respond", "params": {"message": "three"}},
        ],
    )

    import asyncio

    result = asyncio.run(runner.run(mission))

    assert result.status == "blocked"
    assert [step.status for step in result.steps] == ["executed", "blocked", "planned"]
    assert len(gateway.seen) == 2


def test_mission_retry_reruns_failed_step_with_budget() -> None:
    gateway = FakeGateway(
        [
            GatewayResult(False, "UNKNOWN", False, {}, "Unknown action"),
            GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto"),
        ]
    )
    runner = MissionRunner(permission_gateway=gateway)
    mission = runner.plan(
        "retry once",
        steps=[{"action_type": "respond", "params": {"message": "retry"}}],
    )

    import asyncio

    first = asyncio.run(runner.run(mission))
    retried = asyncio.run(runner.retry(first))

    assert first.recovery.retry_count == 1
    assert retried.status == "completed"
    assert retried.steps[0].status == "executed"
    assert any(event.type == "retry_scheduled" for event in retried.events)


def test_mission_retry_denied_when_budget_exhausted() -> None:
    gateway = FakeGateway(
        [
            GatewayResult(False, "UNKNOWN", False, {}, "Unknown action"),
            GatewayResult(False, "UNKNOWN", False, {}, "Unknown action again"),
        ]
    )
    runner = MissionRunner(permission_gateway=gateway)
    mission = runner.plan("retry budget")

    import asyncio

    blocked = asyncio.run(runner.run(mission))
    blocked.recovery.max_retries = 0
    denied = asyncio.run(runner.retry(blocked))

    assert denied.status == "blocked"
    assert any(event.type == "retry_denied" for event in denied.events)


def test_mission_rollback_request_creates_review_artifact() -> None:
    runner = MissionRunner(
        permission_gateway=FakeGateway(
            [GatewayResult(True, "GREEN", True, {"status": "ok", "file": "x.txt"}, "Auto")]
        )
    )
    mission = runner.plan("rollback me")

    import asyncio

    completed = asyncio.run(runner.run(mission))
    rolled = runner.request_rollback(completed, reason="check side effects")

    assert rolled.status == "rollback_requested"
    assert rolled.recovery.rollback_status == "requested"
    assert rolled.artifacts[-1].type == "rollback_plan"
    assert any(event.type == "rollback_requested" for event in rolled.events)


def test_mission_store_persists_and_reloads(tmp_path) -> None:
    store_path = tmp_path / "missions.json"
    store = MissionStore(path=store_path)
    runner = MissionRunner(
        permission_gateway=FakeGateway(
            [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
        ),
        store=store,
    )

    mission = runner.plan(
        "persist this",
        steps=[{"action_type": "respond", "params": {"message": "saved"}}],
    )

    reloaded = MissionStore(path=store_path)
    fetched = reloaded.get(mission.id)

    assert store_path.exists()
    assert fetched is not None
    assert fetched.objective == "persist this"
    assert fetched.steps[0].params["message"] == "saved"


def test_mission_store_saves_terminal_status_after_run(tmp_path) -> None:
    store_path = tmp_path / "missions.json"
    store = MissionStore(path=store_path)
    runner = MissionRunner(
        permission_gateway=FakeGateway(
            [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
        ),
        store=store,
    )
    mission = runner.plan("finish me")

    import asyncio

    asyncio.run(runner.run(mission))
    reloaded = MissionStore(path=store_path)
    fetched = reloaded.get(mission.id)

    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.steps[0].status == "executed"
    assert any(event.type == "completed" for event in fetched.events)
    assert fetched.artifacts[0].title == "respond result"


def test_golden_mission_path_executes_persists_timeline_and_artifacts(tmp_path) -> None:
    store_path = tmp_path / "missions.json"
    store = MissionStore(path=store_path)
    gateway = FakeGateway(
        [
            GatewayResult(
                True,
                "GREEN",
                True,
                {
                    "status": "ok",
                    "answer": "golden path complete",
                    "timestamp": "runtime-only",
                    "params": {"should": "not be stored as artifact payload"},
                },
                "Auto",
            )
        ]
    )
    runner = MissionRunner(permission_gateway=gateway, store=store)
    mission = runner.plan(
        "complete the golden path",
        steps=[
            {
                "action_type": "respond",
                "params": {"message": "golden path"},
                "reason": "safe visible mission output",
            }
        ],
        proposed_by="tests.golden_path",
    )

    import asyncio

    completed = asyncio.run(runner.run(mission))
    reloaded = MissionStore(path=store_path)
    persisted = reloaded.get(completed.id)

    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.progress == 1.0
    assert persisted.steps[0].status == "executed"
    assert persisted.steps[0].report["result"]["answer"] == "golden path complete"
    assert gateway.seen[0].action_type == "respond"
    assert gateway.seen[0].params["message"] == "golden path"
    assert [event.type for event in persisted.events] == [
        "planned",
        "run_started",
        "step_started",
        "step_completed",
        "completed",
    ]
    assert persisted.artifacts
    assert persisted.artifacts[0].step_id == persisted.steps[0].id
    assert persisted.artifacts[0].content == {
        "status": "ok",
        "answer": "golden path complete",
    }


def test_mission_job_store_runs_job_and_updates_mission(tmp_path) -> None:
    store = MissionStore(path=tmp_path / "missions.json")
    jobs = MissionJobStore()
    runner = MissionRunner(
        permission_gateway=FakeGateway(
            [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
        ),
        store=store,
    )
    mission = runner.plan("background me")
    job = jobs._jobs.setdefault(
        "job-test",
        MissionJob(
            id="job-test",
            mission_id=mission.id,
            status="queued",
            dry_run=False,
            created_at=MissionRunner._now(),
            updated_at=MissionRunner._now(),
        ),
    )

    import asyncio

    result_job = asyncio.run(jobs.run_job(job.id, runner))
    fetched = store.get(mission.id)

    assert result_job.status == "completed"
    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.progress == 1.0


def test_missions_api_plan_and_dry_run() -> None:
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
    )
    client, headers = _csrf_client(app)

    plan_response = client.post(
        "/missions/plan",
        json={"objective": "hello mission"},
        headers=headers,
    )
    assert plan_response.status_code == 200
    mission = plan_response.json()["mission"]
    assert mission["steps"][0]["action_type"] == "respond"

    run_response = client.post(
        "/missions/run",
        json={"objective": "hello mission", "dry_run": True},
        headers=headers,
    )
    assert run_response.status_code == 200
    body = run_response.json()
    assert body["status"] == "planned"
    assert body["mission"]["steps"][0]["status"] == "planned"


def test_objective_decomposer_maps_safe_objective() -> None:
    result = ObjectiveDecomposer().decompose(
        "check weather in Kolkata and search vector database architecture",
    )

    assert result["status"] == "decomposed"
    assert [step["action_type"] for step in result["steps"]] == [
        "check_weather",
        "search_web",
    ]
    assert result["steps"][0]["params"]["location"] == "Kolkata"


def test_objective_decomposer_requires_review_for_risky_objective() -> None:
    result = ObjectiveDecomposer().decompose("delete old files and deploy production")

    assert result["status"] == "needs_review"
    assert result["review_required"] is True
    assert result["steps"][0]["action_type"] == "respond"
    assert result["steps"][0]["requires_review"] is True


def test_mission_plan_advisor_uses_local_llm_candidates_safely() -> None:
    def fake_chat(**kwargs):
        return """
        {"steps":[
          {"action_type":"respond","params":{"message":"hello"},"reason":"safe reply","confidence":0.91},
          {"action_type":"unknown_tool","params":{},"reason":"needs gate","confidence":0.86}
        ]}
        """

    advisor = MissionPlanAdvisor(
        permission_gateway=MappingGateway({"respond": "GREEN"}),
        chat_fn=fake_chat,
        model="vector-test",
    )

    result = advisor.advise("say hello then use unknown tool")

    assert result["status"] == "llm_decomposed_with_review"
    assert result["planner"]["source"] == "local_llm"
    assert result["planner"]["fallback_used"] is False
    assert result["steps"][0]["action_type"] == "respond"
    assert result["steps"][0]["requires_review"] is False
    assert result["steps"][1]["safety_level"] == "UNKNOWN"
    assert result["steps"][1]["requires_review"] is True


def test_mission_plan_advisor_falls_back_when_model_unavailable() -> None:
    advisor = MissionPlanAdvisor(
        permission_gateway=FakeGateway([]),
        chat_fn=lambda **kwargs: "",
        model="vector-test",
    )

    result = advisor.advise("check weather in Kolkata")

    assert result["planner"]["fallback_used"] is True
    assert result["steps"][0]["action_type"] == "check_weather"


def test_missions_api_decompose_and_plan_with_decomposition(monkeypatch) -> None:
    monkeypatch.setattr(
        MissionPlanAdvisor,
        "_call_model",
        lambda self, objective, max_steps: "",
    )
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
    )
    client, headers = _csrf_client(app)

    decompose_response = client.post(
        "/missions/decompose",
        json={"objective": "set a timer for 2 minutes"},
        headers=headers,
    )
    assert decompose_response.status_code == 200
    body = decompose_response.json()
    assert body["decomposition"]["steps"][0]["action_type"] == "set_timer"
    assert body["decomposition"]["steps"][0]["params"]["duration_sec"] == 120

    plan_response = client.post(
        "/missions/plan",
        json={"objective": "search local llm routing", "decompose": True},
        headers=headers,
    )
    mission = plan_response.json()["mission"]
    assert mission["decomposition"]["status"] == "decomposed"
    assert mission["steps"][0]["action_type"] == "search_web"

    llm_plan_response = client.post(
        "/missions/plan",
        json={"objective": "check weather in Kolkata", "decompose": True, "llm_plan": True},
        headers=headers,
    )
    llm_mission = llm_plan_response.json()["mission"]
    assert llm_mission["decomposition"]["planner"]["fallback_used"] is True
    assert llm_mission["steps"][0]["action_type"] == "check_weather"


def test_missions_api_advise_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        MissionPlanAdvisor,
        "_call_model",
        lambda self, objective, max_steps: (
            '{"steps":[{"action_type":"respond","params":{"message":"ok"},'
            '"reason":"api test","confidence":0.9}]}'
        ),
    )
    app = create_app()
    app.state.permission_gateway = FakeGateway([])
    client, headers = _csrf_client(app)

    response = client.post(
        "/missions/advise",
        json={"objective": "search local llm routing"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert "planner" in body["decomposition"]
    assert body["decomposition"]["planner"]["source"] == "local_llm"
    assert body["decomposition"]["steps"]


def test_missions_api_run_async_returns_job() -> None:
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
    )
    client, headers = _csrf_client(app)

    response = client.post(
        "/missions/run-async",
        json={"objective": "answer this", "dry_run": True},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job"]["id"]
    assert body["mission"]["job_id"] == body["job"]["id"]

    job_response = client.get(f"/missions/jobs/{body['job']['id']}")
    assert job_response.status_code == 200
    assert job_response.json()["job"]["mission_id"] == body["mission"]["id"]


def test_missions_api_timeline_and_artifacts() -> None:
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        [GatewayResult(True, "GREEN", True, {"status": "ok", "answer": "done"}, "Auto")]
    )
    client, headers = _csrf_client(app)

    created = client.post(
        "/missions/run",
        json={"objective": "timeline me"},
        headers=headers,
    ).json()["mission"]

    timeline = client.get(f"/missions/{created['id']}/timeline")
    artifacts = client.get(f"/missions/{created['id']}/artifacts")

    assert timeline.status_code == 200
    assert artifacts.status_code == 200
    assert any(event["type"] == "completed" for event in timeline.json()["events"])
    assert artifacts.json()["count"] >= 1
    assert artifacts.json()["artifacts"][0]["content"]["answer"] == "done"


def test_missions_api_retry_and_rollback() -> None:
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        [
            GatewayResult(False, "UNKNOWN", False, {}, "Unknown action"),
            GatewayResult(True, "GREEN", True, {"status": "ok", "answer": "retried"}, "Auto"),
        ]
    )
    client, headers = _csrf_client(app)

    created = client.post(
        "/missions/run",
        json={"objective": "recover me"},
        headers=headers,
    ).json()["mission"]

    retry_response = client.post(
        f"/missions/{created['id']}/retry",
        json={},
        headers=headers,
    )
    assert retry_response.status_code == 200
    retried = retry_response.json()["mission"]
    assert retried["recovery"]["retry_count"] == 1

    rollback_response = client.post(
        f"/missions/{created['id']}/rollback",
        json={"reason": "verify side effects"},
        headers=headers,
    )
    assert rollback_response.status_code == 200
    rolled = rollback_response.json()["mission"]
    assert rolled["status"] == "rollback_requested"
    assert rolled["artifacts"][-1]["type"] == "rollback_plan"


def test_missions_api_lists_and_fetches_mission() -> None:
    app = create_app()
    app.state.permission_gateway = FakeGateway(
        [GatewayResult(True, "GREEN", True, {"status": "ok"}, "Auto")]
    )
    client, headers = _csrf_client(app)

    created = client.post(
        "/missions/plan",
        json={"objective": "track me"},
        headers=headers,
    ).json()["mission"]

    listed = client.get("/missions").json()
    fetched = client.get(f"/missions/{created['id']}").json()

    assert listed["count"] >= 1
    assert fetched["mission"]["id"] == created["id"]
