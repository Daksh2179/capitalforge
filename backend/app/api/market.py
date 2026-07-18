"""Market data API: thin read endpoints for the frontend's Markets
page. Reuses AlpacaMarketData exactly as the engine already does —
no new data source, just a new consumer of an existing one.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.schemas.market import HistoricalBarResponse, QuoteResponse
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData
from app.trading_engine.market_data.provider import MarketDataProvider
from app.assets.asset_directory import AssetDirectory, AssetEntry

router = APIRouter(prefix="/market", tags=["market"])


def _get_market_data() -> MarketDataProvider:
    settings = get_settings()
    return AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)


@router.get("/{symbol}/quote", response_model=QuoteResponse)
def get_quote(
    symbol: str,
    market_data: MarketDataProvider = Depends(_get_market_data),
) -> QuoteResponse:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=14)
    bars = market_data.get_historical_bars(symbol.upper(), Timeframe.DAY, start, end)

    if not bars:    
        raise HTTPException(status_code=404, detail=f"No recent data for symbol {symbol}")

    latest = bars[-1]
    return QuoteResponse(symbol=symbol.upper(), price=latest.close, timestamp=latest.timestamp)

def _get_asset_directory() -> AssetDirectory:
    settings = get_settings()
    return AssetDirectory(settings.alpaca_api_key, settings.alpaca_secret_key)


@router.get("/search")
def search_assets(
    q: str,
    directory: AssetDirectory = Depends(_get_asset_directory),
) -> list[AssetEntry]:
    return directory.search(q)

@router.get("/{symbol}/history", response_model=list[HistoricalBarResponse])
def get_history(
    symbol: str,
    days: int = 90,
    market_data: MarketDataProvider = Depends(_get_market_data),
) -> list[HistoricalBarResponse]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    bars = market_data.get_historical_bars(symbol.upper(), Timeframe.DAY, start, end)

    if not bars:
        raise HTTPException(status_code=404, detail=f"No historical data for symbol {symbol}")

    return [HistoricalBarResponse(timestamp=b.timestamp, close=b.close) for b in bars]