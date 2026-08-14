"""FundamentalContext: wraps Finnhub's /stock/profile2 and
/stock/metric endpoints. Same "conversational context, not a tradable
rule primitive" framing as MarketContext/IndicatorContext.

Real field names confirmed against Finnhub's actual response shape,
not guessed: profile2 returns name/finnhubIndustry/marketCapitalization
directly; metric wraps everything else under a "metric" key, with
peBasicExclExtraTTM and dividendYieldIndicatedAnnual as the confirmed
names for P/E and dividend yield. Deliberately limited to fields with
confirmed real names -- no EPS field, since no source confirmed its
exact key; better to under-report than guess a field name that would
silently return None forever.

FinnhubClient is a Protocol, not a concrete class, so
get_fundamental_context is testable without any real network call --
same dependency-injection pattern as MarketDataProvider/LLMService.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubClient(Protocol):
    def get_profile(self, symbol: str) -> dict: ...
    def get_metrics(self, symbol: str) -> dict: ...


class HttpxFinnhubClient:
    """The one real implementation. No Finnhub-specific detail (URLs,
    the token query param) is visible past this class -- everything
    else only ever sees the Protocol and FundamentalContext."""

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def get_profile(self, symbol: str) -> dict:
        response = httpx.get(
            f"{_BASE_URL}/stock/profile2",
            params={"symbol": symbol, "token": self._api_key}, timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_metrics(self, symbol: str) -> dict:
        response = httpx.get(
            f"{_BASE_URL}/stock/metric",
            params={"symbol": symbol, "metric": "all", "token": self._api_key}, timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()


@dataclass(frozen=True)
class FundamentalContext:
    symbol: str
    company_name: str | None
    sector: str | None
    market_cap: float | None  # millions USD -- Finnhub's own unit, not converted
    pe_ratio: float | None
    dividend_yield_pct: float | None


def get_fundamental_context(symbol: str, client: FinnhubClient) -> FundamentalContext | None:
    """Finnhub returns an empty {} for profile2 on an unknown symbol --
    treated as "no data," never an error."""
    profile = client.get_profile(symbol)
    if not profile:
        return None

    metrics_response = client.get_metrics(symbol)
    metric = metrics_response.get("metric", {}) if metrics_response else {}

    return FundamentalContext(
        symbol=symbol,
        company_name=profile.get("name"),
        sector=profile.get("finnhubIndustry"),
        market_cap=profile.get("marketCapitalization"),
        pe_ratio=metric.get("peBasicExclExtraTTM"),
        dividend_yield_pct=metric.get("dividendYieldIndicatedAnnual"),
    )