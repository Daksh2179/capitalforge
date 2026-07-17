"""Logo endpoint: always returns a real image, never a 404 — either
a fetched/cached logo or a generated avatar.
"""

from fastapi import APIRouter, Depends, Response

from app.logos.logo_cache import LogoCache
from app.logos.logo_service import LogoService
from app.logos.ticker_logos_provider import TickerLogosProvider

router = APIRouter(prefix="/logos", tags=["logos"])


def _get_logo_service() -> LogoService:
    return LogoService(TickerLogosProvider(), LogoCache())


@router.get("/{ticker}")
def get_logo(ticker: str, service: LogoService = Depends(_get_logo_service)) -> Response:
    image_bytes = service.get_logo_bytes(ticker)
    return Response(content=image_bytes, media_type="image/png")