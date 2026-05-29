from collections.abc import Mapping


class SecretStore:
    def __init__(self, provider: str, values: Mapping[str, str] | None = None):
        self.provider = provider
        self._values = dict(values or {})

    def read(self, reference: str) -> str:
        if self.provider == "env":
            return self._values.get(reference, "")
        return f"{self.provider}://{reference}"
