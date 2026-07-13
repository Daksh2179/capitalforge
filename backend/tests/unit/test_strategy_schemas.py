"""Unit tests for the Portfolio Strategy config schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.strategy import (
    AssetRule,
    ConditionGroup,
    ExitRules,
    PortfolioRules,
    PositionSizing,
    RuleCondition,
    StrategyConfig,
)


def _valid_asset_rule(symbol: str = "AAPL") -> dict:
    return {
        "symbol": symbol,
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
    }


def _valid_config_dict() -> dict:
    return {
        "schema_version": 2,
        "portfolio_rules": {"cash_reserve_pct": 10, "max_allocation_pct": 25, "max_open_positions": 5},
        "asset_rules": [_valid_asset_rule("AAPL")],
    }


def test_valid_config_parses_successfully():
    config = StrategyConfig.model_validate(_valid_config_dict())

    assert config.schema_version == 2
    assert config.portfolio_rules.cash_reserve_pct == 10
    assert len(config.asset_rules) == 1
    assert config.asset_rules[0].symbol == "AAPL"


def test_multiple_asset_rules_parse_successfully():
    data = _valid_config_dict()
    data["asset_rules"].append(_valid_asset_rule("NVDA"))

    config = StrategyConfig.model_validate(data)

    assert len(config.asset_rules) == 2
    assert {r.symbol for r in config.asset_rules} == {"AAPL", "NVDA"}


def test_duplicate_symbols_in_asset_rules_rejected():
    data = _valid_config_dict()
    data["asset_rules"].append(_valid_asset_rule("AAPL"))

    with pytest.raises(ValidationError, match="only appear once"):
        StrategyConfig.model_validate(data)


def test_empty_asset_rules_rejected():
    data = _valid_config_dict()
    data["asset_rules"] = []

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_unknown_top_level_field_is_rejected():
    data = _valid_config_dict()
    data["unexpected_field"] = "nope"

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_unsupported_schema_version_is_rejected():
    data = _valid_config_dict()
    data["schema_version"] = 1  # old single-asset shape, no longer accepted

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_portfolio_rules_all_fields_optional():
    portfolio_rules = PortfolioRules()
    assert portfolio_rules.cash_reserve_pct is None
    assert portfolio_rules.max_allocation_pct is None
    assert portfolio_rules.max_open_positions is None


def test_portfolio_rules_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        PortfolioRules(cash_reserve_pct=150)  # over 100
    with pytest.raises(ValidationError):
        PortfolioRules(max_open_positions=0)  # must be > 0


class TestRuleConditionComparisonTarget:
    def test_value_only_is_valid(self):
        rule = RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)
        assert rule.value == 30
        assert rule.compare_indicator is None

    def test_compare_indicator_with_period_is_valid(self):
        rule = RuleCondition(
            indicator="EMA", period=20, operator="crosses_above",
            compare_indicator="EMA", compare_period=50,
        )
        assert rule.compare_indicator == "EMA"
        assert rule.compare_period == 50

    def test_price_above_needs_neither_value_nor_compare_indicator(self):
        rule = RuleCondition(indicator="SMA", period=200, operator="price_above")
        assert rule.value is None
        assert rule.compare_indicator is None

    def test_both_value_and_compare_indicator_rejected(self):
        with pytest.raises(ValidationError, match="Only one of"):
            RuleCondition(
                indicator="RSI", period=14, operator="less_than",
                value=30, compare_indicator="EMA", compare_period=50,
            )

    def test_neither_value_nor_compare_indicator_rejected_when_required(self):
        with pytest.raises(ValidationError, match="requires either"):
            RuleCondition(indicator="RSI", period=14, operator="less_than")

    def test_compare_indicator_without_compare_period_rejected(self):
        with pytest.raises(ValidationError, match="compare_period"):
            RuleCondition(
                indicator="EMA", period=20, operator="crosses_above",
                compare_indicator="EMA",
            )

    def test_crosses_below_requires_target(self):
        with pytest.raises(ValidationError):
            RuleCondition(indicator="RSI", period=14, operator="crosses_below")

    def test_pct_below_requires_target(self):
        with pytest.raises(ValidationError):
            RuleCondition(indicator="ROLLING_HIGH", period=20, operator="pct_below")


def test_invalid_indicator_literal_is_rejected():
    with pytest.raises(ValidationError):
        RuleCondition(indicator="MACD", period=14, operator="less_than", value=30)


def test_invalid_operator_literal_is_rejected():
    with pytest.raises(ValidationError):
        RuleCondition(indicator="RSI", period=14, operator="not_a_real_operator", value=30)


def test_condition_group_empty_rules_rejected():
    with pytest.raises(ValidationError):
        ConditionGroup(operator="AND", rules=[])


def test_asset_rule_requires_both_buy_and_sell_conditions():
    data = _valid_asset_rule()
    del data["sell_conditions"]

    with pytest.raises(ValidationError):
        AssetRule.model_validate(data)


def test_asset_rule_unknown_field_rejected():
    data = _valid_asset_rule()
    data["unexpected"] = True

    with pytest.raises(ValidationError):
        AssetRule.model_validate(data)


@pytest.mark.parametrize("bad_value_pct", [0, -5, 101, 150])
def test_position_sizing_value_pct_out_of_range_is_rejected(bad_value_pct):
    with pytest.raises(ValidationError):
        PositionSizing(type="fixed_allocation", value_pct=bad_value_pct)


def test_exit_rules_negative_percentages_rejected():
    with pytest.raises(ValidationError):
        ExitRules(stop_loss_pct=-1)