from dataclasses import dataclass
from enum import Enum


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILING = "failing"


@dataclass
class ServiceHealth:
    name: str
    status: HealthStatus
    reason: str | None = None


@dataclass
class Logger:
    extra: dict[str, str]


def build_logger(service: str) -> Logger:
    return Logger(extra={"service": service})


def build_trace_context(service: str, task_id: str) -> dict[str, str]:
    return {"service.name": service, "task.id": task_id}


def readiness_report(service: str, checks: list[ServiceHealth]) -> dict[str, object]:
    status = "ok"
    if any(check.status == HealthStatus.FAILING for check in checks):
        status = "failing"
    elif any(check.status == HealthStatus.DEGRADED for check in checks):
        status = "degraded"
    return {
        "service": service,
        "status": status,
        "checks": [
            {"name": check.name, "status": check.status.value, "reason": check.reason}
            for check in checks
        ],
    }
