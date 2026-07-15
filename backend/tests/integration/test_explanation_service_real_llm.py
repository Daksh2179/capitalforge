"""One real Groq call proving the explanation prompt/pipeline works
end-to-end against a live model. Deterministic logic (prompt
construction, batch processing) is already covered by unit tests with
a mocked LLMService."""

import uuid
from datetime import datetime, timezone

from app.agent.explanations.explanation_service import explain_decision
from app.agent.llm_client import LLMClient
from app.core.config import get_settings
from app.models.decision_log import DecisionLog


def test_real_explanation_mentions_symbol_and_action():
    settings = get_settings()
    llm = LLMClient(settings.groq_api_key, settings.groq_model)

    log = DecisionLog(
        strategy_version_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 178.5, "volume": 1000, "timestamp": "2026-01-01T00:00:00Z"},
        rules_triggered_json=["PRICE(1) less_than 180 (actual=178.5000)"],
        action_taken="buy",
        risk_approved=True,
        risk_reason="approved",
    )

    result = explain_decision(log, llm)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "AAPL" in result or "Apple" in result