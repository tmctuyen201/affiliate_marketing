from copy import deepcopy
from typing import Any


class AuditLineageWriter:
    def write(
        self,
        task: dict[str, Any] | None,
        decision_trace: dict[str, Any],
        event_ids: list[str],
    ) -> dict[str, Any]:
        record = deepcopy(task) if task is not None else {}
        record["lineage"] = {
            "source_event_ids": list(event_ids),
            "decision_trace": deepcopy(decision_trace),
        }
        return record
