"""Unit tests for the backtest fill simulator."""

from app.trading_engine.backtest.simulator import SimulatedFill, apply_buy_fill, apply_sell_fill
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position


def test_apply_buy_fill_new_position():
    portfolio = Portfolio(cash=10000.0)
    fill = SimulatedFill(symbol="AAPL", quantity=10, price=100.0)

    result = apply_buy_fill(portfolio, fill)

    assert result.cash == 9000.0
    assert result.positions["AAPL"].quantity == 10
    assert result.positions["AAPL"].average_entry_price == 100.0


def test_apply_buy_fill_averages_into_existing_position():
    portfolio = Portfolio(
        cash=9000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=10, average_entry_price=100.0)},
    )
    fill = SimulatedFill(symbol="AAPL", quantity=10, price=120.0)

    result = apply_buy_fill(portfolio, fill)

    assert result.positions["AAPL"].quantity == 20
    assert result.positions["AAPL"].average_entry_price == 110.0  # (10*100 + 10*120) / 20


def test_apply_sell_fill_closes_position_and_computes_pnl():
    portfolio = Portfolio(
        cash=1000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=10, average_entry_price=100.0)},
    )
    fill = SimulatedFill(symbol="AAPL", quantity=10, price=115.0)

    result, realized_pnl = apply_sell_fill(portfolio, fill)

    assert "AAPL" not in result.positions
    assert result.cash == 2150.0  # 1000 + 10*115
    assert realized_pnl == 150.0  # (115-100)*10


def test_apply_sell_fill_without_position_raises():
    portfolio = Portfolio(cash=1000.0)
    fill = SimulatedFill(symbol="AAPL", quantity=10, price=115.0)

    try:
        apply_sell_fill(portfolio, fill)
        assert False, "expected ValueError"
    except ValueError:
        pass