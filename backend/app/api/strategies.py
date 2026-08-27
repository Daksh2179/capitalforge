"""Strategy API routes."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.schemas.backtest import BacktestComparison, BacktestMetrics, BacktestStructuredResult
from app.schemas.strategy import (
    DecisionLogResponse,
    OrderResponse,
    PortfolioSnapshotResponse,
    StrategyConfig,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyState,
    StrategyVersionCreateRequest,
    StrategyVersionResponse,
)
from app.services import strategy_service, trading_cycle_service
from app.trading_engine.backtest.benchmark import simulate_buy_and_hold
from app.trading_engine.backtest.engine import run_backtest
from app.trading_engine.backtest.metrics import max_drawdown_pct, sharpe_ratio, total_return_pct, win_rate_pct
from app.trading_engine.backtest.starting_capital import resolve_starting_cash
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData
from app.trading_engine.market_data.provider import MarketDataProvider
from app.workers.evaluation_job import build_risk_limits

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _get_market_data_provider() -> MarketDataProvider:
    """Deliberately duplicated from api/agent.py's identical private
    function rather than shared, to avoid touching agent.py's existing
    dependency-override wiring (its tests reference that function by
    identity) for the sake of this one small, low-risk endpoint. A
    genuine small-scale duplication, not a calculation duplication --
    flagged here rather than silently done."""
    settings = get_settings()
    return AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)


@router.post("", response_model=StrategyResponse, status_code=201)
def create_strategy(
    request: StrategyCreateRequest,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = strategy_service.create_strategy(
        db,
        user_id=request.user_id,
        config_json=request.config.model_dump(mode="json"),
        source=request.source,
    )
    return StrategyResponse.model_validate(strategy)


@router.get("", response_model=list[StrategyResponse])
def list_strategies(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[StrategyResponse]:
    strategies = strategy_service.list_strategies(db, user_id=user_id)
    return [StrategyResponse.model_validate(s) for s in strategies]


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return StrategyResponse.model_validate(strategy)


@router.post(
    "/{strategy_id}/versions",
    response_model=StrategyVersionResponse,
    status_code=201,
)
def create_strategy_version(
    strategy_id: uuid.UUID,
    request: StrategyVersionCreateRequest,
    db: Session = Depends(get_db),
) -> StrategyVersionResponse:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    version = strategy_service.create_new_version(
        db,
        strategy=strategy,
        config_json=request.config.model_dump(mode="json"),
        source=request.source,
    )
    return StrategyVersionResponse.model_validate(version)


@router.get("/{strategy_id}/decision-logs", response_model=list[DecisionLogResponse])
def get_decision_logs(
    strategy_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[DecisionLogResponse]:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None or strategy.current_version_id is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    logs = trading_cycle_service.list_decision_logs(
        db, strategy_version_id=strategy.current_version_id, limit=limit
    )
    return [DecisionLogResponse.model_validate(log) for log in logs]


@router.get("/{strategy_id}/orders", response_model=list[OrderResponse])
def get_orders(
    strategy_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[OrderResponse]:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None or strategy.current_version_id is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    orders = trading_cycle_service.list_orders(
        db, strategy_version_id=strategy.current_version_id, limit=limit
    )
    return [OrderResponse.model_validate(o) for o in orders]


@router.get("/{strategy_id}/portfolio-snapshots", response_model=list[PortfolioSnapshotResponse])
def get_portfolio_snapshots(
    strategy_id: uuid.UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[PortfolioSnapshotResponse]:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    snapshots = trading_cycle_service.list_portfolio_snapshots(
        db, strategy_id=strategy_id, limit=limit
    )
    return [PortfolioSnapshotResponse.model_validate(s) for s in snapshots]

@router.get("/{strategy_id}/current-version", response_model=StrategyVersionResponse)
def get_current_version(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyVersionResponse:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None or strategy.current_version is None:
        raise HTTPException(status_code=404, detail="No current version found")
    return StrategyVersionResponse.model_validate(strategy.current_version)

@router.post("/{strategy_id}/pause", response_model=StrategyResponse)
def pause_strategy(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if strategy.state != StrategyState.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause a strategy in state '{strategy.state.value}' -- only an active strategy can be paused",
        )

    strategy.state = StrategyState.PAUSED
    db.commit()
    return StrategyResponse.model_validate(strategy)


@router.post("/{strategy_id}/resume", response_model=StrategyResponse)
def resume_strategy(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if strategy.state != StrategyState.PAUSED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume a strategy in state '{strategy.state.value}' -- only a paused strategy can be resumed",
        )

    strategy.state = StrategyState.ACTIVE
    db.commit()
    return StrategyResponse.model_validate(strategy)

@router.get("/{strategy_id}/backtest", response_model=BacktestStructuredResult)
def get_backtest(
    strategy_id: uuid.UUID,
    days: int = 90,
    db: Session = Depends(get_db),
    market_data: MarketDataProvider = Depends(_get_market_data_provider),
) -> BacktestStructuredResult:
    strategy = strategy_service.get_strategy(db, strategy_id=strategy_id)
    if strategy is None or strategy.current_version is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        config = StrategyConfig.model_validate(strategy.current_version.config_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Strategy configuration could not be parsed") from exc

    if not config.asset_rules:
        raise HTTPException(status_code=400, detail="Strategy has no rules to backtest")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    starting_cash, capital_label = resolve_starting_cash(db, strategy_id, config)
    risk_limits = build_risk_limits(config.portfolio_rules)

    rule_metrics: list[BacktestMetrics] = []
    benchmark_comparisons: list[BacktestComparison] = []

    for rule in config.asset_rules:
        result = run_backtest(market_data, rule, start, end, starting_cash, risk_limits)

        rule_metrics.append(BacktestMetrics(
            symbol=rule.symbol,
            period_start=result.equity_curve[0][0] if result.equity_curve else None,
            period_end=result.equity_curve[-1][0] if result.equity_curve else None,
            starting_capital=starting_cash,
            ending_capital=result.equity_curve[-1][1] if result.equity_curve else None,
            total_return_pct=total_return_pct(result.equity_curve),
            max_drawdown_pct=max_drawdown_pct(result.equity_curve),
            sharpe_ratio=sharpe_ratio(result.equity_curve),
            trade_count=len(result.trades),
            win_rate_pct=win_rate_pct(result.trade_pnls),
        ))

        # Default benchmark: buy-and-hold of this rule's own symbol,
        # over the identical window -- deterministic, no entity
        # resolution needed for a REST trigger with no chat message.
        bars = market_data.get_historical_bars(rule.symbol, Timeframe.DAY, start, end)
        if bars:
            benchmark_curve = simulate_buy_and_hold(bars, starting_cash)
            benchmark_comparisons.append(BacktestComparison(
                symbol=rule.symbol,
                total_return_pct=total_return_pct(benchmark_curve),
                max_drawdown_pct=max_drawdown_pct(benchmark_curve),
            ))

    limitations = []
    if len(config.asset_rules) > 1:
        limitations.append(
            "Each rule in this strategy was backtested independently with the full assumed balance -- "
            "this does not model how they would actually compete for the same capital together."
        )

    return BacktestStructuredResult(
        capital_label=capital_label,
        rules=rule_metrics,
        benchmarks=benchmark_comparisons,
        limitations=limitations,
    )