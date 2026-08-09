"""See app/agent/concepts/__init__.py for the rationale.

Deliberately does NOT encode period-specific aliases like "200 dma" ->
SMA(200): mapping such an alias to a bare canonical name while
discarding the period it clearly specifies would silently do the
wrong thing (worse than not recognizing it at all). Extracting a
period from free text is a separate, harder problem than this
directory's job (canonical-name lookup) -- left for a real, deliberate
pass later rather than a token gesture now.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConceptEntry:
    canonical_name: str
    category: str  # "indicator" | "concept"
    registry_name: str | None  # INDICATOR_REGISTRY key; only set for category="indicator"


_ENTRIES: list[ConceptEntry] = [
    ConceptEntry("RSI", "indicator", "RSI"),
    ConceptEntry("SMA", "indicator", "SMA"),
    ConceptEntry("EMA", "indicator", "EMA"),
    ConceptEntry("MOVING_AVERAGE", "concept", None),
    ConceptEntry("TECHNICAL_ANALYSIS", "concept", None),
]

_BY_CANONICAL: dict[str, ConceptEntry] = {e.canonical_name: e for e in _ENTRIES}

_ALIASES: dict[str, str] = {
    "rsi": "RSI",
    "relative strength index": "RSI",
    "relative strength": "RSI",
    "sma": "SMA",
    "simple moving average": "SMA",
    "ema": "EMA",
    "exponential moving average": "EMA",
    "moving average": "MOVING_AVERAGE",
    "moving averages": "MOVING_AVERAGE",
    "technicals": "TECHNICAL_ANALYSIS",
    "technical analysis": "TECHNICAL_ANALYSIS",
    "indicators": "TECHNICAL_ANALYSIS",
}


class ConceptDirectory:
    def lookup(self, text: str) -> ConceptEntry | None:
        normalized = text.strip().lower()
        canonical = _ALIASES.get(normalized)
        if canonical is None and normalized.upper() in _BY_CANONICAL:
            canonical = normalized.upper()
        if canonical is None:
            return None
        return _BY_CANONICAL.get(canonical)