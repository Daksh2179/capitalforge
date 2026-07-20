"""Unit tests for explanation_service, using a fake LLMService —
no real Groq calls. Verifies prompt construction and batch-processing
logic, not model output quality."""

import uuid
from datetime import datetime, timezone

from app.agent.explanations.explanation_service import explain_decision, explain_unexplained_decisions
from app.agent.llm_service import LLMService
from app.models.decision_log import DecisionLog
from app.services import strategy_service


class FakeLLMService(LLMService):
    def __init__(self, text: str = "This is a fake explanation.") -> None:
        self.text = text
        self.received_messages: list[list[dict]] = []

    def generate_structured(self, messages, response_model, schema_name):
        raise NotImplementedError("not used in this test")

    def generate_text(self, messages):
        self.received_messages.append(messages)
        return self.text


def _make_log(**overrides) -> DecisionLog:
    defaults = dict(
        strategy_version_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 178.5, "volume": 1000, "timestamp": "2026-01-01T00:00:00Z"},
        rules_triggered_json=["PRICE(1) less_than 180 (actual=178.5000)"],
        action_taken="buy",
        risk_approved=True,
        risk_reason="approved",
    )
    defaults.update(overrides)
    return DecisionLog(**defaults)


def test_explain_decision_includes_symbol_and_action_in_prompt():
    log = _make_log()
    llm = FakeLLMService()

    result = explain_decision(log, llm)

    assert result == "This is a fake explanation."
    sent_content = llm.received_messages[0][1]["content"]
    assert "AAPL" in sent_content
    assert "buy" in sent_content


def test_explain_decision_includes_risk_reason_for_rejected_signal():
    log = _make_log(action_taken="hold", risk_approved=False, risk_reason="max_position_pct exceeded")
    llm = FakeLLMService()

    explain_decision(log, llm)

    sent_content = llm.received_messages[0][1]["content"]
    assert "max_position_pct exceeded" in sent_content


def test_explain_unexplained_decisions_persists_and_counts(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 2,
            "portfolio_rules": {"cash_reserve_pct": None, "max_allocation_pct": None, "max_open_positions": None},
            "asset_rules": [{
                "symbol": "AAPL",
                "buy_conditions": {"operator": "AND", "rules": [
                    {"indicator": "PRICE", "period": 1, "operator": "less_than", "value": 180}
                ]},
                "sell_conditions": {"operator": "AND", "rules": [
                    {"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 195}
                ]},
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 10},
                "exit": {"stop_loss_pct": 5, "take_profit_pct": None},
            }],
        },
        source="manual",
    )

    log1 = _make_log(strategy_version_id=strategy.current_version_id)
    log2 = _make_log(strategy_version_id=strategy.current_version_id)
    db_session.add_all([log1, log2])
    db_session.commit()

    llm = FakeLLMService()
    processed = explain_unexplained_decisions(db_session, llm, limit=10)

    assert processed == 2
    db_session.refresh(log1)
    db_session.refresh(log2)
    assert log1.explanation_text == "This is a fake explanation."
    assert log2.explanation_text == "This is a fake explanation."


def test_explain_unexplained_decisions_skips_already_explained(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 2,
            "portfolio_rules": {"cash_reserve_pct": None, "max_allocation_pct": None, "max_open_positions": None},
            "asset_rules": [{
                "symbol": "AAPL",
                "buy_conditions": {"operator": "AND", "rules": [
                    {"indicator": "PRICE", "period": 1, "operator": "less_than", "value": 180}
                ]},
                "sell_conditions": {"operator": "AND", "rules": [
                    {"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 195}
                ]},
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 10},
                "exit": {"stop_loss_pct": 5, "take_profit_pct": None},
            }],
        },
        source="manual",
    )

    already_explained = _make_log(strategy_version_id=strategy.current_version_id, explanation_text="already done")
    unexplained = _make_log(strategy_version_id=strategy.current_version_id)
    db_session.add_all([already_explained, unexplained])
    db_session.commit()

    llm = FakeLLMService()
    processed = explain_unexplained_decisions(db_session, llm, limit=10)

    assert processed == 1
    db_session.refresh(already_explained)
    assert already_explained.explanation_text == "already done"


def test_explain_unexplained_decisions_respects_limit(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 2,
            "portfolio_rules": {"cash_reserve_pct": None, "max_allocation_pct": None, "max_open_positions": None},
            "asset_rules": [{
                "symbol": "AAPL",
                "buy_conditions": {"operator": "AND", "rules": [
                    {"indicator": "PRICE", "period": 1, "operator": "less_than", "value": 180}
                ]},
                "sell_conditions": {"operator": "AND", "rules": [
                    {"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 195}
                ]},
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 10},
                "exit": {"stop_loss_pct": 5, "take_profit_pct": None},
            }],
        },
        source="manual",
    )

    logs = [_make_log(strategy_version_id=strategy.current_version_id) for _ in range(3)]
    db_session.add_all(logs)
    db_session.commit()

    llm = FakeLLMService()
    processed = explain_unexplained_decisions(db_session, llm, limit=2)

    assert processed == 2