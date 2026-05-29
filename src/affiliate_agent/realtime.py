from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

EVENT_BUS_TOPIC = "events.normalized"
DEFAULT_DLQ_TOPIC = "events.normalized.dlq"


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    source: str
    account_id: str
    campaign_id: str
    event_type: str
    occurred_at: datetime
    lineage: dict[str, str]
    metrics: dict[str, float | int]


@dataclass(frozen=True)
class PublishEvent:
    topic: str
    payload: dict[str, Any]

    @classmethod
    def from_normalized(cls, event: NormalizedEvent) -> "PublishEvent":
        payload = asdict(event)
        payload["occurred_at"] = event.occurred_at.isoformat()
        payload["metrics_window_tables"] = [
            "metrics_window_1m",
            "metrics_window_1h",
            "metrics_window_1d",
        ]
        return cls(topic=EVENT_BUS_TOPIC, payload=payload)


@dataclass(frozen=True)
class EventPublishReceipt:
    status: str
    attempts: int
    dlq_topic: str | None


@dataclass(frozen=True)
class FreshnessBudget:
    max_age: timedelta
    degraded_after: timedelta


@dataclass(frozen=True)
class FreshnessState:
    source: str
    lag_seconds: int | None
    stale: bool
    degraded: bool
    mode: str


class FreshnessMonitor:
    def __init__(self, budgets: dict[str, FreshnessBudget]) -> None:
        self._budgets = budgets
        self._last_seen: dict[str, datetime] = {}

    def record(self, source: str, seen_at: datetime) -> None:
        self._last_seen[source] = seen_at

    def status_at(self, now: datetime) -> FreshnessState:
        source = next(iter(self._budgets))
        return self._state_for(source, now)

    def snapshot_at(self, now: datetime) -> dict[str, Any]:
        sources = {source: self._state_for(source, now) for source in self._budgets}
        stale_sources = [source for source, state in sources.items() if state.stale]
        overall_mode = "degraded" if any(state.degraded for state in sources.values()) else "live"
        return {
            "sources": sources,
            "stale_sources": stale_sources,
            "overall_mode": overall_mode,
        }

    def _state_for(self, source: str, now: datetime) -> FreshnessState:
        budget = self._budgets[source]
        if source not in self._last_seen:
            return FreshnessState(source=source, lag_seconds=None, stale=True, degraded=True, mode="awaiting_first_event")
        lag_seconds = int((now - self._last_seen[source]).total_seconds())
        stale = lag_seconds > int(budget.max_age.total_seconds())
        degraded = lag_seconds > int(budget.degraded_after.total_seconds())
        return FreshnessState(
            source=source,
            lag_seconds=lag_seconds,
            stale=stale,
            degraded=degraded,
            mode="degraded" if degraded else "live",
        )


class EventBusPublisher:
    def __init__(
        self,
        *,
        sender: Callable[[str, dict[str, Any]], None],
        max_attempts: int = 3,
        dlq_topic: str = DEFAULT_DLQ_TOPIC,
    ) -> None:
        self._sender = sender
        self._max_attempts = max_attempts
        self._dlq_topic = dlq_topic

    def publish(self, event: PublishEvent) -> EventPublishReceipt:
        attempts = 0
        while attempts < self._max_attempts:
            attempts += 1
            try:
                self._sender(event.topic, event.payload)
                return EventPublishReceipt(status="published", attempts=attempts, dlq_topic=None)
            except RuntimeError:
                if attempts == self._max_attempts:
                    try:
                        self._sender(self._dlq_topic, event.payload)
                    except RuntimeError:
                        pass
                    return EventPublishReceipt(
                        status="dead_lettered",
                        attempts=attempts,
                        dlq_topic=self._dlq_topic,
                    )
        raise RuntimeError("unreachable")


def build_source_plan(platform: str) -> dict[str, Any]:
    return {
        "platform": platform,
        "push_first": True,
        "streaming": True,
        "poll_fallback": True,
    }


def normalize_event(source: str, raw_event: dict[str, Any]) -> NormalizedEvent:
    occurred_at = datetime.fromisoformat(raw_event["occurred_at"])
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return NormalizedEvent(
        event_id=raw_event["event_id"],
        source=source,
        account_id=raw_event["account_id"],
        campaign_id=raw_event["campaign_id"],
        event_type=raw_event["event_type"],
        occurred_at=occurred_at,
        lineage={"raw_table": raw_event.get("raw_table", "events_raw"), "normalized_table": "events_normalized"},
        metrics=raw_event.get("metrics", {}),
    )
