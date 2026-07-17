"""Logo service: fetches, caches, and falls back to generated avatars
for stock ticker logos. Provider-agnostic — TickerLogosProvider is the
only V1 implementation, swappable without touching LogoService or the
API layer.
"""