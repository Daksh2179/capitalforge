"""Evaluation job: the orchestrator. Coordinates the pipeline for one
strategy, one cycle. Contains no trading decisions, no indicator math,
no risk logic itself - only calls the components that do, in sequence.

MarketDataProvider -> Rule Evaluator -> Risk Manager -> Broker -> Persistence
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy, StrategyVersion
from app.schemas.strategy import StrategyConfig
from app.services import trading_cycle_service
from app.trading_engine.domain.order import OrderSide, OrderType
from app.trading_engine.domain.signal import SignalAction
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.provider import MarketDataProvider
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.risk.risk_manager import evaluate_risk
from app.trading_engine.rules.evaluator import evaluate_strategy

# V1 constraint (see docs/decisions.md): strategies operate only on
# daily bars. This constant is the single place that assumption lives.
V1_SUPPORTED_TIMEFRAME = Timeframe.DAY
LOOKBACK_DAYS = 60


def run_evaluation_cycle(
    db: Session,
    *,
    strategy: Strategy,
    strategy_version: StrategyVersion,
    market_data: MarketDataProvider,
    broker: Broker,
    risk_limits: RiskLimits,
) -> None:
    config = StrategyConfig.model_validate(strategy_version.config_json)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    bars = market_data.get_historical_bars(config.symbol, V1_SUPPORTED_TIMEFRAME, start, end)

    if not bars:
        return

    signal = evaluate_strategy(bars, config)
    risk_decision = None

    if signal.action == SignalAction.BUY:
        portfolio = broker.get_portfolio()
        risk_decision = evaluate_risk(signal, portfolio, config, risk_limits, current_price=bars[-1].close)

        if risk_decision.approved and risk_decision.quantity:
            domain_order = broker.place_order(
                symbol=config.symbol, side=OrderSide.BUY,
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