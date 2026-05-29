from affiliate_agent.audit import AuditLineageWriter
from affiliate_agent.decisioning import DecisionContext, DecisionEngine
from affiliate_agent.policies import ApprovalRouter, PolicyGate, TaskGenerator


def test_underperformance_cut_generates_bounded_budget_reduction_task():
    generator = TaskGenerator()
    gate = PolicyGate()
    router = ApprovalRouter()
    engine = DecisionEngine(generator=generator, gate=gate, router=router)

    context = DecisionContext(
        account_id="acct-1",
        platform="tiktok",
        campaign_id="cmp-1",
        daily_spend_cap=500,
        current_budget=100,
        baseline_cvr=0.04,
        current_cvr=0.028,
        clicks=250,
        cooldown_active=False,
        current_epc=1.0,
        epc_p75=1.5,
        stable_windows=1,
        fatigue_baseline_ctr=0.02,
        current_ctr=0.018,
        refunds_baseline_rate=0.03,
        current_refund_rate=0.03,
        complaints_anomaly=False,
        segments={},
        daily_spend=120,
        per_campaign_cap=150,
        spend_change_today_pct=0,
        max_step_change_pct=20,
        validated_strategies={"underperformance_cut"},
        risk_category="low",
        sensitive_vertical=False,
        critical_daily_budget_threshold=1000,
        requested_by="agent",
    )

    decision = engine.decide(context)

    assert decision.rule_name == "underperformance_cut"
    assert decision.task["task_type"] == "update_budget"
    assert decision.task["payload"]["budget"] == {"amount": 80.0, "currency": "USD", "type": "daily"}
    assert decision.task["approval_status"] == "not_required"
    assert decision.task["prechecks"] == [
        "session_valid",
        "policy_scan_passed",
        "budget_within_limit",
        "duplicate_task_check",
    ]


def test_winner_scale_routes_manual_approval_above_auto_threshold():
    generator = TaskGenerator()
    gate = PolicyGate()
    router = ApprovalRouter()
    engine = DecisionEngine(generator=generator, gate=gate, router=router)

    context = DecisionContext(
        account_id="acct-2",
        platform="facebook",
        campaign_id="cmp-2",
        daily_spend_cap=800,
        current_budget=200,
        baseline_cvr=0.03,
        current_cvr=0.03,
        clicks=500,
        cooldown_active=False,
        current_epc=2.4,
        epc_p75=2.0,
        stable_windows=3,
        fatigue_baseline_ctr=0.03,
        current_ctr=0.03,
        refunds_baseline_rate=0.02,
        current_refund_rate=0.02,
        complaints_anomaly=False,
        segments={},
        daily_spend=200,
        per_campaign_cap=500,
        spend_change_today_pct=0,
        max_step_change_pct=20,
        validated_strategies={"winner_scale"},
        risk_category="low",
        sensitive_vertical=False,
        critical_daily_budget_threshold=1000,
        requested_by="agent",
    )

    decision = engine.decide(context)

    assert decision.rule_name == "winner_scale"
    assert decision.task["payload"]["budget"]["amount"] == 220.0
    assert decision.task["approval_required"] is True
    assert decision.task["approval_status"] == "pending"
    assert decision.approval_route == "manual"


def test_creative_fatigue_rotation_respects_daily_rotation_limit():
    generator = TaskGenerator()
    gate = PolicyGate(max_creative_rotations_per_day=2)
    router = ApprovalRouter()
    engine = DecisionEngine(generator=generator, gate=gate, router=router)

    context = DecisionContext(
        account_id="acct-3",
        platform="youtube",
        campaign_id="cmp-3",
        daily_spend_cap=300,
        current_budget=100,
        baseline_cvr=0.05,
        current_cvr=0.05,
        clicks=400,
        cooldown_active=False,
        current_epc=1.2,
        epc_p75=2.0,
        stable_windows=0,
        fatigue_baseline_ctr=0.02,
        current_ctr=0.013,
        refunds_baseline_rate=0.01,
        current_refund_rate=0.01,
        complaints_anomaly=False,
        segments={},
        daily_spend=80,
        per_campaign_cap=200,
        spend_change_today_pct=0,
        max_step_change_pct=20,
        validated_strategies={"creative_fatigue_rotation"},
        risk_category="low",
        sensitive_vertical=False,
        critical_daily_budget_threshold=1000,
        requested_by="agent",
        creative_rotation_count_today=2,
        creative_candidates=["creative-b"],
        current_creative_id="creative-a",
    )

    decision = engine.decide(context)

    assert decision.rule_name == "creative_fatigue_rotation"
    assert decision.blocked_reason == "creative_rotation_cap_reached"
    assert decision.task is None


def test_refund_pause_requires_manual_unpause_guard_and_audit_lineage():
    generator = TaskGenerator()
    gate = PolicyGate()
    router = ApprovalRouter()
    engine = DecisionEngine(generator=generator, gate=gate, router=router)

    context = DecisionContext(
        account_id="acct-4",
        platform="tiktok",
        campaign_id="cmp-4",
        daily_spend_cap=500,
        current_budget=120,
        baseline_cvr=0.05,
        current_cvr=0.05,
        clicks=300,
        cooldown_active=False,
        current_epc=1.0,
        epc_p75=2.0,
        stable_windows=0,
        fatigue_baseline_ctr=0.02,
        current_ctr=0.02,
        refunds_baseline_rate=0.02,
        current_refund_rate=0.06,
        complaints_anomaly=True,
        segments={},
        daily_spend=140,
        per_campaign_cap=250,
        spend_change_today_pct=0,
        max_step_change_pct=20,
        validated_strategies={"refund_pause"},
        risk_category="low",
        sensitive_vertical=False,
        critical_daily_budget_threshold=1000,
        requested_by="agent",
        sku_id="sku-9",
    )

    decision = engine.decide(context)
    writer = AuditLineageWriter()
    audit_record = writer.write(
        task=decision.task,
        decision_trace={"rule": decision.rule_name, "reason": decision.reason},
        event_ids=["evt-1", "evt-2"],
    )

    assert decision.rule_name == "refund_pause"
    assert decision.task["task_type"] == "pause_campaign"
    assert decision.task["payload"]["pause_scope"] == {"campaign_id": "cmp-4", "sku_id": "sku-9"}
    assert decision.task["outcome"]["kpi_window"] == "2h"
    assert audit_record["lineage"]["source_event_ids"] == ["evt-1", "evt-2"]
    assert audit_record["lineage"]["decision_trace"]["rule"] == "refund_pause"


def test_segment_reallocation_shifts_budget_to_top_segment_without_exceeding_step_limit():
    generator = TaskGenerator()
    gate = PolicyGate()
    router = ApprovalRouter()
    engine = DecisionEngine(generator=generator, gate=gate, router=router)

    context = DecisionContext(
        account_id="acct-5",
        platform="facebook",
        campaign_id="cmp-5",
        daily_spend_cap=900,
        current_budget=300,
        baseline_cvr=0.04,
        current_cvr=0.04,
        clicks=500,
        cooldown_active=False,
        current_epc=1.4,
        epc_p75=2.0,
        stable_windows=0,
        fatigue_baseline_ctr=0.03,
        current_ctr=0.03,
        refunds_baseline_rate=0.02,
        current_refund_rate=0.02,
        complaints_anomaly=False,
        segments={
            "seg-a": {"cvr": 0.01, "clicks": 300, "budget_share": 0.5},
            "seg-b": {"cvr": 0.05, "clicks": 320, "budget_share": 0.3},
            "seg-c": {"cvr": 0.04, "clicks": 280, "budget_share": 0.2},
        },
        daily_spend=260,
        per_campaign_cap=400,
        spend_change_today_pct=0,
        max_step_change_pct=20,
        validated_strategies={"segment_reallocation"},
        risk_category="low",
        sensitive_vertical=False,
        critical_daily_budget_threshold=1000,
        requested_by="agent",
    )

    decision = engine.decide(context)

    assert decision.rule_name == "segment_reallocation"
    assert decision.task["task_type"] == "update_budget"
    assert decision.task["payload"]["allocation"] == {
        "from_segment": "seg-a",
        "to_segment": "seg-b",
        "shift_pct": 15,
    }
    assert decision.task["approval_status"] == "pending"
    assert decision.approval_route == "manual"
