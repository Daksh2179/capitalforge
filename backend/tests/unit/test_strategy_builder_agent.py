"""Unit tests for StrategyBuilderAgent -- the TranslationResult ->
CapabilityResult mapping, exercised directly (not through the API).
Fakes mirror tests/integration/test_agent_api.py's exactly, so both
suites exercise the same underlying behavior consistently."""

from datetime import datetime, timedelta, timezone

from app.agent.agent_contracts import AgentName, ResultKind
from app.agent.agents.strategy_builder_agent import StrategyBuilderAgent
from app.agent.llm_service import LLMService
from app.agent.translation.parsed_intent import IntentBatch, ParsedIntent
from app.agent.translation.translation_result import TranslationStatus
from app.agent.translation.translation_service import TranslationService
from app.assets.asset_directory import AssetEntry
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeLLMService(LLMService):
    def __init__(self, batch: IntentBatch, text: str | None = None) -> None:
        self._batch = batch
        self._text = text

    def generate_structured(self, messages, response_model, schema_name):
        return self._batch  # type: ignore[return-value]

    def generate_text(self, messages):
        if self._text is None:
            raise NotImplementedError("not used in this test")
        return self._text


class RaisingLLMService(LLMService):
    def generate_structured(self, messages, response_model, schema_name):
        raise RuntimeError("simulated LLM failure")

    def generate_text(self, messages):
        raise NotImplementedError


class FakeMarketDataProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, timeframe, start, end):
        base = datetime.now(timezone.utc) - timedelta(days=5)
        return [
            MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                      open=100, high=110, low=90, close=100 + i, volume=0.0)
            for i in range(5)
        ]


class FakeAssetDirectory:
    def search(self, query: str, limit: int = 10):
        return [AssetEntry(symbol=query.upper(), name=query)]


def _agent(llm: LLMService) -> StrategyBuilderAgent:
    service = TranslationService(llm, FakeMarketDataProvider(), FakeAssetDirectory())
    return StrategyBuilderAgent(service)


def test_single_operation_maps_to_one_capability_result():
    batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_buy_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="less_than", value=180,
            raw_text="Buy Apple below $180",
        )
    ])
    results, state, raw = _agent(FakeLLMService(batch)).execute("Buy Apple below $180", [], None, None)

    assert raw.status == TranslationStatus.UPDATED_DRAFT
    assert len(results) == 1
    assert results[0].agent == AgentName.STRATEGY_BUILDER
    assert results[0].draft_change is not None
    assert results[0].draft_change.symbol == "AAPL"
    assert results[0].reasoning is None
    assert results[0].affected_entities[0].value == "AAPL"
    assert state.focused_symbol == "AAPL"


def test_multiple_operations_in_one_turn_map_to_multiple_capability_results():
    batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_buy_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="less_than", value=180,
            raw_text="Buy Apple below $180",
        ),
        ParsedIntent(
            operation="set_buy_condition", intent_type="objective", symbol="NVDA",
            indicator="PRICE", period=1, operator="less_than", value=120,
            raw_text="and Nvidia below $120",
        ),
    ])
    results, _, _ = _agent(FakeLLMService(batch)).execute(
        "Buy Apple below $180 and Nvidia below $120", [], None, None
    )

    assert len(results) == 2
    assert {r.affected_entities[0].value for r in results} == {"AAPL", "NVDA"}
    assert all(r.draft_change is not None for r in results)


def test_needs_clarification_maps_to_clarification_with_no_candidates():
    batch = IntentBatch(intents=[
        ParsedIntent(
            operation="request_clarification", intent_type="subjective",
            clarification_context="not a concrete price", raw_text="buy when it's cheap",
        )
    ])
    results, _, raw = _agent(FakeLLMService(batch)).execute("buy when it's cheap", [], None, None)

    assert raw.status == TranslationStatus.NEEDS_CLARIFICATION
    assert len(results) == 1
    assert results[0].clarification is not None
    assert results[0].clarification.candidates == []


def test_needs_disambiguation_maps_to_clarification_with_candidates():
    existing_draft_batch = IntentBatch(intents=[
        ParsedIntent(operation="set_buy_condition", intent_type="objective", symbol="AAPL",
                     indicator="PRICE", period=1, operator="less_than", value=180, raw_text="Buy Apple below $180"),
        ParsedIntent(operation="set_buy_condition", intent_type="objective", symbol="NVDA",
                     indicator="PRICE", period=1, operator="less_than", value=120, raw_text="and Nvidia below $120"),
    ])
    agent = _agent(FakeLLMService(existing_draft_batch))
    _, _, first = agent.execute("Buy Apple below $180 and Nvidia below $120", [], None, None)

    ambiguous_batch = IntentBatch(intents=[
        ParsedIntent(operation="set_stop_loss", intent_type="objective", value=8, raw_text="set stop loss to 8%")
    ])
    agent2 = _agent(FakeLLMService(ambiguous_batch))
    results, _, raw = agent2.execute("set stop loss to 8%", [], first.draft, None)

    assert raw.status == TranslationStatus.NEEDS_DISAMBIGUATION
    assert len(results) == 1
    assert set(results[0].clarification.candidates) == {"AAPL", "NVDA"}


def test_information_maps_to_facts():
    batch = IntentBatch(intents=[
        ParsedIntent(operation="request_information", intent_type="objective", symbol="AAPL",
                     raw_text="what's AAPL trading at")
    ])
    results, _, raw = _agent(FakeLLMService(batch, text="AAPL is trading around $104.")).execute(
        "what's AAPL trading at", [], None, None
    )

    assert raw.status == TranslationStatus.INFORMATION
    assert len(results) == 1
    assert results[0].facts == ["AAPL is trading around $104."]
    assert results[0].draft_change is None


def test_error_maps_to_description_only():
    results, _, raw = _agent(RaisingLLMService()).execute("anything", [], None, None)

    assert raw.status == TranslationStatus.ERROR
    assert len(results) == 1
    assert results[0].kind == ResultKind.ERROR
    assert results[0].description
    assert results[0].draft_change is None
    assert results[0].clarification is None