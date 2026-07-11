"""Unit tests for Position and Portfolio computed properties."""

from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position


def test_position_market_value_none_without_current_price():
    position = Position(symbol="AAPL", quantity=10, average_entry_price=100.0)
    assert position.market_value is None
    assert position.unrealized_pl is None


def test_position_market_value_and_unrealized_pl():
    position = Position(symbol="AAPL", quantity=10, average_entry_price=100.0, current_price=110.0)
    assert position.market_value == 1100.0
    assert position.unrealized_pl == 100.0


def test_portfolio_total_value_with_no_positions():
    portfolio = Portfolio(cash=10000.0)
    assert portfolio.positions_value == 0.0
    assert portfolio.total_value == 10000.0


def test_portfolio_total_value_with_positions():
    portfolio = Portfolio(
        cash=5000.0,
        positions={
            "AAPL": Position(symbol="AAPL", quantity=10, average_entry_price=100.0, current_price=110.0),
            "TSLA": Position(symbol="TSLA", quantity=2, average_entry_price=200.0, current_price=190.0),
        },
    )
    assert portfolio.positions_value == 1480.0  # 10*110 + 2*190
    assert portfolio.total_value == 6480.0