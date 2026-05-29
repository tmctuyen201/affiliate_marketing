from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from affiliate_agent.policies import Decision, PolicyGate, TaskGenerator, ApprovalRouter


@dataclass
class DecisionContext:
    account_id: str
    platform: str
    campaign_id: str
    daily_spend_cap: float
    current_budget: float
    baseline_cvr: float
    current_cvr: float
    clicks: int
    cooldown_active: bool
    current_epc: float
    epc_p75: float
    stable_windows: int
    fatigue_baseline_ctr: float
    current_ctr: float
    refunds_baseline_rate: float
    current_refund_rate: float
    complaints_anomaly: bool
    segments: dict[str, dict[str, float]]
    daily_spend: float
    per_campaign_cap: float
    spend_change_today_pct: float
    max_step_change_pct: float
    validated_strategies: set[str]
    risk_category: str
    sensitive_vertical: bool
    critical_daily_budget_threshold: float
    requested_by: str
    creative_rotation_count_today: int = 0
    creative_candidates: list[str] = field(default_factory=list)
    current_creative_id: str | None = None
    sku_id: str | None = None


class DecisionEngine:
    def __init__(self, *, generator: TaskGenerator, gate: PolicyGate, router: ApprovalRouter):
        self.generator = generator
        self.gate = gate
        self.router = router

    def decide(self, context: DecisionContext) -> Decision:
        decision = self._select_rule(context)
        decision = self.gate.evaluate(decision, context)
        return self.gate.apply_approval(decision, context, self.router)

    def _select_rule(self, context: DecisionContext) -> Decision:
        if self._should_pause_for_refunds(context):
            return Decision(
                "refund_pause",
                "refund_or_complaint_risk",
                self.generator.build_pause_task(
                    account_id=context.account_id,
                    platform=context.platform,
                    campaign_id=context.campaign_id,
                    sku_id=context.sku_id,
                    daily_spend_cap=context.daily_spend_cap,
                ),
            )
        if self._should_cut_underperformance(context):
            return Decision(
                "underperformance_cut",
                "cvr_drop_over_threshold",
                self.generator.build_budget_task(
                    account_id=context.account_id,
                    platform=context.platform,
                    campaign_id=context.campaign_id,
                    amount=context.current_budget * 0.8,
                    daily_spend_cap=context.daily_spend_cap,
                ),
            )
        if self._should_scale_winner(context):
            return Decision(
                "winner_scale",
                "epc_above_p75_stable",
                self.generator.build_budget_task(
                    account_id=context.account_id,
                    platform=context.platform,
                    campaign_id=context.campaign_id,
                    amount=context.current_budget * 1.1,
                    daily_spend_cap=context.daily_spend_cap,
                ),
            )
        if self._should_rotate_creative(context):
            next_creative = context.creative_candidates[0]
            return Decision(
                "creative_fatigue_rotation",
                "ctr_decay_over_threshold",
                self.generator.build_rotation_task(
                    account_id=context.account_id,
                    platform=context.platform,
                    campaign_id=context.campaign_id,
                    current_creative_id=context.current_creative_id or "unknown",
                    next_creative_id=next_creative,
                    daily_spend_cap=context.daily_spend_cap,
                ),
            )
        if self._should_reallocate_segment(context):
            from_segment, to_segment = self._find_segment_shift(context.segments)
            return Decision(
                "segment_reallocation",
                "segment_cvr_gap_persistent",
                self.generator.build_budget_task(
                    account_id=context.account_id,
                    platform=context.platform,
                    campaign_id=context.campaign_id,
                    amount=context.current_budget,
                    daily_spend_cap=context.daily_spend_cap,
                    allocation={"from_segment": from_segment, "to_segment": to_segment, "shift_pct": 15},
                ),
            )
        return Decision("no_action", "no_rule_triggered", None, blocked_reason="no_candidate_action")

    def _should_cut_underperformance(self, context: DecisionContext) -> bool:
        return (
            "underperformance_cut" in context.validated_strategies
            and context.clicks >= 100
            and context.current_cvr < context.baseline_cvr * 0.75
        )

    def _should_scale_winner(self, context: DecisionContext) -> bool:
        return (
            "winner_scale" in context.validated_strategies
            and context.current_epc > context.epc_p75
            and context.stable_windows >= 3
        )

    def _should_rotate_creative(self, context: DecisionContext) -> bool:
        return (
            "creative_fatigue_rotation" in context.validated_strategies
            and context.fatigue_baseline_ctr > 0
            and context.current_ctr < context.fatigue_baseline_ctr * 0.7
            and bool(context.creative_candidates)
        )

    def _should_pause_for_refunds(self, context: DecisionContext) -> bool:
        return (
            "refund_pause" in context.validated_strategies
            and (context.current_refund_rate >= context.refunds_baseline_rate * 2 or context.complaints_anomaly)
        )

    def _should_reallocate_segment(self, context: DecisionContext) -> bool:
        if "segment_reallocation" not in context.validated_strategies or len(context.segments) < 2:
            return False
        low, high = self._find_segment_shift(context.segments)
        return (
            context.segments[low]["clicks"] >= 200
            and context.segments[high]["clicks"] >= 200
            and context.segments[low]["cvr"] < context.segments[high]["cvr"]
        )

    def _find_segment_shift(self, segments: dict[str, dict[str, float]]) -> tuple[str, str]:
        ranked = sorted(segments.items(), key=lambda item: item[1]["cvr"])
        return ranked[0][0], ranked[-1][0]
