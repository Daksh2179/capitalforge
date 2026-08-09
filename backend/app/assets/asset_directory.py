"""AssetDirectory: fetches and caches the full list of tradable US
equities from Alpaca, and provides fuzzy search over symbol + company
name. This is reference-data lookup, not a trading action — kept
separate from Broker, which owns order/position/account operations.

Strengthened per docs/decisions.md: real score distributions (run
against curated, verified ticker/name data — see decisions.md for the
full investigation) showed the original matcher failing completely on
ordinary queries like "Google", "Facebook", "Coca Cola", and "Tesla
Inc", and silently resolving a plausible Apple typo to an unrelated
company (APLE, Apple Hospitality REIT) with no ambiguity signal at
all. Fixed at the source rather than compensated for downstream in
Grounding, so every future consumer (TranslationService, Grounding,
and every later Agent) benefits from one strong resolver instead of
each accumulating its own workaround.

Normalization and aliasing are applied only to the boolean match
checks (startswith / substring), never to the score arithmetic itself
— score magnitudes still derive from the original, un-normalized
string lengths, so the empirically-validated score distribution and
ambiguity threshold (see grounding.py) remain exactly as measured.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest


@dataclass(frozen=True)
class AssetEntry:
    symbol: str
    name: str


@dataclass(frozen=True)
class AssetSearchResult:
    entry: AssetEntry
    score: float


# Deterministic aliases only — no fuzzy AI, no heuristics. Applied
# additively (see search_scored): both the original query AND, if an
# alias exists, the alias's target are searched, and the higher score
# per entry wins. This means a literal ticker match is never
# suppressed by an alias, only supplemented by it. Lowercase keys,
# matched against the same normalized form used for name matching.
_ALIASES: dict[str, str] = {
    "google": "alphabet",
    "google inc": "alphabet",
    "facebook": "meta",
    "fb": "meta",
    "coca cola": "coca cola company",
}


def _normalize_for_symbol_match(text: str) -> str:
    """Ticker symbols have no internal spaces or punctuation
    conceptually (BRK.A is "BRKA" in spirit) — strip periods, spaces,
    and hyphens entirely so "BRK.A", "BRK A", and "BRKA" all compare
    equal."""
    return text.upper().replace(".", "").replace(" ", "").replace("-", "")


def _normalize_for_name_match(text: str) -> str:
    """Company names vary in punctuation users have no reason to type
    correctly (commas, hyphens, parentheses) — fold all of it to a
    single space so "Tesla Inc" matches "Tesla, Inc.", "Coca Cola"
    matches "Coca-Cola", and "(The)" doesn't break a match."""
    text = text.lower()
    text = re.sub(r"[.,'\-()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class AssetDirectory:
    def __init__(
        self, api_key: str, secret_key: str, cache_path: str | Path = "asset_directory_cache.json"
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._cache_path = Path(cache_path)
        self._entries: list[AssetEntry] | None = None

    def search(self, query: str, limit: int = 10) -> list[AssetEntry]:
        """Thin compatibility wrapper — unchanged behavior for every
        existing caller. search_scored is the real implementation."""
        return [result.entry for result in self.search_scored(query, limit)]

    def search_scored(self, query: str, limit: int = 10) -> list[AssetSearchResult]:
        entries = self._get_entries()
        stripped = query.strip()
        if not stripped:
            return []

        results = self._score_all(entries, stripped)

        alias_target = _ALIASES.get(_normalize_for_name_match(stripped))
        if alias_target:
            alias_results = self._score_all(entries, alias_target)
            best: dict[str, AssetSearchResult] = {r.entry.symbol: r for r in results}
            for r in alias_results:
                if r.entry.symbol not in best or r.score > best[r.entry.symbol].score:
                    best[r.entry.symbol] = r
            results = list(best.values())

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _score_all(self, entries: list[AssetEntry], query: str) -> list[AssetSearchResult]:
        query_symbol_form = _normalize_for_symbol_match(query)
        query_name_form = _normalize_for_name_match(query)
        scored: list[AssetSearchResult] = []

        for entry in entries:
            score = 0.0

            # Exact symbol prefix match is the strongest possible signal.
            # Score magnitude still uses the ORIGINAL symbol length, not
            # the normalized form — preserves the exact score arithmetic
            # already validated against real data.
            entry_symbol_form = _normalize_for_symbol_match(entry.symbol)
            if entry_symbol_form.startswith(query_symbol_form) and query_symbol_form:
                score = 100.0 - len(entry.symbol)

            # Name match, same normalized-comparison-but-original-length
            # principle.
            entry_name_form = _normalize_for_name_match(entry.name)
            if query_name_form and query_name_form in entry_name_form:
                extra_length = len(entry.name) - len(query)
                name_score = max(0.0, 90.0 - extra_length)
                if entry_name_form.startswith(query_name_form):
                    name_score += 10.0
                score = max(score, name_score)

            if score > 0:
                scored.append(AssetSearchResult(entry=entry, score=score))

        return scored

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
                continue
            if asset.tradable and asset.symbol and asset.name:
                entries.append(AssetEntry(symbol=asset.symbol, name=asset.name))

        self._cache_path.write_text(
            json.dumps([{"symbol": e.symbol, "name": e.name} for e in entries]),
            encoding="utf-8",
        )
        return entries