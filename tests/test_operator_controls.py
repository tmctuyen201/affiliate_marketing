from fastapi.testclient import TestClient

from affiliate_agent.api import create_app


def test_kill_switch_blocks_mutating_operator_commands_until_disabled():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    enable_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch on",
            }
        },
    )
    blocked_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )
    disable_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch off",
            }
        },
    )
    approval_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )

    assert enable_response.status_code == 200
    assert enable_response.json() == {"ok": True, "reply": "Kill switch enabled globally"}
    assert blocked_response.status_code == 423
    assert blocked_response.json() == {"detail": "kill_switch_enabled_global"}
    assert disable_response.status_code == 200
    assert disable_response.json() == {"ok": True, "reply": "Kill switch disabled globally"}
    assert approval_response.status_code == 200
    assert approval_response.json()["reply"] == "Approved task-1. Reason logged: approved via telegram by admin"


def test_rollback_drill_restores_last_approval_decision_and_records_audit_entry():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    approve_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )
    rollback_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/rollback task-1 operator drill",
            }
        },
    )
    approvals_response = client.get("/api/approvals")
    audit_response = client.get("/api/audit")

    assert approve_response.status_code == 200
    assert rollback_response.status_code == 200
    assert rollback_response.json() == {
        "ok": True,
        "reply": "Rollback drill queued for task-1",
    }
    approvals = approvals_response.json()
    assert approvals[0]["approval_status"] == "approved"
    audit_entries = audit_response.json()
    assert audit_entries[-1] == {
        "event": "rollback_requested",
        "actor": "admin",
        "user_id": 7,
        "role": "admin",
        "command": "/rollback",
        "reason": "rollback_drill_for:task-1",
    }


def test_regression_harness_snapshot_exposes_guardrail_state_for_drills():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                }
            ],
            user_roles={7: "admin"},
            health_snapshot={
                "net_profit": 1240.5,
                "ad_spend": 3300.0,
                "roas": 1.8,
                "queue_lag": "2s",
                "api_health": "ok",
            },
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch on",
            }
        },
    )

    response = client.get("/api/regression-harness")

    assert response.status_code == 200
    assert response.json() == {
        "kill_switch_enabled": True,
        "pending_approvals": 1,
        "approved_approvals": 0,
        "last_audit_event": "kill_switch_enabled",
        "health_snapshot": {
            "net_profit": 1240.5,
            "ad_spend": 3300.0,
            "roas": 1.8,
            "queue_lag": "2s",
            "api_health": "ok",
        },
    }
