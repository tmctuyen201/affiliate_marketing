from affiliate_agent.observability import (
    HealthStatus,
    ServiceHealth,
    build_logger,
    build_trace_context,
    readiness_report,
)


def test_readiness_report_tracks_degraded_dependencies():
    report = readiness_report(
        "strategy",
        [
            ServiceHealth("event_bus", HealthStatus.OK),
            ServiceHealth("postgres", HealthStatus.DEGRADED, "lag high"),
        ],
    )

    assert report["service"] == "strategy"
    assert report["status"] == "degraded"
    assert report["checks"][1]["reason"] == "lag high"


def test_logger_and_trace_context_share_service_identity():
    logger = build_logger("executor")
    trace = build_trace_context("executor", "task-123")

    assert logger.extra["service"] == "executor"
    assert trace["service.name"] == "executor"
    assert trace["task.id"] == "task-123"
