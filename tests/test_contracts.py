from affiliate_agent.contracts import (
    ArtifactRecord,
    PlatformAdapterResult,
    TaskContract,
)


def test_task_contract_serializes_required_safety_and_execution_fields():
    contract = TaskContract(
        task_type="update_budget",
        platform="tiktok",
        account_id="acct-1",
        idempotency_key="idem-123",
        payload={"budget": {"amount": 100}},
    )

    data = contract.to_dict()

    assert data["task_type"] == "update_budget"
    assert data["idempotency_key"] == "idem-123"
    assert data["approval_required"] is True
    assert data["safety_profile"]["max_spend_change_pct"] == 20
    assert data["execution"]["status"] == "queued"
    assert data["execution"]["artifacts"] == {
        "screenshots": [],
        "dom_snapshots": [],
        "api_logs": [],
        "traces": [],
    }


def test_adapter_result_preserves_artifact_uris():
    result = PlatformAdapterResult(
        success=True,
        platform_campaign_id="cmp-1",
        request_id="req-1",
        artifacts=[ArtifactRecord("trace", "s3://bucket/trace.json")],
    )

    assert result.to_dict()["artifacts"] == [
        {"artifact_type": "trace", "uri": "s3://bucket/trace.json"}
    ]
