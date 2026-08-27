"""Shared starting-capital resolution for backtesting -- used by both
BacktestAnalystAgent (chat) and the structured GET /backtest REST
endpoint, so the two paths can never silently drift on what "starting
capital" means for a given strategy.

Priority, in order: the strategy's own declared total_capital_usd pool
(a deliberate statement of what this strategy is allowed to manage,
more relevant than the account's real total balance for a backtest of
THIS strategy specifically), then the real recorded account balance,
then a labeled default when neither exists yet.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.strategy import StrategyConfig
from app.services import trading_cycle_service

DEFAULT_STARTING_CASH = 100_000.0


def resolve_starting_cash(
    db: Session, strategy_id: UUID | None, current_config: StrategyConfig | None
) -> tuple[float, str]:
    if current_config is not None and current_config.portfolio_rules.total_capital_usd is not None:
        return current_config.portfolio_rules.total_capital_usd, "your strategy's declared trading pool"
    if strategy_id is not None:
        snapshots = trading_cycle_service.list_portfolio_snapshots(db, strategy_id=strategy_id, limit=1)
        if snapshots:
            return snapshots[0].total_value, "your current paper account balance"
    return DEFAULT_STARTING_CASH, "a default assumed simulation balance (no recorded account balance yet)"