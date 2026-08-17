"""Integration tests for the agent API: /agent/translate, /agent/confirm,
and /agent/conversations/{id}. Every dependency the pipeline needs
(TranslationService's LLM, GoalExtractor's LLM, AssetDirectory,
MarketDataProvider) is independently faked -- no real Groq/Alpaca/
Finnhub call anywhere in this file.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.llm_service import LLMService
from app.agent.pipeline.goal_extractor import GoalExtractor
from app.agent.pipeline.types import ExtractedGoal, GoalExtractionIntent
from app.agent.translation.parsed_intent import IntentBatch, ParsedIntent
from app.agent.translation.translation_service import TranslationService
from app.api.agent import _get_asset_directory, _get_goal_extractor, _get_market_data_provider, _get_translation_service
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


class FakeGoalExtractionLLM(LLMService):
    def __init__(self, goal: ExtractedGoal) -> None:
        self._goal = goal

    def generate_structured(self, messages, response_model, schema_name):
        return self._goal  # type: ignore[return-value]

    def generate_text(self, messages):
        raise NotImplementedError


class RaisingGoalExtractionLLM(LLMService):
    def generate_structured(self, messages, response_model, schema_name):
        raise RuntimeError("simulated Goal Extraction failure")

    def generate_text(self, messages):
        raise NotImplementedError


class FakeMarketDataProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, timeframe, start, end):
        from datetime import datetime, timedelta, timezone
        base = datetime.now(timezone.utc) - timedelta(days=250)
        return [
            MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                      open=100, high=110, low=90, close=100 + i, volume=100_000.0)
            for i in range(250)
        ]


class FakeAssetDirectory:
    """Returns the input symbol unchanged, uppercased — enough for
    tests that don't exercise real company-name resolution."""

    def search(self, query: str, limit: int = 10):
        from app.assets.asset_directory import AssetEntry
        return [AssetEntry(symbol=query.upper(), name=query)]

    def search_scored(self, query: str, limit: int = 10):
        from app.assets.asset_directory import AssetEntry, AssetSearchResult
        return [AssetSearchResult(entry=AssetEntry(symbol=query.upper(), name=query), score=95.0)]


def _override_translation_service(
    batch: IntentBatch, *, agent: str = "strategy_builder", mentioned_entities: list[str] | None = None,
) -> None:
    """Overrides every dependency the pipeline needs for a
    fully-deterministic, no-real-network-call test. `agent` defaults
    to "strategy_builder" -- existing tests all exercise BUILD/EDIT
    behavior, where Goal Extraction's exact intent value doesn't
    affect routing at all (both STRATEGY_BUILDER and STRATEGY_EDITOR
    route to the same shared implementation)."""
    app.dependency_overrides[_get_translation_service] = lambda: TranslationService(
        FakeLLMService(batch), FakeMarketDataProvider(), FakeAssetDirectory()
    )
    goal = ExtractedGoal(
        intent=GoalExtractionIntent.BUILD, candidate_agents=[agent],
        mentioned_entities=mentioned_entities or [],
    )
    app.dependency_overrides[_get_goal_extractor] = lambda: GoalExtractor(FakeGoalExtractionLLM(goal))
    app.dependency_overrides[_get_asset_directory] = lambda: FakeAssetDirectory()
    app.dependency_overrides[_get_market_data_provider] = lambda: FakeMarketDataProvider()


def _clear_overrides() -> None:
    for dep in (_get_translation_service, _get_goal_extractor, _get_asset_directory, _get_market_data_provider):
        app.dependency_overrides.pop(dep, None)


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
        "schema_version": 3,
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
    user_id = str(uuid.uuid4())

    response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Buy Apple below $180",
    })

    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "updated_draft"
    assert body["draft"]["asset_rules"][0]["symbol"] == "AAPL"


def test_translate_populates_agent_response_for_build_turn(client: TestClient):
    _override_translation_service(_buy_aapl_batch())
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())

    response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Buy Apple below $180",
    })
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["agent_response"] != ""
    assert "AAPL" in body["agent_response"]


def test_translate_twice_accumulates_history_and_draft(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())

    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Buy Apple below $180",
    })
    _clear_overrides()

    sell_batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_sell_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="greater_than", value=195,
            raw_text="Sell above $195",
        )
    ])
    _override_translation_service(sell_batch)
    second_response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Sell above $195",
    })
    _clear_overrides()

    assert second_response.status_code == 200
    draft = second_response.json()["draft"]
    rule = draft["asset_rules"][0]
    assert len(rule["buy_conditions"]["rules"]) == 1
    assert len(rule["sell_conditions"]["rules"]) == 1


def test_translate_information_response_uses_information_message(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())

    _override_translation_service(
        IntentBatch(intents=[]), agent="market_research", mentioned_entities=["AAPL"],
    )
    response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "what's AAPL trading at?",
    })
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "information"
    assert body["information_message"] is not None
    assert "AAPL" in body["information_message"]
    assert body["agent_response"] == body["information_message"]
    assert body["draft"] is None  # no draft-modifying step ran this turn


def test_memory_persists_between_turns(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())

    _override_translation_service(
        IntentBatch(intents=[]), agent="market_research", mentioned_entities=["AAPL"],
    )
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "what's AAPL trading at?",
    })
    _clear_overrides()

    # No entity mentioned this turn -- must resolve via persisted
    # ConversationMemory.primary_focus (AAPL, from the previous turn),
    # proving memory actually round-trips across two separate HTTP calls.
    _override_translation_service(IntentBatch(intents=[]), agent="market_research", mentioned_entities=[])
    second_response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "what about its 52-week range?",
    })
    _clear_overrides()

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["status"] == "information"
    assert "AAPL" in body["information_message"]


def test_pipeline_failure_returns_graceful_error_not_500(client: TestClient):
    app.dependency_overrides[_get_goal_extractor] = lambda: GoalExtractor(RaisingGoalExtractionLLM())
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())

    response = client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "anything",
    })
    app.dependency_overrides.pop(_get_goal_extractor, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error_message"] != ""
    assert body["agent_response"] != ""


def test_get_conversation_session_returns_persisted_state(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())
    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Buy Apple below $180",
    })
    _clear_overrides()

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
    (conversation_id, user_id) for reuse."""
    conversation_id = f"conv-{uuid.uuid4()}"
    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Buy Apple below $180",
    })
    _clear_overrides()

    sell_batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_sell_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="greater_than", value=195,
            raw_text="Sell above $195",
        )
    ])
    _override_translation_service(sell_batch)
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Sell above $195",
    })
    _clear_overrides()

    return conversation_id, user_id


def test_confirm_with_valid_draft_persists_strategy(client: TestClient, db_session: Session):
    """Also confirms /confirm continues to work with a draft produced
    by the new pipeline -- session.draft flows through identically
    regardless of which internal path produced it."""
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


def test_strategy_id_resolved_after_confirmation(client: TestClient, db_session: Session):
    """Confirms a strategy via the normal chat flow, then sends a
    follow-up REVIEW-type message in a BRAND NEW conversation (so
    ConversationMemory starts genuinely empty -- no leftover
    primary_focus to trigger the implicit-reference fallback) and
    checks PortfolioAnalystAgent (real db, real strategy_id resolution)
    sees the just-confirmed strategy rather than "no active strategy" --
    proving strategy_id is resolved from user_id, correctly, after
    confirmation, independent of conversation history."""
    user_id = str(uuid.uuid4())
    conversation_id, _ = _confirm_via_chat(client, user_id)
    client.post("/agent/confirm", json={"user_id": user_id, "conversation_id": conversation_id})

    fresh_conversation_id = f"conv-{uuid.uuid4()}"
    _override_translation_service(IntentBatch(intents=[]), agent="portfolio_analyst")
    response = client.post("/agent/translate", json={
        "conversation_id": fresh_conversation_id, "user_id": user_id, "message": "how's my strategy doing?",
    })
    _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    # Not "no active strategy" (strategy_id was None) -- specifically
    # "no portfolio snapshot yet" (strategy_id resolved to a real,
    # just-confirmed strategy that simply hasn't completed a cycle).
    assert "portfolio snapshot" in body["information_message"]


def test_confirm_with_no_session_returns_400(client: TestClient):
    response = client.post("/agent/confirm", json={
        "user_id": str(uuid.uuid4()), "conversation_id": f"conv-{uuid.uuid4()}",
    })

    assert response.status_code == 400


def test_confirm_with_invalid_draft_is_rejected_and_not_persisted(client: TestClient):
    conversation_id = f"conv-{uuid.uuid4()}"
    user_id = str(uuid.uuid4())
    _override_translation_service(_buy_aapl_batch())
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Buy Apple below $180",
    })
    _clear_overrides()

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "conversation_id": conversation_id,
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
            operation="set_capital_allocation", intent_type="objective", symbol="AAPL",
            percentage=20, allocation_type="percentage_of_portfolio", raw_text="Make that 20%",
        )
    ])
    _override_translation_service(size_batch)
    client.post("/agent/translate", json={
        "conversation_id": conversation_id, "user_id": user_id, "message": "Make that 20%",
    })
    _clear_overrides()

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
    assert versions[0].config_json["asset_rules"][0]["capital_allocation"]["percentage"] == 5.0
    assert versions[1].config_json["asset_rules"][0]["capital_allocation"]["percentage"] == 20


def test_confirm_for_unknown_strategy_id_returns_404(client: TestClient):
    conversation_id, user_id = _confirm_via_chat(client, str(uuid.uuid4()))

    response = client.post("/agent/confirm", json={
        "user_id": user_id, "conversation_id": conversation_id,
        "strategy_id": str(uuid.uuid4()),
    })
    

    assert response.status_code == 404