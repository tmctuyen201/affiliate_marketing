from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affiliate_agent.contracts import PlatformAdapterResult

@dataclass(frozen=True)
class ConnectorBase:
    platform: str

    def _result(self) -> PlatformAdapterResult:
        return PlatformAdapterResult(
            success=False,
            platform_campaign_id=None,
            request_id=f"{self.platform}-stub-request",
            artifacts=[],
            error="not_implemented",
        )

    def create_campaign(self, task_payload: dict[str, Any]) -> PlatformAdapterResult:
        return self._result()

    def update_budget(self, task_payload: dict[str, Any]) -> PlatformAdapterResult:
        return self._result()

    def pause_campaign(self, task_payload: dict[str, Any]) -> PlatformAdapterResult:
        return self._result()

    def rotate_creative(self, task_payload: dict[str, Any]) -> PlatformAdapterResult:
        return self._result()

    def get_campaign_state(self, account_id: str, campaign_id: str) -> dict[str, str]:
        return {"account_id": account_id, "campaign_id": campaign_id, "status": "unknown", "source": self.platform}

    def validate_session(self, account_id: str) -> bool:
        return True

class ShopeeConnector(ConnectorBase):
    def __init__(self) -> None:
        super().__init__(platform="shopee")

class TikTokShopConnector(ConnectorBase):
    def __init__(self) -> None:
        super().__init__(platform="tiktok_shop")
