"""Stage 2 of the Opportunity Engine: portfolio-impact evaluation.

Scores a candidate by its correlation with the portfolio's *existing*
holdings, weighted by each holding's current market value -- a larger
existing position contributes more to concentration than a smaller
one. This is a structural, backward-looking fact about the portfolio
the user already built, not a claim about which candidate will
perform better (see docs/decisions.md for why indicator-magnitude
scoring was rejected in favor of this).

Returns None when correlation can't be computed with reasonable
confidence: an empty portfolio, or no held symbol having enough
overlapping return history with the candidate. Callers must treat
None as "no evidence available," never as "zero correlation," and
fall back to the deterministic procedural policy instead.
"""

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.portfolio import Portfolio

MIN_OVERLAPPING_OBSERVATIONS = 20


def daily_returns(bars: list[MarketBar]) -> list[float]:
    """Simple close-to-close percentage returns, oldest-first -- one
    element shorter than `bars`, since a return needs two prices."""
    returns = []
    for prev, curr in zip(bars, bars[1:]):
        if prev.close != 0:
            returns.append((curr.close - prev.close) / prev.close)
    return returns


def _pearson_correlation(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < MIN_OVERLAPPING_OBSERVATIONS:
        return None
    a, b = a[-n:], b[-n:]

    mean_a = sum(a) / n
    mean_b = sum(b) / n
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    variance_a = sum((x - mean_a) ** 2 for x in a)
    variance_b = sum((y - mean_b) ** 2 for y in b)

    denominator = (variance_a * variance_b) ** 0.5
    if denominator == 0:
        return None
    return covariance / denominator


def portfolio_impact_score(
    candidate_symbol: str,
    candidate_bars: list[MarketBar],
    portfolio: Portfolio,
    bars_by_symbol: dict[str, list[MarketBar]],
) -> float | None:
    """Weighted-average correlation between the candidate and each of
    the portfolio's current holdings, weighted by each holding's
    market value. A holding whose correlation can't be computed is
    excluded entirely (not treated as zero) -- weights are
    renormalized across whatever remains computable.
    """
    candidate_returns = daily_returns(candidate_bars)

    weighted_terms: list[tuple[float, float]] = []  # (correlation, weight)
    for symbol, position in portfolio.positions.items():
        if symbol == candidate_symbol:
            continue
        held_bars = bars_by_symbol.get(symbol)
        if not held_bars:
            continue
        held_returns = daily_returns(held_bars)
        correlation = _pearson_correlation(candidate_returns, held_returns)
        if correlation is None:
            continue
        weight = position.market_value or 0.0
        if weight <= 0:
            continue
        weighted_terms.append((correlation, weight))

    if not weighted_terms:
        return None

    total_weight = sum(weight for _, weight in weighted_terms)
    if total_weight <= 0:
        return None

    return sum(correlation * weight for correlation, weight in weighted_terms) / total_weight