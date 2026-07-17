"""TickerLogosProvider: the only file permitted to know about
AllInvestView's Ticker Logos service. Two real network calls per
never-before-seen ticker: search API (ticker -> domain), then CDN
(domain -> image bytes).
"""

import httpx
from app.logos.logo_provider import LogoProvider

_SEARCH_URL = "https://www.allinvestview.com/api/logo-search/"
_CDN_BASE = "https://cdn.tickerlogos.com"


class TickerLogosProvider(LogoProvider):
    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    def get_logo(self, ticker: str) -> bytes | None:
        domain = self._resolve_domain(ticker)
        if domain is None:
            return None
        return self._fetch_logo_bytes(domain)

    def _resolve_domain(self, ticker: str) -> str | None:
        response = httpx.get(
            _SEARCH_URL, params={"q": ticker}, timeout=self._timeout
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        return results[0].get("website")

    def _fetch_logo_bytes(self, domain: str) -> bytes | None:
        response = httpx.get(f"{_CDN_BASE}/{domain}", timeout=self._timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content