"""Unit tests for get_fundamental_context -- fake FinnhubClient, no
real network calls."""

from app.agent.context.fundamental_context import get_fundamental_context


class FakeFinnhubClient:
    def __init__(self, profile: dict, metrics: dict | None = None) -> None:
        self._profile = profile
        self._metrics = metrics or {}

    def get_profile(self, symbol: str) -> dict:
        return self._profile

    def get_metrics(self, symbol: str) -> dict:
        return self._metrics


def test_builds_context_from_confirmed_real_field_names():
    client = FakeFinnhubClient(
        profile={"name": "Apple Inc", "finnhubIndustry": "Technology Hardware", "marketCapitalization": 2800000.0},
        metrics={"metric": {"peBasicExclExtraTTM": 32.1, "dividendYieldIndicatedAnnual": 0.45}},
    )
    context = get_fundamental_context("AAPL", client)

    assert context.company_name == "Apple Inc"
    assert context.sector == "Technology Hardware"
    assert context.market_cap == 2800000.0
    assert context.pe_ratio == 32.1
    assert context.dividend_yield_pct == 0.45


def test_empty_profile_returns_none():
    client = FakeFinnhubClient(profile={})
    assert get_fundamental_context("NONEXISTENT", client) is None


def test_missing_metrics_fields_default_to_none_not_zero():
    client = FakeFinnhubClient(profile={"name": "Test Co"}, metrics={"metric": {}})
    context = get_fundamental_context("TEST", client)

    assert context.pe_ratio is None
    assert context.dividend_yield_pct is None