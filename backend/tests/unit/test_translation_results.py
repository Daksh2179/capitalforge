"""Unit tests for TranslationService using a fake LLMService — no real
Groq calls. Deterministic translation logic is verified here; the one
real-API check lives in tests/integration/test_translation_service.py.
"""

from datetime import datetime, timedelta, timezone

from app.agent.llm_service import LLMService
from app.agent.translation.parsed_intent import IntentBatch, ParsedIntent
from app.agent.translation.translation_result import TranslationStatus
from app.agent.translation.translation_service import TranslationService
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeLLMService(LLMService):
    def __init__(self, batch: IntentBatch) -> None:
        self._batch = batch

    def generate_structured(self, messages, response_model, schema_name):
        return self._batch  # type: ignore[return-value]


class FakeMarketDataProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, timeframe, start, end):
        base = datetime.now(timezone.utc) - timedelta(days=5)
        return [
            MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                      open=100, high=110, low=90, close=100 + i, volume=0.0)
            for i in range(5)
        ]


def test_objective_intent_updates_draft():
    batch = IntentBatch(intents=[
        ParsedIntent(
            operation="set_buy_condition", intent_type="objective", symbol="AAPL",
            indicator="PRICE", period=1, operator="less_than", value=180,
            raw_text="Buy Apple below $180",
        )
    ])
    service = TranslationService(FakeLLMService(batch), FakeMarketDataProvider())

    result = service.translate("Buy Apple below $180", [], None)

    assert result.status == TranslationStatus.UPDATED_DRAFT
    assert result.draft is not None
    assert len(result.applied_operations) == 1


def test_subjective_intent_returns_clarification_with_market_context():
    batch = IntentBatch(intents=[
        ParsedIntent(
            operation="request_clarification", intent_type="subjective", symbol="AAPL",
            clarification_context="cheap is subjective", raw_text="buy when cheap",
        )
    ])
    service = TranslationService(FakeLLMService(batch), FakeMarketDataProvider())

    result = service.translate("buy when cheap", [], None)

    assert result.status == TranslationStatus.NEEDS_CLARIFICATION
    assert result.clarification_message is not None
    assert "trading around" in result.clarification_message


def test_ambiguous_update_returns_disambiguation():
    build_batch = IntentBatch(intents=[
        ParsedIntent(operation="set_buy_condition", intent_type="objective", symbol="AAPL",
                     indicator="PRICE", period=1, operator="less_than", value=180, raw_text="buy AAPL below 180"),
    ])
    service = TranslationService(FakeLLMService(build_batch), FakeMarketDataProvider())
    first_result = service.translate("buy AAPL below 180", [], None)

    build_batch_2 = IntentBatch(intents=[
        ParsedIntent(operation="set_buy_condition", intent_type="objective", symbol="NVDA",
                     indicator="PRICE", period=1, operator="less_than", value=140, raw_text="buy NVDA below 140"),
    ])
    service_2 = TranslationService(FakeLLMService(build_batch_2), FakeMarketDataProvider())
    second_result = service_2.translate("buy NVDA below 140", [], first_result.draft)

    ambiguous_batch = IntentBatch(intents=[
        ParsedIntent(operation="set_stop_loss", intent_type="objective", percentage_value=5, raw_text="make that 5%")
    ])
    service_3 = TranslationService(FakeLLMService(ambiguous_batch), FakeMarketDataProvider())
    result = service_3.translate("make that 5%", [], second_result.draft)

    assert result.status == TranslationStatus.NEEDS_DISAMBIGUATION
    assert set(result.disambiguation_candidates) == {"AAPL", "NVDA"}


def test_llm_error_returns_error_status():
    class BrokenLLMService(LLMService):
        def generate_structured(self, messages, response_model, schema_name):
            raise RuntimeError("API unavailable")

    service = TranslationService(BrokenLLMService(), FakeMarketDataProvider())
    result = service.translate("anything", [], None)

    assert result.status == TranslationStatus.ERROR
    assert result.error_message is not None