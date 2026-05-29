from fastapi.testclient import TestClient

from affiliate_agent.api import create_app


def test_kill_switch_scopes_support_per_channel_and_per_campaign_drills():
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
                },
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
    blocked_tiktok = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-1",
            }
        },
    )
    allowed_facebook = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 7, "username": "admin"},
                "text": "/approve task-2",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "reply": "Kill switch enabled for channel tiktok"}
    assert blocked_tiktok.status_code == 423
    assert blocked_tiktok.json() == {"detail": "kill_switch_enabled_for_channel:tiktok"}
    assert allowed_facebook.status_code == 200
    assert allowed_facebook.json()["reply"] == "Approved task-2. Reason logged: approved via telegram by admin"


def test_authorization_failures_are_audited_with_identity_command_and_reason():
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
    audit_response = client.get("/api/audit")

    assert response.status_code == 403
    assert response.json() == {"detail": "role_not_allowed"}
    assert audit_response.status_code == 200
    assert audit_response.json()[-1] == {
        "event": "authorization_denied",
        "actor": "operator",
        "user_id": 8,
        "role": "operator",
        "command": "/approve",
        "reason": "role_not_allowed",
    }


def test_signed_callback_validation_rejects_untrusted_telegram_updates():
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


def test_admin_only_commands_matrix_blocks_approver_from_global_kill_switch_and_rollback():
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

    kill_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 9, "username": "approver"},
                "text": "/kill-switch on",
            }
        },
    )
    rollback_response = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 101},
                "from": {"id": 9, "username": "approver"},
                "text": "/rollback task-1 drill",
            }
        },
    )
    audit_response = client.get("/api/audit")

    assert kill_response.status_code == 403
    assert kill_response.json() == {"detail": "role_not_allowed"}
    assert rollback_response.status_code == 403
    assert rollback_response.json() == {"detail": "role_not_allowed"}
    assert audit_response.json()[-2:] == [
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
