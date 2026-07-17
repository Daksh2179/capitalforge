"""Schemas for market data endpoints exposed to the frontend."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    price: float
    timestamp: datetime