"""AssetDirectory: fetches and caches the full list of tradable US
equities from Alpaca, and provides fuzzy search over symbol + company
name. This is reference-data lookup, not a trading action — kept
separate from Broker, which owns order/position/account operations.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest


@dataclass(frozen=True)
class AssetEntry:
    symbol: str
    name: str


class AssetDirectory:
    def __init__(
        self, api_key: str, secret_key: str, cache_path: str | Path = "asset_directory_cache.json"
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._cache_path = Path(cache_path)
        self._entries: list[AssetEntry] | None = None

    def search(self, query: str, limit: int = 10) -> list[AssetEntry]:
        entries = self._get_entries()
        stripped = query.strip()
        if not stripped:
            return []

        query_upper = stripped.upper()
        query_lower = stripped.lower()
        scored: list[tuple[float, AssetEntry]] = []

        for entry in entries:
            score = 0.0

            # Exact symbol prefix match is the strongest possible signal
            # ("tsla" -> "TSLA", "aap" -> "AAPL"). Short, close symbols
            # score higher than longer ones.
            if entry.symbol.upper().startswith(query_upper):
                score = 100.0 - len(entry.symbol)

            # Name match: only consider it if the query actually appears
            # in the name, then score inversely to how much of the name
            # is "extra" beyond the query — a name that IS basically the
            # query ("Tesla, Inc.") scores much higher than a long name
            # that merely mentions it ("Corgi TSLA 2x Daily ETF").
            name_lower = entry.name.lower()
            if query_lower in name_lower:
                extra_length = len(name_lower) - len(query_lower)
                name_score = max(0.0, 90.0 - extra_length)
                if name_lower.startswith(query_lower):
                    name_score += 10.0
                score = max(score, name_score)

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in scored[:limit]]
    
    def _get_entries(self) -> list[AssetEntry]:
        if self._entries is not None:
            return self._entries

        if self._cache_path.exists():
            self._entries = self._load_cache()
        else:
            self._entries = self._fetch_and_cache()

        return self._entries

    def _load_cache(self) -> list[AssetEntry]:
        raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
        return [AssetEntry(symbol=e["symbol"], name=e["name"]) for e in raw]

    def _fetch_and_cache(self) -> list[AssetEntry]:
        client = TradingClient(self._api_key, self._secret_key, paper=True)
        request = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE)
        assets = client.get_all_assets(request)

        entries = []
        for asset in assets:
            if isinstance(asset, str):
                # Only possible with raw_data=True, which we never pass —
                # narrows the type for mypy and fails loudly if it ever
                # unexpectedly occurs.
                continue
            if asset.tradable and asset.symbol and asset.name:
                entries.append(AssetEntry(symbol=asset.symbol, name=asset.name))

        self._cache_path.write_text(
            json.dumps([{"symbol": e.symbol, "name": e.name} for e in entries]),
            encoding="utf-8",
        )
        return entries