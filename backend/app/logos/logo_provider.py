"""LogoProvider: the interface every logo lookup implementation
adheres to. TickerLogosProvider (AllInvestView) is the only V1
implementation — swappable without touching LogoService or the API.
"""

from abc import ABC, abstractmethod


class LogoProvider(ABC):
    @abstractmethod
    def get_logo(self, ticker: str) -> bytes | None:
        """Return raw image bytes for a ticker's logo, or None if no
        logo exists for this ticker. Raises on transient failures
        (network errors, rate limits) — callers distinguish "no logo"
        (None) from "couldn't check right now" (exception)."""
        raise NotImplementedError