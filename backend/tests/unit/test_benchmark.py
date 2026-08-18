"""Unit tests for simulate_buy_and_hold."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.backtest.benchmark import simulate_buy_and_hold
from app.trading_engine.domain.market_bar import MarketBar


def _bars(closes: list[float]) -> list[MarketBar]:
    base = datetime.now(timezone.utc) - timedelta(days=len(closes))
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                  open=c, high=c, low=c, close=c, volume=100_000.0)
        for i, c in enumerate(closes)
    ]


def test_buy_and_hold_tracks_price_movement():
    curve = simulate_buy_and_hold(_bars([100.0, 110.0, 90.0]), starting_cash=1000.0)

    assert len(curve) == 3
    assert curve[0][1] == 1000.0
    assert curve[1][1] == 1100.0
    assert curve[2][1] == 900.0


def test_empty_bars_returns_empty_curve():
    assert simulate_buy_and_hold([], starting_cash=1000.0) == []