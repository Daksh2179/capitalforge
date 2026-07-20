"""Evaluation job: the orchestrator. Coordinates the pipeline for one
Portfolio Strategy, one cycle, looping over every AssetRule inside it.
Contains no trading decisions, no indicator math, no risk logic itself
- only calls the components that do, in sequence, once per asset.

MarketDataProvider -> Rule Evaluator (entry or exit) -> Risk Manager -> Broker -> Persistence
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy, StrategyVersion
from app.schemas.strategy import PortfolioRules, StrategyConfig
from app.services import trading_cycle_service
from app.trading_engine.domain.order import OrderSide, OrderType
from app.trading_engine.domain.signal import SignalAction
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.provider import MarketDataProvider
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.risk.risk_manager import evaluate_risk
from app.trading_engine.rules.evaluator import evaluate_exit, evaluate_strategy

# V1 constraint (see docs/decisions.md): strategies operate only on
# daily bars. This constant is the single place that assumption lives.
V1_SUPPORTED_TIMEFRAME = Timeframe.DAY
LOOKBACK_DAYS = 60


def build_risk_limits(portfolio_rules: PortfolioRules) -> RiskLimits:
    """Construct RiskLimits from a strategy's PortfolioRules, falling
    back to engine defaults for any field the user didn't specify.
    """
    defaults = RiskLimits()
    return RiskLimits(
        max_position_pct=defaults.max_position_pct,
        max_portfolio_deployment_pct=(
            (portfolio_rules.max_allocation_pct / 100)
            if portfolio_rules.max_allocation_pct is not None
            else defaults.max_portfolio_deployment_pct
        ),
        min_cash_reserve_pct=(
            (portfolio_rules.cash_reserve_pct / 100)
            if portfolio_rules.cash_reserve_pct is not None
            else defaults.min_cash_reserve_pct
        ),
        max_open_positions=portfolio_rules.max_open_positions,
        total_capital_usd=portfolio_rules.total_capital_usd,
    )


def run_evaluation_cycle(
    db: Session,
    *,
    strategy: Strategy,
    strategy_version: StrategyVersion,
    market_data: MarketDataProvider,
    broker: Broker,
) -> None:
    config = StrategyConfig.model_validate(strategy_version.config_json)
    risk_limits = build_risk_limits(config.portfolio_rules)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)

    for rule in config.asset_rules:
        _evaluate_one_asset(
            db, strategy=strategy, strategy_version=strategy_version, rule=rule,
            market_data=market_data, broker=broker, risk_limits=risk_limits,
            start=start, end=end,
        )


def _evaluate_one_asset(
    db: Session, *, strategy: Strategy, strategy_version: StrategyVersion, rule,
    market_data: MarketDataProvider, broker: Broker, risk_limits: RiskLimits,
    start: datetime, end: datetime,
) -> None:
    bars = market_data.get_historical_bars(rule.symbol, V1_SUPPORTED_TIMEFRAME, start, end)
    if not bars:
        return

    portfolio = broker.get_portfolio()
    existing_position = portfolio.positions.get(rule.symbol)

    if existing_position is not None:
        signal = evaluate_exit(existing_position, bars, rule)
    else:
        signal = evaluate_strategy(bars, rule)

    risk_decision = None

    if signal.action in (SignalAction.BUY, SignalAction.SELL):
        risk_decision = evaluate_risk(signal, portfolio, rule, risk_limits, current_price=bars[-1].close)

        if risk_decision.approved and risk_decision.quantity:
            side = OrderSide.BUY if signal.action == SignalAction.BUY else OrderSide.SELL
            domain_order = broker.place_order(
                symbol=rule.symbol, side=side,
                order_type=OrderType.MARKET, quantity=risk_decision.quantity,
            )
            trading_cycle_service.record_order(
                db, strategy_version_id=strategy_version.id, domain_order=domain_order
            )

    trading_cycle_service.log_decision(
        db, strategy_version_id=strategy_version.id, latest_bar=bars[-1],
        signal=signal, risk_decision=risk_decision,
    )

    portfolio = broker.get_portfolio()
    trading_cycle_service.record_portfolio_snapshot(db, strategy_id=strategy.id, portfolio=portfolio)