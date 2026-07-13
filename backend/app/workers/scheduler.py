"""Scheduler: wraps APScheduler to run the evaluation cycle for every
active strategy on an interval. Purely mechanical scheduling — pipeline
logic lives entirely in evaluation_job.run_evaluation_cycle.
"""

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.strategy import Strategy, StrategyState
from app.trading_engine.execution.alpaca_broker import AlpacaBroker
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData
from app.workers.evaluation_job import run_evaluation_cycle


def run_all_active_strategies(db: Session) -> None:
    settings = get_settings()
    market_data = AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)
    broker = AlpacaBroker(settings.alpaca_api_key, settings.alpaca_secret_key)

    active_strategies = db.execute(
        select(Strategy).where(Strategy.state == StrategyState.ACTIVE)
    ).scalars().all()

    for strategy in active_strategies:
        if strategy.current_version is None:
            continue
        run_evaluation_cycle(
            db, strategy=strategy, strategy_version=strategy.current_version,
            market_data=market_data, broker=broker,
        )


def start_scheduler(db_session_factory: Callable[[], Session], interval_minutes: int = 15) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    def job() -> None:
        db = db_session_factory()
        try:
            run_all_active_strategies(db)
        finally:
            db.close()

    scheduler.add_job(job, "interval", minutes=interval_minutes)
    scheduler.start()
    return scheduler