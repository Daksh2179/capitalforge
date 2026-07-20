"""Unit tests for ParsedIntent / IntentBatch schema validation."""

import pytest
from pydantic import ValidationError

from app.agent.translation.parsed_intent import IntentBatch, ParsedIntent


def test_minimal_buy_condition_intent_parses():
    intent = ParsedIntent(
        operation="set_buy_condition",
        intent_type="objective",
        symbol="AAPL",
        indicator="PRICE",
        period=1,
        operator="less_than",
        value=180,
        raw_text="Buy Apple below $180",
    )
    assert intent.symbol == "AAPL"
    assert intent.value == 180


def test_subjective_intent_requires_no_condition_fields():
    intent = ParsedIntent(
        operation="request_clarification",
        intent_type="subjective",
        symbol="AAPL",
        clarification_context="'cheap' is subjective, need a concrete price",
        raw_text="Buy Apple when it's cheap",
    )
    assert intent.indicator is None
    assert intent.clarification_context is not None


def test_portfolio_rule_intent():
    intent = ParsedIntent(
        operation="set_portfolio_rule",
        intent_type="objective",
        portfolio_rule_field="cash_reserve_pct",
        percentage=10,
        raw_text="Keep 10% in cash reserve",
    )
    assert intent.portfolio_rule_field == "cash_reserve_pct"


def test_pause_strategy_intent_needs_no_symbol():
    intent = ParsedIntent(
        operation="pause_strategy",
        intent_type="objective",
        raw_text="Pause my strategy",
    )
    assert intent.symbol is None


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ParsedIntent(
            operation="set_buy_condition",
            intent_type="objective",
            raw_text="x",
            unexpected_field="nope",
        )


def test_intent_batch_with_multiple_intents():
    batch = IntentBatch(
        intents=[
            ParsedIntent(
                operation="set_buy_condition", intent_type="objective", symbol="AAPL",
                indicator="PRICE", period=1, operator="less_than", value=180,
                raw_text="buy Apple below $180",
            ),
            ParsedIntent(
                operation="set_sell_condition", intent_type="objective", symbol="AAPL",
                indicator="PRICE", period=1, operator="greater_than", value=195,
                raw_text="sell above $195",
            ),
        ]
    )
    assert len(batch.intents) == 2


def test_intent_batch_empty_list_allowed():
    batch = IntentBatch(intents=[])
    assert batch.intents == []