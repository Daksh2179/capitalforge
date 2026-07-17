"""LogoService: the orchestrator. Cache check -> provider fetch ->
cache write -> deterministic avatar fallback. This is the only class
the API layer talks to — it has no idea a provider or cache exists
underneath.
"""

import logging

from app.logos.avatar_generator import generate_avatar
from app.logos.logo_cache import LogoCache
from app.logos.logo_provider import LogoProvider

logger = logging.getLogger(__name__)


class LogoService:
    def __init__(self, provider: LogoProvider, cache: LogoCache) -> None:
        self._provider = provider
        self._cache = cache

    def get_logo_bytes(self, ticker: str) -> bytes:
        """Always returns real image bytes — either a cached/fetched
        real logo, or a generated avatar. Never raises for a normal
        "no logo" case; only truly unexpected errors propagate.
        """
        cached = self._cache.get(ticker)
        if cached is not None:
            return cached

        if self._cache.has_negative_cache(ticker):
            return generate_avatar(ticker)

        try:
            fetched = self._provider.get_logo(ticker)
        except Exception:
            # Transient provider failure (network, rate limit) is
            # never negatively cached — only a confident "no logo"
            # response is. Fall back to the avatar for this request,
            # but let a future request try the provider again.
            logger.warning("Logo provider failed for %s", ticker, exc_info=True)
            return generate_avatar(ticker)

        if fetched is None:
            self._cache.save_negative_cache(ticker)
            return generate_avatar(ticker)

        self._cache.save(ticker, fetched)
        return fetched