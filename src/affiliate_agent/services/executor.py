from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from affiliate_agent.contracts import PlatformAdapterResult, TaskContract

SERVICE_NAME = "executor"


class TransientExecutionError(Exception):
    pass


class PermanentExecutionError(Exception):
    pass


class ApiUnavailableError(Exception):
    pass


class PlatformAdapter(Protocol):
    def create_campaign(self, task_payload: TaskContract) -> PlatformAdapterResult: ...
    def update_budget(self, task_payload: TaskContract) -> PlatformAdapterResult: ...
    def pause_campaign(self, task_payload: TaskContract) -> PlatformAdapterResult: ...
    def rotate_creative(self, task_payload: TaskContract) -> PlatformAdapterResult: ...
    def get_campaign_state(self, account_id: str, campaign_id: str) -> dict[str, object]: ...
    def validate_session(self, account_id: str) -> bool: ...


class BrowserWorker(Protocol):
    def run(self, task_payload: TaskContract) -> PlatformAdapterResult: ...


@dataclass
class ExecutionRecord:
    task: TaskContract
    status: str
    adapter_kind: str | None
    attempt_count: int
    result: PlatformAdapterResult | None = None
    last_error: str | None = None
    retry_delays: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "status": self.status,
            "adapter_kind": self.adapter_kind,
            "attempt_count": self.attempt_count,
            "result": None if self.result is None else self.result.to_dict(),
            "last_error": self.last_error,
            "retry_delays": list(self.retry_delays),
        }


class ExecutionService:
    def __init__(
        self,
        adapters: dict[str, PlatformAdapter],
        browser_worker: BrowserWorker | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._adapters = adapters
        self._browser_worker = browser_worker
        self._max_attempts = max_attempts
        self._records: dict[str, ExecutionRecord] = {}
        self._dead_letters: list[TaskContract] = []

    def execute(self, task: TaskContract) -> ExecutionRecord:
        cached = self._records.get(task.idempotency_key)
        if cached is not None:
            return cached

        adapter = self._adapters[task.platform]
        if not adapter.validate_session(task.account_id):
            record = ExecutionRecord(
                task=task,
                status="failed",
                adapter_kind="api",
                attempt_count=1,
                last_error="session invalid",
            )
            self._records[task.idempotency_key] = record
            return record

        operation = self._operation_name(task.task_type)
        retry_delays: list[int] = []

        for attempt in range(1, self._max_attempts + 1):
            try:
                result = getattr(adapter, operation)(task)
                record = ExecutionRecord(
                    task=task,
                    status="succeeded",
                    adapter_kind="api",
                    attempt_count=attempt,
                    result=result,
                    retry_delays=retry_delays,
                )
                self._records[task.idempotency_key] = record
                return record
            except ApiUnavailableError:
                if self._browser_worker is None:
                    record = ExecutionRecord(
                        task=task,
                        status="failed",
                        adapter_kind="api",
                        attempt_count=attempt,
                        last_error="api unavailable",
                        retry_delays=retry_delays,
                    )
                    self._records[task.idempotency_key] = record
                    return record
                result = self._browser_worker.run(task)
                record = ExecutionRecord(
                    task=task,
                    status="succeeded",
                    adapter_kind="browser",
                    attempt_count=attempt,
                    result=result,
                    retry_delays=retry_delays,
                )
                self._records[task.idempotency_key] = record
                return record
            except PermanentExecutionError as exc:
                record = ExecutionRecord(
                    task=task,
                    status="failed",
                    adapter_kind="api",
                    attempt_count=attempt,
                    last_error=str(exc),
                    retry_delays=retry_delays,
                )
                self._records[task.idempotency_key] = record
                return record
            except TransientExecutionError as exc:
                if attempt == self._max_attempts:
                    self._dead_letters.append(task)
                    record = ExecutionRecord(
                        task=task,
                        status="dead_letter",
                        adapter_kind="api",
                        attempt_count=attempt,
                        last_error=str(exc),
                        retry_delays=retry_delays,
                    )
                    self._records[task.idempotency_key] = record
                    return record
                retry_delays.append(2 ** (attempt - 1))

        raise RuntimeError("unreachable")

    def dead_letters(self) -> list[TaskContract]:
        return list(self._dead_letters)

    @staticmethod
    def _operation_name(task_type: str) -> str:
        operations = {
            "create_campaign": "create_campaign",
            "update_budget": "update_budget",
            "pause_campaign": "pause_campaign",
            "rotate_creative": "rotate_creative",
        }
        return operations[task_type]
