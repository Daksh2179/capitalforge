"""Unit tests for translate_intent — pure function, no mocking needed."""

import pytest

from app.agent.translation.intent_translator import FragmentKind, translate_intent
from app.agent.translation.parsed_intent import ParsedIntent


def test_buy_condition_translates_to_rule_condition():
    intent = ParsedIntent(
        operation="set_buy_condition", intent_type="objective", symbol="AAPL",
        indicator="PRICE", period=1, operator="less_than", value=180,
        raw_text="Buy Apple below $180",
    )
    fragment = translate_intent(intent)

    assert fragment.kind == FragmentKind.BUY_CONDITION
    assert fragment.symbol == "AAPL"
    assert fragment.condition is not None
    assert fragment.condition.value == 180


def test_subjective_intent_always_produces_clarification_fragment():
    intent = ParsedIntent(
        operation="set_buy_condition", intent_type="subjective", symbol="AAPL",
        clarification_context="cheap is subjective", raw_text="buy when cheap",
    )
    fragment = translate_intent(intent)

    assert fragment.kind == FragmentKind.CLARIFICATION_NEEDED
    assert fragment.clarification_context == "cheap is subjective"


def test_request_clarification_operation_produces_clarification_fragment():
    intent = ParsedIntent(
        operation="request_clarification", intent_type="subjective",
        clarification_context="ambiguous", raw_text="something vague",
    )
    fragment = translate_intent(intent)
    assert fragment.kind == FragmentKind.CLARIFICATION_NEEDED


def test_buy_condition_missing_fields_raises():
    intent = ParsedIntent(operation="set_buy_condition", intent_type="objective", symbol="AAPL", raw_text="buy Apple")
    with pytest.raises(ValueError, match="requires indicator"):
        translate_intent(intent)


def test_stop_loss_translates_correctly():
    intent = ParsedIntent(
        operation="set_stop_loss", intent_type="objective", symbol="AAPL",
        percentage_value=5, raw_text="5% stop loss on Apple",
    )
    fragment = translate_intent(intent)
    assert fragment.kind == FragmentKind.STOP_LOSS
    assert fragment.percentage_value == 5


def test_portfolio_rule_translates_correctly():
    intent = ParsedIntent(
        operation="set_portfolio_rule", intent_type="objective",
        portfolio_rule_field="cash_reserve_pct", percentage_value=10,
        raw_text="keep 10% cash",
    )
    fragment = translate_intent(intent)
    assert fragment.kind == FragmentKind.PORTFOLIO_RULE
    assert fragment.portfolio_rule_field == "cash_reserve_pct"


def test_pause_strategy_translates_correctly():
    intent = ParsedIntent(operation="pause_strategy", intent_type="objective", raw_text="pause it")
    fragment = translate_intent(intent)
    assert fragment.kind == FragmentKind.PAUSE_STRATEGY