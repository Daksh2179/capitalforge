"""Unit tests for performance metrics, using small hand-verifiable
equity curves."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.backtest.metrics import (
    daily_returns,
    max_drawdown_pct,
    sharpe_ratio,
    total_return_pct,
    win_rate_pct,
)


def _curve(values: list[float]) -> list[tuple[datetime, float]]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [(base + timedelta(days=i), v) for i, v in enumerate(values)]


def test_total_return_pct_normal_case():
    curve = _curve([10000, 11000])
    assert total_return_pct(curve) == 10.0


def test_total_return_pct_insufficient_data():
    assert total_return_pct(_curve([10000])) is None
    assert total_return_pct([]) is None


def test_max_drawdown_pct_no_drawdown():
    curve = _curve([100, 110, 120, 130])
    assert max_drawdown_pct(curve) == 0.0


def test_max_drawdown_pct_single_drop():
    # peak 100, drops to 80 -> 20% drawdown
    curve = _curve([100, 90, 80, 95])
    assert max_drawdown_pct(curve) == 20.0


def test_max_drawdown_pct_multiple_peaks():
    curve = _curve([100, 50, 120, 60])  # 50% dd, new peak 120, then 50% dd again
    result = max_drawdown_pct(curve)
    assert result == 50.0


def test_daily_returns_normal_case():
    curve = _curve([100, 110, 99])
    returns = daily_returns(curve)
    assert len(returns) == 2
    assert abs(returns[0] - 0.10) < 1e-9
    assert abs(returns[1] - (-0.10)) < 1e-9


def test_sharpe_ratio_insufficient_data_returns_none():
    assert sharpe_ratio(_curve([100])) is None
    assert sharpe_ratio(_curve([100, 105])) is None  # only 1 return, need 2+


def test_sharpe_ratio_zero_variance_returns_none():
    # Constant daily return every period -> zero variance -> undefined Sharpe.
    curve = _curve([100, 110, 121, 133.1])  # exactly 10% every day
    assert sharpe_ratio(curve) is None


def test_sharpe_ratio_computes_for_varying_returns():
    curve = _curve([100, 110, 105, 115, 108])
    result = sharpe_ratio(curve)
    assert result is not None
    assert isinstance(result, float)


def test_win_rate_pct_normal_case():
    assert win_rate_pct([10, -5, 20, -3, 8]) == 60.0


def test_win_rate_pct_no_trades_returns_none():
    assert win_rate_pct([]) is None


def test_win_rate_pct_all_losses():
    assert win_rate_pct([-1, -2, -3]) == 0.0