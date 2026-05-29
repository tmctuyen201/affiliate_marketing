from fastapi.testclient import TestClient

from affiliate_agent.api import create_app


def test_dashboard_renders_command_center_and_guardrail_panels():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Command Center" in body
    assert "Approval Inbox" in body
    assert "Execution Timeline" in body
    assert "Guardrail Controls" in body


def test_telegram_health_reports_ok():
    client = TestClient(create_app())

    response = client.get("/telegram/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_telegram_webhook_rejects_unauthorized_chat():
    client = TestClient(create_app())

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 999},
                "from": {"id": 999, "username": "outsider"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "chat_not_allowed"}


def test_telegram_status_returns_health_and_kpis_for_operator():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            health_snapshot={
                "net_profit": 1240.5,
                "ad_spend": 3300.0,
                "roas": 1.8,
                "queue_lag": "2s",
                "api_health": "ok",
            },
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "reply": "Health ok | Net profit 1240.5 | Ad spend 3300.0 | ROAS 1.8 | Queue lag 2s"
    }


def test_telegram_approvals_lists_pending_tasks():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                },
                {
                    "task_id": "task-2",
                    "summary": "Pause cmp-3 for refund spike",
                    "approval_status": "approved",
                    "risk_impact": "high",
                },
            ],
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/approvals",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "reply": "Pending approvals:\n- task-1 | Raise budget 15% for cmp-9 | risk medium"
    }


def test_telegram_approve_requires_privileged_role_and_updates_task():
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
            user_roles={7: "approver"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/approve task-1",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "reply": "Approved task-1. Reason logged: approved via telegram by approver"
    }

    dashboard = client.get("/api/approvals").json()
    assert dashboard[0]["approval_status"] == "approved"
    assert dashboard[0]["decision_reason"] == "approved via telegram by approver"


def test_telegram_reject_requires_reason_and_logs_decision():
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
            user_roles={7: "approver"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/reject task-1 too risky for current volatility",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "reply": "Rejected task-1. Reason logged: too risky for current volatility"
    }

    dashboard = client.get("/api/approvals").json()
    assert dashboard[0]["approval_status"] == "rejected"
    assert dashboard[0]["decision_reason"] == "too risky for current volatility"


def test_telegram_approve_denies_operator_role():
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
            user_roles={7: "operator"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/approve task-1",
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "role_not_allowed"}


def test_telegram_webhook_exposes_approval_state_inputs():
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
            user_roles={7: "approver"},
        )
    )

    approvals = client.get("/api/approvals")

    assert approvals.status_code == 200
    assert approvals.json() == [
        {
            "task_id": "task-1",
            "summary": "Raise budget 15% for cmp-9",
            "approval_status": "pending",
            "risk_impact": "medium",
        }
    ]


def test_telegram_approve_denial_is_logged_to_audit_feed():
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
            user_roles={8: "operator"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 8, "username": "operator"},
                "text": "/approve task-1",
            }
        },
    )
    audit = client.get("/api/audit")

    assert response.status_code == 403
    assert audit.status_code == 200
    assert audit.json()[-1] == {
        "event": "authorization_denied",
        "actor": "operator",
        "user_id": 8,
        "role": "operator",
        "command": "/approve",
        "reason": "role_not_allowed",
    }


def test_telegram_webhook_rejects_invalid_signature():
    client = TestClient(create_app(allowed_chat_ids={101}))

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_telegram_signature"}


def test_telegram_admin_can_enable_channel_kill_switch():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                    "campaign_id": "cmp-9",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch channel tiktok on",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "reply": "Kill switch enabled for channel tiktok"}


def test_telegram_channel_kill_switch_blocks_matching_approval():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                    "campaign_id": "cmp-9",
                },
                {
                    "task_id": "task-2",
                    "summary": "Raise budget 10% for cmp-77",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "facebook",
                    "campaign_id": "cmp-77",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch channel tiktok on",
            }
        },
    )

    blocked = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )
    allowed = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-2",
            }
        },
    )

    assert blocked.status_code == 423
    assert blocked.json() == {"detail": "kill_switch_enabled_for_channel:tiktok"}
    assert allowed.status_code == 200
    assert allowed.json()["reply"] == "Approved task-2. Reason logged: approved via telegram by admin"


def test_telegram_admin_only_commands_deny_non_admin_and_log_audit():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "approved",
                    "risk_impact": "high",
                }
            ],
            user_roles={9: "approver"},
        )
    )

    kill = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 9, "username": "approver"},
                "text": "/kill-switch on",
            }
        },
    )
    rollback = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 9, "username": "approver"},
                "text": "/rollback task-1 drill",
            }
        },
    )
    audit = client.get("/api/audit")

    assert kill.status_code == 403
    assert rollback.status_code == 403
    assert audit.json()[-2:] == [
        {
            "event": "authorization_denied",
            "actor": "approver",
            "user_id": 9,
            "role": "approver",
            "command": "/kill-switch",
            "reason": "role_not_allowed",
        },
        {
            "event": "authorization_denied",
            "actor": "approver",
            "user_id": 9,
            "role": "approver",
            "command": "/rollback",
            "reason": "role_not_allowed",
        },
    ]


def test_telegram_health_still_available_for_operator_surface():
    client = TestClient(create_app())

    response = client.get("/telegram/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_still_renders_primary_panels():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Command Center" in body
    assert "Approval Inbox" in body
    assert "Execution Timeline" in body
    assert "Guardrail Controls" in body


def test_status_command_still_returns_health_snapshot():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            health_snapshot={
                "net_profit": 1240.5,
                "ad_spend": 3300.0,
                "roas": 1.8,
                "queue_lag": "2s",
                "api_health": "ok",
            },
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "reply": "Health ok | Net profit 1240.5 | Ad spend 3300.0 | ROAS 1.8 | Queue lag 2s"
    }


def test_approvals_command_still_lists_pending_tasks():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                },
                {
                    "task_id": "task-2",
                    "summary": "Pause cmp-3 for refund spike",
                    "approval_status": "approved",
                    "risk_impact": "high",
                },
            ],
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/approvals",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "reply": "Pending approvals:\n- task-1 | Raise budget 15% for cmp-9 | risk medium"
    }


def test_reject_command_still_logs_decision_reason():
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
            user_roles={7: "approver"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/reject task-1 too risky for current volatility",
            }
        },
    )

    approvals = client.get("/api/approvals")

    assert response.status_code == 200
    assert approvals.json()[0]["approval_status"] == "rejected"
    assert approvals.json()[0]["decision_reason"] == "too risky for current volatility"


def test_approve_command_still_logs_decision_reason():
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
            user_roles={7: "approver"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/approve task-1",
            }
        },
    )

    approvals = client.get("/api/approvals")

    assert response.status_code == 200
    assert approvals.json()[0]["approval_status"] == "approved"
    assert approvals.json()[0]["decision_reason"] == "approved via telegram by approver"


def test_webhook_rejects_unknown_chat():
    client = TestClient(create_app())

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 999},
                "from": {"id": 999, "username": "outsider"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "chat_not_allowed"}


def test_reject_requires_reason():
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
            user_roles={7: "approver"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/reject task-1",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "reject_reason_required"}


def test_unsupported_command_rejected():
    client = TestClient(create_app(allowed_chat_ids={101}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/profit",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "unsupported_command"}


def test_missing_task_returns_not_found():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "approver"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/approve task-x",
            }
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "task_not_found"}


def test_missing_task_id_returns_bad_request():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "approver"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/approve",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "task_id_required"}


def test_default_chat_allowlist_denies_unknown_request():
    client = TestClient(create_app())

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 42},
                "from": {"id": 7, "username": "operator"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "chat_not_allowed"}


def test_unknown_chat_denial_is_logged():
    client = TestClient(create_app())

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 42},
                "from": {"id": 7, "username": "outsider"},
                "text": "/status",
            }
        },
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "authorization_denied",
        "actor": "outsider",
        "user_id": 7,
        "role": "operator",
        "command": "/status",
        "reason": "chat_not_allowed",
    }


def test_admin_only_global_kill_switch_enable_message():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch on",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "reply": "Kill switch enabled globally"}


def test_admin_only_rollback_success_message():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "approved",
                    "risk_impact": "high",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/rollback task-1 drill",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "reply": "Rollback drill queued for task-1"}


def test_rollback_missing_task_returns_not_found():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/rollback task-x drill",
            }
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "task_not_found"}


def test_rollback_requires_task_id():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/rollback",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "task_id_required"}


def test_global_kill_switch_blocks_approve():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                }
            ],
            user_roles={7: "admin"},
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

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )

    assert response.status_code == 423
    assert response.json() == {"detail": "kill_switch_enabled_global"}


def test_global_kill_switch_blocks_reject():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                }
            ],
            user_roles={7: "admin"},
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

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/reject task-1 too risky",
            }
        },
    )

    assert response.status_code == 423
    assert response.json() == {"detail": "kill_switch_enabled_global"}


def test_channel_kill_switch_blocks_reject_for_matching_platform():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch channel tiktok on",
            }
        },
    )

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/reject task-1 too risky",
            }
        },
    )

    assert response.status_code == 423
    assert response.json() == {"detail": "kill_switch_enabled_for_channel:tiktok"}


def test_campaign_kill_switch_blocks_matching_campaign():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                    "campaign_id": "cmp-9",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    enable = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch campaign cmp-9 on",
            }
        },
    )
    blocked = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )

    assert enable.status_code == 200
    assert enable.json() == {"ok": True, "reply": "Kill switch enabled for campaign cmp-9"}
    assert blocked.status_code == 423
    assert blocked.json() == {"detail": "kill_switch_enabled_for_campaign:cmp-9"}


def test_channel_kill_switch_off_reopens_approvals():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                    "campaign_id": "cmp-9",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch channel tiktok on",
            }
        },
    )
    disable = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch channel tiktok off",
            }
        },
    )
    approve = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )

    assert disable.status_code == 200
    assert disable.json() == {"ok": True, "reply": "Kill switch disabled for channel tiktok"}
    assert approve.status_code == 200


def test_campaign_kill_switch_off_reopens_approvals():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "pending",
                    "risk_impact": "medium",
                    "platform": "tiktok",
                    "campaign_id": "cmp-9",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch campaign cmp-9 on",
            }
        },
    )
    disable = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch campaign cmp-9 off",
            }
        },
    )
    approve = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )

    assert disable.status_code == 200
    assert disable.json() == {"ok": True, "reply": "Kill switch disabled for campaign cmp-9"}
    assert approve.status_code == 200


def test_invalid_kill_switch_scope_rejected():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch region us on",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_kill_switch_scope"}


def test_invalid_kill_switch_state_rejected():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch on maybe",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_kill_switch_state"}


def test_kill_switch_changes_logged_to_audit_feed():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

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

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "kill_switch_changed",
        "actor": "admin",
        "user_id": 7,
        "role": "admin",
        "command": "/kill-switch",
        "reason": "enabled_global",
    }


def test_successful_rollback_logged_to_audit_feed():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {
                    "task_id": "task-1",
                    "summary": "Raise budget 15% for cmp-9",
                    "approval_status": "approved",
                    "risk_impact": "high",
                }
            ],
            user_roles={7: "admin"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/rollback task-1 drill",
            }
        },
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "rollback_requested",
        "actor": "admin",
        "user_id": 7,
        "role": "admin",
        "command": "/rollback",
        "reason": "rollback_drill_for:task-1",
    }


def test_approved_actions_logged_to_audit_feed():
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
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/approve task-1",
            }
        },
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "approval_recorded",
        "actor": "approver",
        "user_id": 7,
        "role": "approver",
        "command": "/approve",
        "reason": "approved:task-1",
    }


def test_rejected_actions_logged_to_audit_feed():
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
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/reject task-1 too risky",
            }
        },
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "approval_recorded",
        "actor": "approver",
        "user_id": 7,
        "role": "approver",
        "command": "/reject",
        "reason": "rejected:task-1",
    }


def test_invalid_signature_denial_logged_to_audit_feed():
    client = TestClient(create_app(allowed_chat_ids={101}))

    client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/status",
            }
        },
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "authorization_denied",
        "actor": "admin",
        "user_id": 7,
        "role": "operator",
        "command": "/status",
        "reason": "invalid_telegram_signature",
    }


def test_api_audit_starts_empty():
    client = TestClient(create_app())

    response = client.get("/api/audit")

    assert response.status_code == 200
    assert response.json() == []


def test_dashboard_renders_audit_panel_link_text():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Audit trail" in response.text


def test_dashboard_renders_command_center_summary_metrics():
    client = TestClient(
        create_app(
            health_snapshot={
                "net_profit": 100.0,
                "ad_spend": 200.0,
                "roas": 1.5,
                "queue_lag": "1s",
                "api_health": "ok",
            }
        )
    )

    response = client.get("/")

    body = response.text
    assert "Net revenue / profit snapshot" in body
    assert "API health" in body


def test_dashboard_renders_guardrail_summary_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Daily spend cap" in response.text


def test_dashboard_renders_timeline_linkback_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Telegram actions link back to dashboard detail" in response.text


def test_dashboard_approvals_panel_shows_pending_count():
    client = TestClient(
        create_app(
            approvals=[
                {"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"},
                {"task_id": "task-2", "summary": "Pause campaign", "approval_status": "approved", "risk_impact": "high"},
            ]
        )
    )

    response = client.get("/")

    assert "Pending approvals: 1" in response.text


def test_admin_only_campaign_kill_switch_requires_target_and_state():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch campaign",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_kill_switch_scope"}


def test_admin_only_channel_kill_switch_requires_target_and_state():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/kill-switch channel",
            }
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_kill_switch_scope"}


def test_rollbacks_require_admin_even_with_allowed_chat():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "operator"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/rollback task-1 drill",
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "role_not_allowed"}


def test_kill_switch_requires_admin_even_with_allowed_chat():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "operator"}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "operator"},
                "text": "/kill-switch on",
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "role_not_allowed"}


def test_signature_accepts_expected_secret_token():
    client = TestClient(create_app(allowed_chat_ids={101}))

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "dev-telegram-secret"},
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 200


def test_default_signature_header_optional_when_not_sent():
    client = TestClient(create_app(allowed_chat_ids={101}))

    response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/status",
            }
        },
    )

    assert response.status_code == 200


def test_dashboard_renders_guardrail_panel_title_exact_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Guardrail Controls" in response.text


def test_dashboard_renders_timeline_panel_title_exact_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Execution Timeline" in response.text


def test_dashboard_renders_command_center_panel_title_exact_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Command Center" in response.text


def test_dashboard_renders_approval_inbox_panel_title_exact_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Approval Inbox" in response.text


def test_dashboard_lists_pending_approval_summary_lines():
    client = TestClient(
        create_app(
            approvals=[
                {"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}
            ]
        )
    )

    response = client.get("/")

    assert "task-1: Raise budget" in response.text


def test_dashboard_timeline_defaults_to_waiting_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Awaiting operator actions" in response.text


def test_approval_write_updates_timeline_feed():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}
            ],
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/approve task-1",
            }
        },
    )

    response = client.get("/")

    assert "Approved task-1" in response.text


def test_reject_write_updates_timeline_feed():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[
                {"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}
            ],
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "approver"},
                "text": "/reject task-1 too risky",
            }
        },
    )

    response = client.get("/")

    assert "Rejected task-1" in response.text


def test_dashboard_api_health_defaults_unknown():
    client = TestClient(create_app())

    response = client.get("/")

    assert "unknown" in response.text


def test_dashboard_api_health_uses_snapshot_value():
    client = TestClient(create_app(health_snapshot={"api_health": "ok", "net_profit": 0, "ad_spend": 0, "roas": 0, "queue_lag": "0s"}))

    response = client.get("/")

    assert "API health: ok" in response.text


def test_dashboard_pending_zero_copy_when_empty():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Pending approvals: 0" in response.text


def test_dashboard_audit_api_returns_mutation_events_ordered():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}],
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "approver"}, "text": "/approve task-1"}},
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1]["event"] == "approval_recorded"


def test_reject_command_preserves_original_summary_in_api():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}],
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "approver"}, "text": "/reject task-1 too risky"}},
    )

    approvals = client.get("/api/approvals")

    assert approvals.json()[0]["summary"] == "Raise budget"


def test_approve_command_preserves_original_summary_in_api():
    client = TestClient(
        create_app(
            allowed_chat_ids={101},
            approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}],
            user_roles={7: "approver"},
        )
    )

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "approver"}, "text": "/approve task-1"}},
    )

    approvals = client.get("/api/approvals")

    assert approvals.json()[0]["summary"] == "Raise budget"


def test_status_command_works_for_admin_role_too():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}, health_snapshot={"net_profit": 1, "ad_spend": 2, "roas": 3, "queue_lag": "4s", "api_health": "ok"}))

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/status"}},
    )

    assert response.status_code == 200


def test_approvals_command_works_for_admin_role_too():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}]))

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/approvals"}},
    )

    assert response.status_code == 200


def test_approve_command_works_for_admin_role_too():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}]))

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/approve task-1"}},
    )

    assert response.status_code == 200


def test_reject_command_works_for_admin_role_too():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}]))

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/reject task-1 too risky"}},
    )

    assert response.status_code == 200


def test_dashboard_shows_audit_heading():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Audit trail" in response.text


def test_dashboard_shows_linkback_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "dashboard detail" in response.text


def test_webhook_signature_denial_does_not_mutate_approvals():
    client = TestClient(create_app(allowed_chat_ids={101}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}], user_roles={7: "approver"}))

    client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "approver"}, "text": "/approve task-1"}},
    )

    approvals = client.get("/api/approvals")

    assert approvals.json()[0]["approval_status"] == "pending"


def test_chat_denial_does_not_mutate_approvals():
    client = TestClient(create_app(allowed_chat_ids={101}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}], user_roles={7: "approver"}))

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 999}, "from": {"id": 7, "username": "approver"}, "text": "/approve task-1"}},
    )

    approvals = client.get("/api/approvals")

    assert approvals.json()[0]["approval_status"] == "pending"


def test_role_denial_does_not_mutate_approvals():
    client = TestClient(create_app(allowed_chat_ids={101}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}], user_roles={7: "operator"}))

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "operator"}, "text": "/approve task-1"}},
    )

    approvals = client.get("/api/approvals")

    assert approvals.json()[0]["approval_status"] == "pending"


def test_kill_switch_channel_denial_logged_before_block():
    client = TestClient(create_app(allowed_chat_ids={101}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium", "platform": "tiktok"}], user_roles={7: "admin"}))

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/kill-switch channel tiktok on"}},
    )
    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/approve task-1"}},
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "authorization_denied",
        "actor": "admin",
        "user_id": 7,
        "role": "admin",
        "command": "/approve",
        "reason": "kill_switch_enabled_for_channel:tiktok",
    }


def test_kill_switch_campaign_denial_logged_before_block():
    client = TestClient(create_app(allowed_chat_ids={101}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium", "campaign_id": "cmp-9"}], user_roles={7: "admin"}))

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/kill-switch campaign cmp-9 on"}},
    )
    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/approve task-1"}},
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "authorization_denied",
        "actor": "admin",
        "user_id": 7,
        "role": "admin",
        "command": "/approve",
        "reason": "kill_switch_enabled_for_campaign:cmp-9",
    }


def test_kill_switch_global_denial_logged_before_block():
    client = TestClient(create_app(allowed_chat_ids={101}, approvals=[{"task_id": "task-1", "summary": "Raise budget", "approval_status": "pending", "risk_impact": "medium"}], user_roles={7: "admin"}))

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/kill-switch on"}},
    )
    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/approve task-1"}},
    )

    audit = client.get("/api/audit")

    assert audit.json()[-1] == {
        "event": "authorization_denied",
        "actor": "admin",
        "user_id": 7,
        "role": "admin",
        "command": "/approve",
        "reason": "kill_switch_enabled_global",
    }


def test_audit_feed_preserves_order_of_events():
    client = TestClient(create_app(allowed_chat_ids={101}, user_roles={7: "admin"}))

    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/kill-switch on"}},
    )
    client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 101}, "from": {"id": 7, "username": "admin"}, "text": "/kill-switch off"}},
    )

    audit = client.get("/api/audit")

    assert [entry["reason"] for entry in audit.json()[-2:]] == ["enabled_global", "disabled_global"]


def test_dashboard_mentions_mobile_speed_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Telegram optimized for speed" in response.text


def test_dashboard_mentions_forensic_analysis_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "forensic analysis" in response.text


def test_dashboard_mentions_traceability_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "full traceability" in response.text


def test_dashboard_mentions_low_latency_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "low-latency decisioning" in response.text


def test_dashboard_mentions_incident_annotations_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "incident annotations" in response.text


def test_dashboard_mentions_global_emergency_stop_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "global kill switch" in response.text


def test_dashboard_mentions_periodic_kpi_summaries_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "KPI summaries" in response.text


def test_dashboard_mentions_side_by_side_context_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Side-by-side context" in response.text


def test_dashboard_mentions_expected_uplift_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "expected uplift" in response.text


def test_dashboard_mentions_risk_impact_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "risk impact" in response.text


def test_dashboard_mentions_drill_down_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Drill-down to artifacts" in response.text


def test_dashboard_mentions_badges_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "health badges" in response.text


def test_dashboard_mentions_profit_trend_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Profit trend" in response.text


def test_dashboard_mentions_volatility_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "volatility" in response.text


def test_dashboard_mentions_winners_losers_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "winners" in response.text
    assert "losers" in response.text


def test_dashboard_mentions_constrained_campaigns_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "constrained campaigns" in response.text


def test_dashboard_mentions_cooldown_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Cooldown intervals" in response.text


def test_dashboard_mentions_stop_loss_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "stop-loss thresholds" in response.text


def test_dashboard_mentions_automation_level_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "automation level" in response.text


def test_dashboard_mentions_operator_interfaces_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Telegram actions link back" in response.text


def test_dashboard_mentions_approval_completion_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Every dashboard approval can be completed from Telegram" in response.text


def test_dashboard_mentions_mobile_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "mobility" in response.text


def test_dashboard_mentions_situational_awareness_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "situational awareness" in response.text


def test_dashboard_mentions_depth_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "deep monitoring" in response.text


def test_dashboard_mentions_control_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "control" in response.text


def test_dashboard_mentions_alerts_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "alerts" in response.text


def test_dashboard_mentions_incidents_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "incidents" in response.text


def test_dashboard_mentions_action_requests_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "action requests" in response.text


def test_dashboard_mentions_on_demand_qa_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "On-demand Q&A" in response.text


def test_dashboard_mentions_incident_notifications_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Incident notifications" in response.text


def test_dashboard_mentions_fast_communication_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "fast communication" in response.text


def test_dashboard_mentions_approvals_and_alerts_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "approvals" in response.text
    assert "alerts" in response.text


def test_dashboard_mentions_operator_surfaces_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "operator surfaces" in response.text


def test_dashboard_mentions_execution_outcome_chain_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "decision -> action -> platform result -> outcome" in response.text


def test_dashboard_mentions_rollback_markers_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Rollback markers" in response.text


def test_dashboard_mentions_data_freshness_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "data freshness" in response.text


def test_dashboard_mentions_queue_lag_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "queue lag" in response.text


def test_dashboard_mentions_api_health_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "API health" in response.text


def test_dashboard_mentions_roi_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "ROAS" in response.text


def test_dashboard_mentions_refund_rate_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "refund rate" in response.text


def test_dashboard_mentions_campaign_intelligence_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Campaign Intelligence" in response.text


def test_dashboard_mentions_risk_score_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "risk score" in response.text


def test_dashboard_mentions_sort_filter_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Sort/filter" in response.text


def test_dashboard_mentions_budget_epc_ctr_cvr_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "budget" in response.text
    assert "EPC" in response.text
    assert "CTR" in response.text
    assert "CVR" in response.text


def test_dashboard_mentions_chronological_stream_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Chronological stream" in response.text


def test_dashboard_mentions_artifacts_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "screenshots" in response.text
    assert "DOM snapshots" in response.text
    assert "API logs" in response.text


def test_dashboard_mentions_emergency_stop_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "emergency stop" in response.text


def test_dashboard_mentions_daily_briefing_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Daily briefing" in response.text


def test_dashboard_mentions_primary_near_realtime_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Primary near-realtime communication channel" in response.text


def test_dashboard_mentions_dual_operator_interfaces_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "dual operator surfaces" in response.text


def test_dashboard_mentions_speed_and_depth_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "speed" in response.text
    assert "depth" in response.text


def test_dashboard_mentions_traceability_and_control_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "traceability" in response.text
    assert "control" in response.text


def test_dashboard_mentions_human_decision_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "human decision" in response.text


def test_dashboard_mentions_high_impact_actions_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "high-impact actions" in response.text


def test_dashboard_mentions_expected_uplift_and_risk_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "expected uplift" in response.text
    assert "risk impact" in response.text


def test_dashboard_mentions_fast_mobility_low_latency_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "speed, mobility, and low-latency decisioning" in response.text


def test_dashboard_mentions_dashboard_approval_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Every dashboard approval can be completed from Telegram" in response.text


def test_dashboard_mentions_timeline_and_artifacts_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Drill-down to artifacts" in response.text
    assert "Rollback markers" in response.text


def test_dashboard_mentions_guardrail_controls_copy():
    client = TestClient(create_app())

    response = client.get("/")

    assert "Guardrail Controls" in response.text
    assert "Daily spend cap" in response.text
