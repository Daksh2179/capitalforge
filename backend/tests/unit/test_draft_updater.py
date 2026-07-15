"""Unit tests for apply_fragment — pure, deterministic, no mocking."""

import pytest

from app.agent.translation.draft_updater import AmbiguousAssetError, apply_fragment
from app.agent.translation.intent_translator import FragmentKind, IntentFragment
from app.schemas.strategy import RuleCondition


def _condition_fragment(kind: FragmentKind, symbol: str | None, value: float = 180) -> IntentFragment:
    return IntentFragment(
        kind=kind, symbol=symbol, raw_text="test",
        condition=RuleCondition(indicator="PRICE", period=1, operator="less_than", value=value),
    )


def test_buy_condition_on_empty_draft_creates_asset_rule():
    fragment = _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL")
    outcome = apply_fragment(None, fragment)

    assert len(outcome.config.asset_rules) == 1
    rule = outcome.config.asset_rules[0]
    assert rule.symbol == "AAPL"
    assert len(rule.buy_conditions.rules) == 1


def test_second_condition_on_same_asset_appends_not_replaces():
    first = apply_fragment(None, _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL", value=180))
    second = apply_fragment(
        first.config, _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL", value=170)
    )

    rule = second.config.asset_rules[0]
    assert len(rule.buy_conditions.rules) == 2


def test_condition_on_second_asset_preserves_first():
    first = apply_fragment(None, _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL"))
    second = apply_fragment(first.config, _condition_fragment(FragmentKind.BUY_CONDITION, "NVDA"))

    symbols = {r.symbol for r in second.config.asset_rules}
    assert symbols == {"AAPL", "NVDA"}


def test_missing_symbol_with_single_asset_resolves_automatically():
    first = apply_fragment(None, _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL"))
    fragment_no_symbol = IntentFragment(
        kind=FragmentKind.STOP_LOSS, symbol=None, raw_text="set 5% stop loss", percentage_value=5,
    )

    outcome = apply_fragment(first.config, fragment_no_symbol)

    assert outcome.config.asset_rules[0].exit.stop_loss_pct == 5


def test_missing_symbol_with_multiple_assets_raises_ambiguous():
    first = apply_fragment(None, _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL"))
    second = apply_fragment(first.config, _condition_fragment(FragmentKind.BUY_CONDITION, "NVDA"))

    fragment_no_symbol = IntentFragment(
        kind=FragmentKind.STOP_LOSS, symbol=None, raw_text="make that 5%", percentage_value=5,
    )

    with pytest.raises(AmbiguousAssetError) as exc_info:
        apply_fragment(second.config, fragment_no_symbol)

    assert set(exc_info.value.candidates) == {"AAPL", "NVDA"}


def test_remove_asset_removes_only_that_symbol():
    first = apply_fragment(None, _condition_fragment(FragmentKind.BUY_CONDITION, "AAPL"))
    second = apply_fragment(first.config, _condition_fragment(FragmentKind.BUY_CONDITION, "NVDA"))

    outcome = apply_fragment(second.config, IntentFragment(kind=FragmentKind.REMOVE_ASSET, symbol="AAPL", raw_text="remove Apple"))

    assert len(outcome.config.asset_rules) == 1
    assert outcome.config.asset_rules[0].symbol == "NVDA"


def test_portfolio_rule_percentage_field_applies():
    fragment = IntentFragment(
        kind=FragmentKind.PORTFOLIO_RULE, symbol=None, raw_text="keep 10% cash",
        portfolio_rule_field="cash_reserve_pct", percentage_value=10,
    )
    outcome = apply_fragment(None, fragment)

    assert outcome.config.portfolio_rules.cash_reserve_pct == 10


def test_portfolio_rule_max_open_positions_field_applies():
    fragment = IntentFragment(
        kind=FragmentKind.PORTFOLIO_RULE, symbol=None, raw_text="max 3 positions",
        portfolio_rule_field="max_open_positions", max_open_positions=3,
    )
    outcome = apply_fragment(None, fragment)

    assert outcome.config.portfolio_rules.max_open_positions == 3