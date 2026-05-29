from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from affiliate_agent.contracts import TaskContract

DEFAULT_PRECHECKS = [
    "session_valid",
    "policy_scan_passed",
    "budget_within_limit",
    "duplicate_task_check",
]


@dataclass
class Decision:
    rule_name: str
    reason: str
    task: dict[str, Any] | None
    blocked_reason: str | None = None
    approval_route: str | None = None


class TaskGenerator:
    def build_budget_task(
        self,
        *,
        account_id: str,
        platform: str,
        campaign_id: str,
        amount: float,
        daily_spend_cap: float,
        critical_daily_budget_threshold: float,
        allocation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = TaskContract(
            task_type="update_budget",
            platform=platform,
            account_id=account_id,
            idempotency_key=f"{campaign_id}:update_budget:{round(amount, 2)}",
            payload={
                "campaign_id": campaign_id,
                "budget": {
                    "amount": round(amount, 2),
                    "currency": "USD",
                    "type": "daily",
                },
            },
        ).to_dict()
        task.update(self._base_task_fields(account_id, platform))
        task["safety_profile"]["daily_spend_cap"] = daily_spend_cap
        task["safety_profile"]["critical_daily_budget_threshold"] = critical_daily_budget_threshold
        if allocation:
            task["payload"]["allocation"] = allocation
        return task

    def build_rotation_task(
        self,
        *,
        account_id: str,
        platform: str,
        campaign_id: str,
        current_creative_id: str,
        next_creative_id: str,
        daily_spend_cap: float,
        critical_daily_budget_threshold: float,
    ) -> dict[str, Any]:
        task = TaskContract(
            task_type="rotate_creative",
            platform=platform,
            account_id=account_id,
            idempotency_key=f"{campaign_id}:rotate_creative:{next_creative_id}",
            payload={
                "campaign_id": campaign_id,
                "creative": {
                    "current_asset_id": current_creative_id,
                    "asset_id": next_creative_id,
                },
            },
        ).to_dict()
        task.update(self._base_task_fields(account_id, platform))
        task["safety_profile"]["daily_spend_cap"] = daily_spend_cap
        task["safety_profile"]["critical_daily_budget_threshold"] = critical_daily_budget_threshold
        return task

    def build_pause_task(
        self,
        *,
        account_id: str,
        platform: str,
        campaign_id: str,
        sku_id: str | None,
        daily_spend_cap: float,
        critical_daily_budget_threshold: float,
    ) -> dict[str, Any]:
        task = TaskContract(
            task_type="pause_campaign",
            platform=platform,
            account_id=account_id,
            idempotency_key=f"{campaign_id}:pause",
            payload={"campaign_id": campaign_id},
        ).to_dict()
        task.update(self._base_task_fields(account_id, platform))
        task["safety_profile"]["daily_spend_cap"] = daily_spend_cap
        task["safety_profile"]["critical_daily_budget_threshold"] = critical_daily_budget_threshold
        task["payload"]["pause_scope"] = {"campaign_id": campaign_id, "sku_id": sku_id}
        return task

    def _base_task_fields(self, account_id: str, platform: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        return {
            "task_id": str(uuid4()),
            "account_id": account_id,
            "platform": platform,
            "priority": "normal",
            "requested_by": "agent",
            "prechecks": list(DEFAULT_PRECHECKS),
            "timestamps": {
                "created_at": now,
                "approved_at": None,
                "started_at": None,
                "finished_at": None,
            },
        }


class ApprovalRouter:
    def route(
        self,
        task: dict[str, Any],
        *,
        risk_category: str,
        sensitive_vertical: bool,
        requested_by: str,
    ) -> str | None:
        if task["task_type"] == "pause_campaign":
            return "manual"
        if task["task_type"] == "rotate_creative":
            return None
        if task["task_type"] == "update_budget" and "allocation" in task["payload"]:
            return "manual"
        budget = task["payload"].get("budget", {})
        current = task["payload"].get("current_budget", budget.get("amount", 0))
        amount = budget.get("amount", 0)
        delta_pct = 0 if not current else abs(amount - current) / current * 100
        critical_threshold = task["safety_profile"].get("critical_daily_budget_threshold", float("inf"))
        daily_cap = task["safety_profile"]["daily_spend_cap"]
        if delta_pct > 30 or daily_cap > critical_threshold:
            return "dual"
        if amount < current:
            return None
        if delta_pct >= 10 or sensitive_vertical or risk_category != "low" or requested_by == "human":
            return "manual"
        return None


class PolicyGate:
    def __init__(self, max_creative_rotations_per_day: int = 3):
        self.max_creative_rotations_per_day = max_creative_rotations_per_day

    def evaluate(self, decision: Decision, context: Any) -> Decision:
        if decision.task is None:
            return decision
        if decision.rule_name == "underperformance_cut" and context.cooldown_active:
            return Decision(decision.rule_name, decision.reason, None, blocked_reason="cooldown_active")
        if (
            decision.rule_name == "creative_fatigue_rotation"
            and context.creative_rotation_count_today >= self.max_creative_rotations_per_day
        ):
            return Decision(
                decision.rule_name,
                decision.reason,
                None,
                blocked_reason="creative_rotation_cap_reached",
            )
        budget = decision.task["payload"].get("budget")
        if budget:
            new_amount = budget["amount"]
            if new_amount > context.per_campaign_cap:
                return Decision(decision.rule_name, decision.reason, None, blocked_reason="per_campaign_cap_exceeded")
            projected_daily_spend = context.daily_spend - context.current_budget + new_amount
            if projected_daily_spend > context.daily_spend_cap:
                return Decision(decision.rule_name, decision.reason, None, blocked_reason="daily_spend_cap_exceeded")
            delta_pct = abs(new_amount - context.current_budget) / context.current_budget * 100
            if delta_pct > context.max_step_change_pct:
                return Decision(decision.rule_name, decision.reason, None, blocked_reason="max_step_change_exceeded")
            decision.task["payload"]["current_budget"] = context.current_budget
        return decision

    def apply_approval(self, decision: Decision, context: Any, router: ApprovalRouter) -> Decision:
        if decision.task is None:
            return decision
        route = router.route(
            decision.task,
            risk_category=context.risk_category,
            sensitive_vertical=context.sensitive_vertical,
            requested_by=context.requested_by,
        )
        if route is None:
            decision.task["approval_required"] = False
            decision.task["approval_status"] = "not_required"
            return Decision(decision.rule_name, decision.reason, decision.task, approval_route=None)
        decision.task["approval_required"] = True
        decision.task["approval_status"] = "pending"
        return Decision(decision.rule_name, decision.reason, decision.task, approval_route=route)
