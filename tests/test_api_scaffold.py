from fastapi.testclient import TestClient

from affiliate_agent.api import create_app


def test_health_endpoint_reports_service_catalog_and_ready_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "affiliate-agent",
        "services": [
            "observer",
            "feature",
            "strategy",
            "policy_risk",
            "executor",
            "evaluator",
            "learner",
            "supervisor",
        ],
    }


def test_decision_preview_endpoint_returns_policy_decision_payload():
    client = TestClient(create_app())

    response = client.post(
        "/decision/preview",
        json={
            "account_id": "acct-10",
            "platform": "tiktok",
            "campaign_id": "cmp-10",
            "daily_spend_cap": 500,
            "current_budget": 100,
            "baseline_cvr": 0.04,
            "current_cvr": 0.028,
            "clicks": 250,
            "cooldown_active": False,
            "current_epc": 1.0,
            "epc_p75": 1.5,
            "stable_windows": 1,
            "fatigue_baseline_ctr": 0.02,
            "current_ctr": 0.018,
            "refunds_baseline_rate": 0.03,
            "current_refund_rate": 0.03,
            "complaints_anomaly": False,
            "segments": {},
            "daily_spend": 120,
            "per_campaign_cap": 150,
            "spend_change_today_pct": 0,
            "max_step_change_pct": 20,
            "validated_strategies": ["underperformance_cut"],
            "risk_category": "low",
            "sensitive_vertical": False,
            "critical_daily_budget_threshold": 1000,
            "requested_by": "agent"
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rule_name"] == "underperformance_cut"
    assert body["approval_route"] is None
    assert body["task"]["task_type"] == "update_budget"
    assert body["task"]["payload"]["budget"]["amount"] == 80.0
