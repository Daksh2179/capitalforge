"""Backtest engine: replays a MarketDataProvider's historical bars
through the same rule evaluator and risk manager used live, one bar at
a time, tracking portfolio, trades, and realized P&L along the way.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.strategy import StrategyConfig
from app.trading_engine.backtest.simulator import (
    SimulatedFill,
    apply_buy_fill,
    apply_sell_fill,
    mark_to_market,
)
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.signal import SignalAction
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.provider import MarketDataProvider
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.risk.risk_manager import evaluate_risk
from app.trading_engine.rules.evaluator import evaluate_exit, evaluate_strategy


@dataclass
class BacktestResult:
    starting_cash: float
    ending_portfolio: Portfolio
    trades: list[SimulatedFill] = field(default_factory=list)
    trade_pnls: list[float] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)


def run_backtest(
    provider: MarketDataProvider,
    config: StrategyConfig,
    start: datetime,
    end: datetime,
    starting_cash: float,
    risk_limits: RiskLimits,
) -> BacktestResult:
    all_bars = provider.get_historical_bars(config.symbol, _config_timeframe(config), start, end)

    portfolio = Portfolio(cash=starting_cash)
    trades: list[SimulatedFill] = []
    trade_pnls: list[float] = []
    equity_curve: list[tuple[datetime, float]] = []

    for i in range(len(all_bars)):
        window = all_bars[: i + 1]
        current_bar = all_bars[i]

        portfolio = mark_to_market(portfolio, current_bar)
        existing_position = portfolio.positions.get(config.symbol)

        if existing_position is not None:
            signal = evaluate_exit(existing_position, current_bar, config)
        else:
            signal = evaluate_strategy(window, config)

        if signal.action in (SignalAction.BUY, SignalAction.SELL):
            decision = evaluate_risk(
                signal, portfolio, config, risk_limits, current_price=current_bar.close
            )
            if decision.approved and decision.quantity:
                fill = SimulatedFill(
                    symbol=config.symbol, quantity=decision.quantity, price=current_bar.close
                )
                if signal.action == SignalAction.BUY:
                    portfolio = apply_buy_fill(portfolio, fill)
                    trades.append(fill)
                else:
                    portfolio, realized_pnl = apply_sell_fill(portfolio, fill)
                    trades.append(fill)
                    trade_pnls.append(realized_pnl)

        equity_curve.append((current_bar.timestamp, portfolio.total_value))

    return BacktestResult(
        starting_cash=starting_cash,
        ending_portfolio=portfolio,
        trades=trades,
        trade_pnls=trade_pnls,
        equity_curve=equity_curve,
    )


def _config_timeframe(config: StrategyConfig) -> Timeframe:
    # V1 constraint: strategies operate only on daily bars.
    # StrategyConfig has no timeframe field yet (see docs/decisions.md).
    return Timeframe.DAY
