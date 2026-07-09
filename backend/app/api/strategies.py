"""Strategy API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyResponse,
    StrategyVersionCreateRequest,
    StrategyVersionResponse,
)
from app.services import strategy_service

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