"""Scheduler: wraps APScheduler to run the evaluation cycle for every
active or paused strategy on an interval. Purely mechanical
scheduling -- pipeline logic (including the smart-pause behavior)
lives entirely in evaluation_job.run_evaluation_cycle.

PAUSED strategies are deliberately INCLUDED here, not excluded --
excluding them would mean a paused strategy's stop loss/take profit
stops being monitored at all, which is exactly the unsafe behavior
smart pause was designed to avoid. run_evaluation_cycle itself decides
what a paused strategy's cycle actually does (SELL/exit evaluation in
full, BUY side suspended).

run_all_active_strategies now takes market_data/broker as explicit
parameters rather than constructing them internally -- the one
inconsistency in this module versus every other piece of the trading
engine, which already takes these as injected dependencies. Fixed
here specifically because it's what makes the state-filtering logic
testable without live Alpaca credentials.
"""

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.strategy import Strategy, StrategyState
from app.trading_engine.execution.alpaca_broker import AlpacaBroker
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData
from app.trading_engine.market_data.provider import MarketDataProvider
from app.workers.evaluation_job import run_evaluation_cycle


def run_all_active_strategies(db: Session, market_data: MarketDataProvider, broker: Broker) -> None:
    strategies_to_evaluate = db.execute(
        select(Strategy).where(Strategy.state.in_([StrategyState.ACTIVE, StrategyState.PAUSED]))
    ).scalars().all()

    for strategy in strategies_to_evaluate:
        if strategy.current_version is None:
            continue
        run_evaluation_cycle(
            db, strategy=strategy, strategy_version=strategy.current_version,
            market_data=market_data, broker=broker,
        )


def start_scheduler(db_session_factory: Callable[[], Session], interval_minutes: int = 15) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    settings = get_settings()

    def job() -> None:
        db = db_session_factory()
        try:
            market_data = AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)
            broker = AlpacaBroker(settings.alpaca_api_key, settings.alpaca_secret_key)
            run_all_active_strategies(db, market_data, broker)
        finally:
            db.close()

    scheduler.add_job(job, "interval", minutes=interval_minutes)
    scheduler.start()
    return scheduler