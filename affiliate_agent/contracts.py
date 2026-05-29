from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArtifactRecord:
    artifact_type: str
    uri: str

    def to_dict(self) -> dict[str, str]:
        return {"artifact_type": self.artifact_type, "uri": self.uri}


@dataclass
class PlatformAdapterResult:
    success: bool
    platform_campaign_id: str
    request_id: str
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "platform_campaign_id": self.platform_campaign_id,
            "request_id": self.request_id,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "error": self.error,
        }


@dataclass
class TaskContract:
    task_type: str
    platform: str
    account_id: str
    idempotency_key: str
    payload: dict[str, Any]
    priority: str = "normal"
    requested_by: str = "agent"
    approval_required: bool = True
    approval_status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "platform": self.platform,
            "account_id": self.account_id,
            "priority": self.priority,
            "requested_by": self.requested_by,
            "idempotency_key": self.idempotency_key,
            "approval_required": self.approval_required,
            "approval_status": self.approval_status,
            "safety_profile": {
                "max_spend_change_pct": 20,
                "daily_spend_cap": 500,
                "ops_per_hour_cap": 30,
                "rollback_enabled": True,
            },
            "payload": self.payload,
            "prechecks": [
                "session_valid",
                "policy_scan_passed",
                "budget_within_limit",
                "duplicate_task_check",
            ],
            "execution": {
                "status": "queued",
                "attempt": 0,
                "max_attempts": 3,
                "last_error": None,
                "artifacts": {
                    "screenshots": [],
                    "dom_snapshots": [],
                    "api_logs": [],
                    "traces": [],
                },
            },
            "outcome": {
                "kpi_window": "2h",
                "delta": {
                    "spend": 0,
                    "clicks": 0,
                    "cvr": 0,
                    "commission": 0,
                    "net_profit": 0,
                },
                "reward": 0,
                "confidence": 0,
            },
        }
