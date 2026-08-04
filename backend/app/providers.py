from __future__ import annotations


class ProviderUnavailableError(RuntimeError):
    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} is unavailable: {reason}")
        self.provider = provider
        self.reason = reason


class ProviderResponseError(RuntimeError):
    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} returned an invalid response: {reason}")
        self.provider = provider
        self.reason = reason
