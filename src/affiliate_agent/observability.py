from dataclasses import dataclass
from enum import StrEnum


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAIL = "fail"


@dataclass(frozen=True)
class ServiceHealth:
    dependency: str
    status: HealthStatus
    reason: str | None = None


@dataclass(frozen=True)
class ServiceLogger:
    name: str
    extra: dict[str, str]


def readiness_report(service: str, checks: list[ServiceHealth]) -> dict:
    overall = HealthStatus.OK
    if any(check.status == HealthStatus.FAIL for check in checks):
        overall = HealthStatus.FAIL
    elif any(check.status == HealthStatus.DEGRADED for check in checks):
        overall = HealthStatus.DEGRADED

    return {
        "service": service,
        "status": overall.value,
        "checks": [
            {
                "dependency": check.dependency,
                "status": check.status.value,
                "reason": check.reason,
            }
            for check in checks
        ],
    }


def build_logger(service: str) -> ServiceLogger:
    return ServiceLogger(name=service, extra={"service": service})


def build_trace_context(service: str, task_id: str) -> dict[str, str]:
    return {
        "service.name": service,
        "task.id": task_id,
    }
