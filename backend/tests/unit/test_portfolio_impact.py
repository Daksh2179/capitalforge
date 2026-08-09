"""Unit tests for portfolio-impact (correlation) scoring."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.opportunity.portfolio_impact import (
    MIN_OVERLAPPING_OBSERVATIONS,
    daily_returns,
    portfolio_impact_score,
)


def _bars_from_closes(closes: list[float], symbol: str = "TEST") -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                  open=c, high=c, low=c, close=c, volume=0.0)
        for i, c in enumerate(closes)
    ]


def test_daily_returns_is_one_shorter_than_bars():
    bars = _bars_from_closes([100, 110, 99])
    returns = daily_returns(bars)
    assert len(returns) == 2
    assert returns[0] == 0.1


def test_empty_portfolio_returns_none():
    candidate_bars = _bars_from_closes([100 + i for i in range(25)])
    portfolio = Portfolio(cash=10000.0, positions={})

    score = portfolio_impact_score("NEW", candidate_bars, portfolio, bars_by_symbol={})
    assert score is None


def test_insufficient_overlapping_history_returns_none():
    candidate_bars = _bars_from_closes([100 + i for i in range(5)], symbol="NEW")
    held_bars = _bars_from_closes([50 + i for i in range(5)], symbol="HELD")
    portfolio = Portfolio(
        cash=10000.0,
        positions={"HELD": Position(symbol="HELD", quantity=10, average_entry_price=50.0, current_price=54.0)},
    )

    score = portfolio_impact_score(
        "NEW", candidate_bars, portfolio, bars_by_symbol={"HELD": held_bars}
    )
    assert score is None  # only 4 overlapping returns, below MIN_OVERLAPPING_OBSERVATIONS


def test_perfectly_correlated_holding_scores_near_one():
    n = MIN_OVERLAPPING_OBSERVATIONS + 5
    identical_closes = [100 + i for i in range(n)]
    candidate_bars = _bars_from_closes(identical_closes, symbol="NEW")
    held_bars = _bars_from_closes(identical_closes, symbol="HELD")
    portfolio = Portfolio(
        cash=10000.0,
        positions={"HELD": Position(symbol="HELD", quantity=10, average_entry_price=100.0, current_price=100 + n)},
    )

    score = portfolio_impact_score(
        "NEW", candidate_bars, portfolio, bars_by_symbol={"HELD": held_bars}
    )
    assert score is not None
    assert score > 0.99


def test_larger_holding_dominates_weighted_average():
    n = MIN_OVERLAPPING_OBSERVATIONS + 5
    rising = [100 + i for i in range(n)]
    falling = [200 - i for i in range(n)]
    candidate_bars = _bars_from_closes(rising, symbol="NEW")
    correlated_bars = _bars_from_closes(rising, symbol="BIG")   # correlation ~ +1
    anticorrelated_bars = _bars_from_closes(falling, symbol="SMALL")  # correlation ~ -1

    portfolio = Portfolio(
        cash=10000.0,
        positions={
            "BIG": Position(symbol="BIG", quantity=100, average_entry_price=100.0, current_price=100 + n),
            "SMALL": Position(symbol="SMALL", quantity=1, average_entry_price=200.0, current_price=200 - n),
        },
    )

    score = portfolio_impact_score(
        "NEW", candidate_bars, portfolio,
        bars_by_symbol={"BIG": correlated_bars, "SMALL": anticorrelated_bars},
    )
    # BIG's market_value vastly exceeds SMALL's, so the weighted score
    # should sit close to BIG's correlation (+1), not the unweighted
    # average of +1 and -1 (which would be ~0).
    assert score is not None
    assert score > 0.5