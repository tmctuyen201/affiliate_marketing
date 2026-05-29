from datetime import datetime, timedelta, timezone

import pytest

from affiliate_agent.realtime import (
    EventBusPublisher,
    EVENT_BUS_TOPIC,
    FreshnessBudget,
    FreshnessMonitor,
    FreshnessState,
    NormalizedEvent,
    PublishEvent,
    build_source_plan,
    normalize_event,
)
from affiliate_agent.connectors import ShopeeConnector, TikTokShopConnector


def test_connector_registry_exposes_required_mutation_and_observation_methods():
    shopee = ShopeeConnector()
    tiktok = TikTokShopConnector()

    for connector in (shopee, tiktok):
        assert connector.create_campaign({"name": "launch"}).success is False
        assert connector.update_budget({"budget": 100}).error == "not_implemented"
        assert connector.pause_campaign({"campaign_id": "cmp-1"}).request_id.startswith(
            connector.platform
        )
        assert connector.rotate_creative({"creative_id": "cr-1"}).platform_campaign_id is None
        state = connector.get_campaign_state("acct-1", "cmp-1")
        assert state["status"] == "unknown"
        assert state["source"] == connector.platform
        assert connector.validate_session("acct-1") is True


def test_source_plan_marks_push_stream_and_poll_requirements_per_platform():
    assert build_source_plan("shopee") == {
        "platform": "shopee",
        "push_first": True,
        "streaming": True,
        "poll_fallback": True,
    }
    assert build_source_plan("tiktok_shop") == {
        "platform": "tiktok_shop",
        "push_first": True,
        "streaming": True,
        "poll_fallback": True,
    }


def test_normalize_event_preserves_immutable_lineage_and_metrics_dimensions():
    event = normalize_event(
        source="shopee",
        raw_event={
            "event_id": "evt-1",
            "account_id": "acct-1",
            "campaign_id": "cmp-1",
            "event_type": "order_paid",
            "occurred_at": "2026-05-25T08:00:00+00:00",
            "metrics": {"commission": 12.5, "net_profit": 5.2},
            "raw_table": "events_raw",
        },
    )

    assert event == NormalizedEvent(
        event_id="evt-1",
        source="shopee",
        account_id="acct-1",
        campaign_id="cmp-1",
        event_type="order_paid",
        occurred_at=datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc),
        lineage={"raw_table": "events_raw", "normalized_table": "events_normalized"},
        metrics={"commission": 12.5, "net_profit": 5.2},
    )


def test_publish_event_builds_topic_and_payload_for_normalized_stream():
    event = NormalizedEvent(
        event_id="evt-1",
        source="tiktok_shop",
        account_id="acct-9",
        campaign_id="cmp-9",
        event_type="click",
        occurred_at=datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc),
        lineage={"raw_table": "events_raw", "normalized_table": "events_normalized"},
        metrics={"clicks": 1},
    )

    published = PublishEvent.from_normalized(event)

    assert published.topic == EVENT_BUS_TOPIC
    assert published.payload["event_id"] == "evt-1"
    assert published.payload["source"] == "tiktok_shop"
    assert published.payload["metrics_window_tables"] == [
        "metrics_window_1m",
        "metrics_window_1h",
        "metrics_window_1d",
    ]


def test_freshness_monitor_flags_stale_sources_and_degraded_mode():
    budget = FreshnessBudget(max_age=timedelta(seconds=60), degraded_after=timedelta(seconds=120))
    monitor = FreshnessMonitor({"shopee": budget})
    seen_at = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    monitor.record("shopee", seen_at)

    assert monitor.status_at(seen_at + timedelta(seconds=59)) == FreshnessState(
        source="shopee",
        lag_seconds=59,
        stale=False,
        degraded=False,
        mode="live",
    )
    assert monitor.status_at(seen_at + timedelta(seconds=61)).stale is True
    assert monitor.status_at(seen_at + timedelta(seconds=121)).mode == "degraded"


def test_freshness_monitor_requires_first_event_before_source_is_healthy():
    budget = FreshnessBudget(max_age=timedelta(seconds=60), degraded_after=timedelta(seconds=120))
    monitor = FreshnessMonitor({"tiktok_shop": budget})

    state = monitor.status_at(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc))

    assert state == FreshnessState(
        source="tiktok_shop",
        lag_seconds=None,
        stale=True,
        degraded=True,
        mode="awaiting_first_event",
    )


def test_freshness_monitor_reports_all_sources_with_overall_status():
    budgets = {
        "shopee": FreshnessBudget(max_age=timedelta(seconds=60), degraded_after=timedelta(seconds=120)),
        "tiktok_shop": FreshnessBudget(max_age=timedelta(seconds=30), degraded_after=timedelta(seconds=90)),
    }
    monitor = FreshnessMonitor(budgets)
    now = datetime(2026, 5, 25, 10, 5, tzinfo=timezone.utc)
    monitor.record("shopee", now - timedelta(seconds=20))
    monitor.record("tiktok_shop", now - timedelta(seconds=95))

    snapshot = monitor.snapshot_at(now)

    assert snapshot["overall_mode"] == "degraded"
    assert snapshot["stale_sources"] == ["tiktok_shop"]
    assert snapshot["sources"]["shopee"] == FreshnessState(
        source="shopee",
        lag_seconds=20,
        stale=False,
        degraded=False,
        mode="live",
    )
    assert snapshot["sources"]["tiktok_shop"] == FreshnessState(
        source="tiktok_shop",
        lag_seconds=95,
        stale=True,
        degraded=True,
        mode="degraded",
    )


def test_event_bus_publisher_retries_transient_failures_before_success():
    attempts = []

    def flaky_send(topic, payload):
        attempts.append((topic, payload["event_id"]))
        if len(attempts) < 3:
            raise RuntimeError("temporary bus outage")

    publisher = EventBusPublisher(sender=flaky_send, max_attempts=3)
    event = PublishEvent(
        topic=EVENT_BUS_TOPIC,
        payload={"event_id": "evt-9", "source": "shopee"},
    )

    receipt = publisher.publish(event)

    assert receipt.status == "published"
    assert receipt.attempts == 3
    assert receipt.dlq_topic is None
    assert attempts == [
        (EVENT_BUS_TOPIC, "evt-9"),
        (EVENT_BUS_TOPIC, "evt-9"),
        (EVENT_BUS_TOPIC, "evt-9"),
    ]


def test_event_bus_publisher_sends_terminal_failures_to_dlq():
    sent = []

    def always_fail(topic, payload):
        sent.append((topic, payload["event_id"]))
        raise RuntimeError("permanent bus outage")

    publisher = EventBusPublisher(sender=always_fail, max_attempts=3, dlq_topic="events.normalized.dlq")
    event = PublishEvent(
        topic=EVENT_BUS_TOPIC,
        payload={"event_id": "evt-dead", "source": "tiktok_shop"},
    )

    receipt = publisher.publish(event)

    assert receipt.status == "dead_lettered"
    assert receipt.attempts == 3
    assert receipt.dlq_topic == "events.normalized.dlq"
    assert sent == [
        (EVENT_BUS_TOPIC, "evt-dead"),
        (EVENT_BUS_TOPIC, "evt-dead"),
        (EVENT_BUS_TOPIC, "evt-dead"),
        ("events.normalized.dlq", "evt-dead"),
    ]
