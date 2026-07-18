"""Portfolio API: staging holdings for the user's intended paper
portfolio. Nothing here touches Alpaca or executes anything — this is
purely the Discover -> Build staging layer.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.portfolio import PortfolioHoldingCreateRequest, PortfolioHoldingResponse
from app.services import portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/holdings", response_model=PortfolioHoldingResponse, status_code=201)
def add_holding(
    request: PortfolioHoldingCreateRequest,
    db: Session = Depends(get_db),
) -> PortfolioHoldingResponse:
    holding = portfolio_service.add_holding(db, user_id=request.user_id, symbol=request.symbol.upper())
    is_configured = portfolio_service.is_symbol_ai_configured(
        db, user_id=request.user_id, symbol=holding.symbol
    )
    return PortfolioHoldingResponse(
        id=holding.id, symbol=holding.symbol, created_at=holding.created_at,
        is_ai_configured=is_configured,
    )


@router.get("/holdings", response_model=list[PortfolioHoldingResponse])
def list_holdings(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[PortfolioHoldingResponse]:
    holdings = portfolio_service.list_holdings(db, user_id=user_id)
    return [
        PortfolioHoldingResponse(
            id=h.id, symbol=h.symbol, created_at=h.created_at,
            is_ai_configured=portfolio_service.is_symbol_ai_configured(db, user_id=user_id, symbol=h.symbol),
        )
        for h in holdings
    ]


@router.delete("/holdings/{symbol}", status_code=204)
def remove_holding(
    symbol: str,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    removed = portfolio_service.remove_holding(db, user_id=user_id, symbol=symbol.upper())
    if not removed:
        raise HTTPException(status_code=404, detail="Holding not found")