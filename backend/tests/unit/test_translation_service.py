"""One real integration test against Groq, proving the whole pipeline
works end-to-end with a live model. Deterministic logic is already
covered by unit tests with mocked LLM responses — this test exists
only to catch real prompt/schema drift against the actual API.
"""

from app.agent.llm_client import LLMClient
from app.agent.translation.translation_result import TranslationStatus
from app.agent.translation.translation_service import TranslationService
from app.core.config import get_settings
from app.trading_engine.execution.broker import Broker  # noqa: F401  (not used directly, kept for parity)
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData


def test_real_objective_message_updates_draft():
    settings = get_settings()
    llm = LLMClient(settings.groq_api_key, settings.groq_model)
    market_data = AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)
    service = TranslationService(llm, market_data)

    result = service.translate("Buy Apple below $180", [], None)

    assert result.status == TranslationStatus.UPDATED_DRAFT
    assert result.draft is not None
    assert result.draft.asset_rules[0].symbol == "AAPL"