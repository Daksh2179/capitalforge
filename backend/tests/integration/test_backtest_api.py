"""Integration tests for GET /strategies/{id}/backtest -- the
structured, chat-independent counterpart to BacktestAnalystAgent.
Strategies are created directly via strategy_service (same convention
as test_backtest_analyst_agent.py's helpers) rather than through the
chat pipeline, since this endpoint's whole point is not depending on it.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.strategies import _get_market_data_provider
from app.main import app
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.schemas.strategy import StrategyVersionSource
from app.services import strategy_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, timeframe, start, end):
        base = datetime.now(timezone.utc) - timedelta(days=250)
        return [
            MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                      open=100, high=110, low=90, close=100 + i, volume=100_000.0)
            for i in range(250)
        ]


def _override_market_data() -> None:
    app.dependency_overrides[_get_market_data_provider] = lambda: FakeMarketDataProvider()


def _clear_overrides() -> None:
    app.dependency_overrides.pop(_get_market_data_provider, None)


def _rule(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "buy_conditions": {"operator": "AND", "rules": [
            {"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}
        ]},
        "sell_conditions": {"operator": "AND", "rules": [
            {"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 500}
        ]},
        "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 10},
        "exit": {"stop_loss_pct": 5, "take_profit_pct": None},
    }


def _create_strategy(db_session: Session, asset_rules: list[dict], portfolio_rules: dict | None = None):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3,
            "portfolio_rules": portfolio_rules or {},
            "asset_rules": asset_rules,
        },
        source=StrategyVersionSource.MANUAL, confirmed_now=True,
    )
    db_session.refresh(strategy)
    return strategy


def test_backtest_endpoint_returns_structured_metrics_for_single_rule(client: TestClient, db_session: Session):
    strategy = _create_strategy(db_session, [_rule("AAPL")])
    _override_market_data()

    response = client.get(f"/strategies/{strategy.id}/backtest?days=90")
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert len(body["rules"]) == 1
    rule_metrics = body["rules"][0]
    assert rule_metrics["symbol"] == "AAPL"
    assert rule_metrics["starting_capital"] == 100_000.0
    assert rule_metrics["period_start"] is not None
    assert rule_metrics["period_end"] is not None
    # Not asserting an exact value for any of these -- they're
    # computed by run_backtest/metrics.py, the actual source of truth.
    # Just confirming they're genuinely present in the response shape.
    assert "total_return_pct" in rule_metrics
    assert "max_drawdown_pct" in rule_metrics
    assert "sharpe_ratio" in rule_metrics
    assert "win_rate_pct" in rule_metrics
    assert isinstance(rule_metrics["trade_count"], int)
    assert body["limitations"] == []


def test_backtest_endpoint_flags_multi_rule_limitation(client: TestClient, db_session: Session):
    strategy = _create_strategy(db_session, [_rule("AAPL"), _rule("NVDA")])
    _override_market_data()

    response = client.get(f"/strategies/{strategy.id}/backtest?days=90")
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert len(body["rules"]) == 2
    assert any("independently" in limitation for limitation in body["limitations"])


def test_backtest_endpoint_prefers_declared_pool_as_starting_capital(client: TestClient, db_session: Session):
    strategy = _create_strategy(
        db_session, [_rule("AAPL")], portfolio_rules={"total_capital_usd": 2500.0},
    )
    _override_market_data()

    response = client.get(f"/strategies/{strategy.id}/backtest?days=90")
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["capital_label"] == "your strategy's declared trading pool"
    assert body["rules"][0]["starting_capital"] == 2500.0


def test_backtest_endpoint_prefers_real_snapshot_over_default_when_no_pool_declared(
    client: TestClient, db_session: Session
):
    strategy = _create_strategy(db_session, [_rule("AAPL")])
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=8000.0, positions_json={}, total_value=8000.0,
    ))
    db_session.commit()
    _override_market_data()

    response = client.get(f"/strategies/{strategy.id}/backtest?days=90")
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["capital_label"] == "your current paper account balance"
    assert body["rules"][0]["starting_capital"] == 8000.0


def test_backtest_endpoint_includes_one_benchmark_per_rule(client: TestClient, db_session: Session):
    strategy = _create_strategy(db_session, [_rule("AAPL"), _rule("NVDA")])
    _override_market_data()

    response = client.get(f"/strategies/{strategy.id}/backtest?days=90")
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    benchmark_symbols = {b["symbol"] for b in body["benchmarks"]}
    assert benchmark_symbols == {"AAPL", "NVDA"}


def test_backtest_endpoint_returns_404_for_unknown_strategy(client: TestClient):
    _override_market_data()
    response = client.get(f"/strategies/{uuid.uuid4()}/backtest")
    _clear_overrides()

    assert response.status_code == 404


def test_backtest_endpoint_returns_400_when_no_asset_rules(client: TestClient, db_session: Session):
    strategy = _create_strategy(db_session, [])
    _override_market_data()

    response = client.get(f"/strategies/{strategy.id}/backtest")
    _clear_overrides()

    assert response.status_code == 400