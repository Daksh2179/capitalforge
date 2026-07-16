"""Strategy API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.strategy import (
    DecisionLogResponse,
    OrderResponse,
    PortfolioSnapshotResponse,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyVersionCreateRequest,
    StrategyVersionResponse,
)
from app.services import strategy_service, trading_cycle_service

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", response_model=StrategyResponse, status_code=201)
def create_strategy(
    request: StrategyCreateRequest,
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = strategy_service.create_strategy(
        db,
        user_id=request.user_id,
        config_json=request.config.model_dump(),
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
        config_json=request.config.model_dump(),
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