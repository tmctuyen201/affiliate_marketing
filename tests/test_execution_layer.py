from fastapi.testclient import TestClient

from affiliate_agent.api import create_app
from affiliate_agent.contracts import ArtifactRecord, PlatformAdapterResult, TaskContract
from affiliate_agent.services.executor import (
    ApiUnavailableError,
    ExecutionService,
    PermanentExecutionError,
    TransientExecutionError,
)


class FakeAdapter:
    def __init__(self, responses=None, session_valid=True):
        self.responses = list(responses or [])
        self.session_valid = session_valid
        self.calls = []

    def create_campaign(self, task_payload):
        self.calls.append(("create_campaign", task_payload.idempotency_key))
        return self._next_response()

    def update_budget(self, task_payload):
        self.calls.append(("update_budget", task_payload.idempotency_key))
        return self._next_response()

    def pause_campaign(self, task_payload):
        self.calls.append(("pause_campaign", task_payload.idempotency_key))
        return self._next_response()

    def rotate_creative(self, task_payload):
        self.calls.append(("rotate_creative", task_payload.idempotency_key))
        return self._next_response()

    def get_campaign_state(self, account_id, campaign_id):
        return {"account_id": account_id, "campaign_id": campaign_id}

    def validate_session(self, account_id):
        return self.session_valid

    def _next_response(self):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeBrowserWorker:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, task_payload):
        self.calls.append(task_payload.idempotency_key)
        return self.result


def build_task(idempotency_key="idem-1", task_type="update_budget"):
    return TaskContract(
        task_type=task_type,
        platform="tiktok",
        account_id="acct-1",
        idempotency_key=idempotency_key,
        payload={"budget": {"amount": 100}},
    )


def build_result(request_id="req-1"):
    return PlatformAdapterResult(
        success=True,
        platform_campaign_id="cmp-1",
        request_id=request_id,
        artifacts=[ArtifactRecord("api_response", "memory://response")],
    )


def test_execution_service_uses_api_first_adapter_path():
    adapter = FakeAdapter([build_result()])
    service = ExecutionService(adapters={"tiktok": adapter})

    record = service.execute(build_task())

    assert record.status == "succeeded"
    assert record.adapter_kind == "api"
    assert record.attempt_count == 1
    assert record.result.to_dict()["request_id"] == "req-1"
    assert adapter.calls == [("update_budget", "idem-1")]


def test_execution_service_falls_back_to_browser_worker_when_api_unavailable():
    adapter = FakeAdapter([ApiUnavailableError("api unavailable")])
    browser = FakeBrowserWorker(build_result(request_id="browser-1"))
    service = ExecutionService(adapters={"tiktok": adapter}, browser_worker=browser)

    record = service.execute(build_task())

    assert record.status == "succeeded"
    assert record.adapter_kind == "browser"
    assert record.result.to_dict()["request_id"] == "browser-1"
    assert browser.calls == ["idem-1"]


def test_execution_service_retries_transient_failures_with_same_idempotency_key():
    adapter = FakeAdapter(
        [
            TransientExecutionError("timeout"),
            TransientExecutionError("timeout"),
            build_result(request_id="req-3"),
        ]
    )
    service = ExecutionService(adapters={"tiktok": adapter}, max_attempts=3)

    record = service.execute(build_task())

    assert record.status == "succeeded"
    assert record.attempt_count == 3
    assert record.retry_delays == [1, 2]
    assert adapter.calls == [
        ("update_budget", "idem-1"),
        ("update_budget", "idem-1"),
        ("update_budget", "idem-1"),
    ]


def test_execution_service_moves_task_to_dlq_after_max_attempts():
    adapter = FakeAdapter([TransientExecutionError("timeout")] * 3)
    service = ExecutionService(adapters={"tiktok": adapter}, max_attempts=3)

    record = service.execute(build_task())

    assert record.status == "dead_letter"
    assert record.attempt_count == 3
    assert record.last_error == "timeout"
    assert service.dead_letters()[0].idempotency_key == "idem-1"


def test_execution_service_does_not_retry_permanent_failures():
    adapter = FakeAdapter([PermanentExecutionError("invalid payload")])
    service = ExecutionService(adapters={"tiktok": adapter}, max_attempts=3)

    record = service.execute(build_task())

    assert record.status == "failed"
    assert record.attempt_count == 1
    assert record.last_error == "invalid payload"


def test_execution_service_returns_cached_record_for_duplicate_idempotency_key():
    adapter = FakeAdapter([build_result(request_id="req-1")])
    service = ExecutionService(adapters={"tiktok": adapter})
    task = build_task(idempotency_key="idem-dup")

    first = service.execute(task)
    second = service.execute(task)

    assert first is second
    assert adapter.calls == [("update_budget", "idem-dup")]


def test_execute_endpoint_returns_execution_record_payload():
    adapter = FakeAdapter([build_result(request_id="req-endpoint")])
    app = create_app(execution_service=ExecutionService(adapters={"tiktok": adapter}))
    client = TestClient(app)

    response = client.post(
        "/execution/tasks",
        json={
            "task_type": "update_budget",
            "platform": "tiktok",
            "account_id": "acct-1",
            "idempotency_key": "idem-endpoint",
            "payload": {"budget": {"amount": 150}},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["adapter_kind"] == "api"
    assert response.json()["result"]["request_id"] == "req-endpoint"
