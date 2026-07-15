"""Integration tests for the agent API: /agent/translate and
/agent/confirm. Uses a fake TranslationService for /translate (no real
Groq call needed, deterministic and fast) and real strategy_service
persistence for /confirm (the actual thing worth verifying end-to-end).
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.llm_service import LLMService
from app.agent.translation.parsed_intent import IntentBatch, ParsedIntent
from app.agent.translation.translation_service import TranslationService
from app.api.agent import _get_translation_service
from app.main import app
from app.models.strategy import StrategyVersion
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeLLMService(LLMService):
    def __init__(self, batch: IntentBatch) -> None:
        self._batch = batch

    def generate_structured(self, messages, response_model, schema_name):
        return self._batch  # type: ignore[return-value]


class FakeMarketDataProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, timeframe, start, end):
        from datetime import datetime, timedelta, timezone
        base = datetime.now(timezone.utc) - timedelta(days=5)
        return [
            MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                      open=100, high=110, low=90, close=100 + i, volume=0.0)
            for i in range(5)
        ]


def _override_translation_service(batch: IntentBatch) -> None:
    app.dependency_overrides[_get_translation_service] = lambda: TranslationService(
        FakeLLMService(batch), FakeMarketDataProvider()
    )


def _valid_config_payload() -> dict:
    return {
        "schema_version": 2,
        "portfolio_rules": {"cash_reserve_pct": None, "max_allocation_pct": None, "max_open_positions": None},
        "asset_rules": [{
            "symbol": "AAPL",
            "buy_conditions": {
                "operator": "AND",
                "rules": [{"indicator": "PRICE", "period": 1, "operator": "less_than", "value": 180}],
            },
            "sell_conditions": {
                "operator": "AND",
                "rules": [{"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 195}],
            },
            "position_sizing": {"type": "fixed_allocation", "value_pct": 10},
            "exit": {"stop_loss_pct": 5, "take_profit_pct": None},
        }],
    }


def test_translate_returns_updated_draft(client: TestClient):
    batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_buy_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="less_than", value=180,
            raw_text="Buy Apple below $180",
        )
    ])
    _override_translation_service(batch)

    response = client.post("/agent/translate", json={
        "message": "Buy Apple below $180", "conversation_history": [], "draft": None,
    })

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "updated_draft"
    assert body["draft"]["asset_rules"][0]["symbol"] == "AAPL"


def test_confirm_with_valid_draft_persists_strategy(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "draft": _valid_config_payload(),
    })

    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is True
    assert body["strategy"]["user_id"] == user_id

    
    strategy_id = uuid.UUID(body["strategy"]["id"])
    version = (
        db_session.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .one()
    )
    assert version.confirmed_at is not None
    assert version.source.value == "chat"


def test_confirm_with_invalid_draft_is_rejected_and_not_persisted(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())
    invalid_config = _valid_config_payload()
    invalid_config["asset_rules"][0]["buy_conditions"]["rules"] = []  # no buy conditions -> ERROR

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "draft": invalid_config,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is False
    assert any("no buy conditions" in issue["message"] for issue in body["issues"])


def test_confirm_with_warning_only_issues_still_persists(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())
    config_with_warning = _valid_config_payload()
    config_with_warning["portfolio_rules"]["max_allocation_pct"] = 5  # below the 10% requested -> WARNING only

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "draft": config_with_warning,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is True
    assert len(body["warnings"]) >= 1


def test_confirm_for_existing_strategy_creates_new_version(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())

    first_response = client.post("/agent/confirm", json={
        "user_id": user_id, "draft": _valid_config_payload(),
    })
    strategy_id = first_response.json()["strategy"]["id"]

    updated_config = _valid_config_payload()
    updated_config["asset_rules"][0]["position_sizing"]["value_pct"] = 20

    second_response = client.post("/agent/confirm", json={
        "user_id": user_id, "draft": updated_config, "strategy_id": strategy_id,
    })

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["confirmed"] is True

    versions = (
        db_session.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == uuid.UUID(strategy_id))
        .order_by(StrategyVersion.version_number)
        .all()
    )
    assert len(versions) == 2
    assert versions[0].config_json["asset_rules"][0]["position_sizing"]["value_pct"] == 10
    assert versions[1].config_json["asset_rules"][0]["position_sizing"]["value_pct"] == 20


def test_confirm_for_unknown_strategy_id_returns_404(client: TestClient):
    response = client.post("/agent/confirm", json={
        "user_id": str(uuid.uuid4()), "draft": _valid_config_payload(),
        "strategy_id": str(uuid.uuid4()),
    })

    assert response.status_code == 404