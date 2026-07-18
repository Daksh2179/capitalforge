"""Schemas for the Portfolio API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PortfolioHoldingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    symbol: str


class PortfolioHoldingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    created_at: datetime
    is_ai_configured: bool