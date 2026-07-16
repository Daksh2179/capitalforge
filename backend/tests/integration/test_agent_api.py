"""Integration tests for the agent API: /agent/translate, /agent/confirm,
and /agent/conversations/{id}. Uses a fake TranslationService for
/translate (no real Groq call needed) and real strategy_service
persistence for /confirm.
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

    def generate_text(self, messages):
        raise NotImplementedError("not used in these tests")


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


def _buy_aapl_batch() -> IntentBatch:
    return IntentBatch(intents=[
        ParsedIntent(
            operation="set_buy_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="less_than", value=180,
            raw_text="Buy Apple below $180",
        )
    ])


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


def test_translate_returns_updated_draft_and_persists_session(client: TestClient):
    _override_translation_service(_buy_aapl_batch())
    conversation_id = f"conv-{uuid.uuid4()}"

    response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Buy Apple below $180",
    })

    del app.dependency_overrides[_get_translation_service]

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "updated_draft"
    assert body["draft"]["asset_rules"][0]["symbol"] == "AAPL"


def test_translate_twice_accumulates_history_and_draft(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"

    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Buy Apple below $180",
    })
    del app.dependency_overrides[_get_translation_service]

    sell_batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_sell_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="greater_than", value=195,
            raw_text="Sell above $195",
        )
    ])
    _override_translation_service(sell_batch)
    second_response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Sell above $195",
    })
    del app.dependency_overrides[_get_translation_service]

    assert second_response.status_code == 200
    draft = second_response.json()["draft"]
    rule = draft["asset_rules"][0]
    assert len(rule["buy_conditions"]["rules"]) == 1
    assert len(rule["sell_conditions"]["rules"]) == 1


def test_get_conversation_session_returns_persisted_state(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Buy Apple below $180",
    })
    del app.dependency_overrides[_get_translation_service]

    response = client.get(f"/agent/conversations/{conversation_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 2  # one user, one assistant
    assert body["draft"]["asset_rules"][0]["symbol"] == "AAPL"


def test_get_conversation_session_returns_empty_for_unknown_id(client: TestClient):
    response = client.get(f"/agent/conversations/conv-{uuid.uuid4()}")

    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == []
    assert body["draft"] is None


def _confirm_via_chat(client: TestClient, user_id: str) -> tuple[str, str]:
    """Helper: drives a conversation to a confirmable draft, returns
    (conversation_id, draft_json_asset_rules_symbol) for reuse."""
    conversation_id = f"conv-{uuid.uuid4()}"
    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Buy Apple below $180",
    })
    del app.dependency_overrides[_get_translation_service]

    sell_batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_sell_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="greater_than", value=195,
            raw_text="Sell above $195",
        )
    ])
    _override_translation_service(sell_batch)
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Sell above $195",
    })
    del app.dependency_overrides[_get_translation_service]

    return conversation_id, user_id


def test_confirm_with_valid_draft_persists_strategy(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())
    conversation_id, _ = _confirm_via_chat(client, user_id)

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "conversation_id": conversation_id,
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


def test_confirm_with_no_session_returns_400(client: TestClient):
    response = client.post("/agent/confirm", json={
        "user_id": str(uuid.uuid4()), "conversation_id": f"conv-{uuid.uuid4()}",
    })

    assert response.status_code == 400


def test_confirm_with_invalid_draft_is_rejected_and_not_persisted(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    # A buy-only, no-sell-condition draft is invalid (missing sell conditions -> ERROR).
    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Buy Apple below $180",
    })
    del app.dependency_overrides[_get_translation_service]

    response = client.post("/agent/confirm", json={
        "user_id": str(uuid.uuid4()), "conversation_id": conversation_id,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is False
    assert any("no sell conditions" in issue["message"] for issue in body["issues"])


def test_confirm_for_existing_strategy_creates_new_version(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())
    conversation_id, _ = _confirm_via_chat(client, user_id)

    first_response = client.post("/agent/confirm", json={
        "user_id": user_id, "conversation_id": conversation_id,
    })
    strategy_id = first_response.json()["strategy"]["id"]

    size_batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_position_sizing", intent_type="objective", symbol="AAPL",
            percentage_value=20, raw_text="Make that 20%",
        )
    ])
    _override_translation_service(size_batch)
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "message": "Make that 20%",
    })
    del app.dependency_overrides[_get_translation_service]

    second_response = client.post("/agent/confirm", json={
        "user_id": user_id, "conversation_id": conversation_id, "strategy_id": strategy_id,
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
    assert versions[0].config_json["asset_rules"][0]["position_sizing"]["value_pct"] == 5.0
    assert versions[1].config_json["asset_rules"][0]["position_sizing"]["value_pct"] == 20


def test_confirm_for_unknown_strategy_id_returns_404(client: TestClient):
    conversation_id, user_id = _confirm_via_chat(client, str(uuid.uuid4()))

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "conversation_id": conversation_id,
        "strategy_id": str(uuid.uuid4()),
    })

    assert response.status_code == 404