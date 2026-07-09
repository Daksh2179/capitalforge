"""Unit tests for the strategy config Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.strategy import ConditionGroup, PositionSizing, RuleCondition, StrategyConfig


def _valid_config_dict() -> dict:
    """A minimal, fully valid StrategyConfig payload, reused as a base for
    negative tests by copying and mutating."""
    return {
        "schema_version": 1,
        "symbol": "AAPL",
        "conditions": {
            "operator": "AND",
            "rules": [
                {"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30},
                {"indicator": "SMA", "period": 200, "operator": "price_above"},
            ],
        },
        "position_sizing": {"type": "fixed_allocation", "value_pct": 5},
        "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
    }


def test_valid_config_parses_successfully():
    config = StrategyConfig.model_validate(_valid_config_dict())

    assert config.symbol == "AAPL"
    assert config.conditions.operator == "AND"
    assert len(config.conditions.rules) == 2
    assert config.position_sizing.value_pct == 5
    assert config.exit.stop_loss_pct == 3
    assert config.exit.take_profit_pct is None


def test_unknown_top_level_field_is_rejected():
    data = _valid_config_dict()
    data["unexpected_field"] = "should not be allowed"

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_unknown_nested_field_in_rule_condition_is_rejected():
    data = _valid_config_dict()
    data["conditions"]["rules"][0]["threshold"] = 30  # typo'd/extra field, not "value"

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_invalid_indicator_literal_is_rejected():
    data = _valid_config_dict()
    data["conditions"]["rules"][0]["indicator"] = "MACD"  # not in the allowed Literal set

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_unsupported_schema_version_is_rejected():
    data = _valid_config_dict()
    data["schema_version"] = 2

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


@pytest.mark.parametrize("bad_value_pct", [0, -5, 101, 150])
def test_position_sizing_value_pct_out_of_range_is_rejected(bad_value_pct):
    data = _valid_config_dict()
    data["position_sizing"]["value_pct"] = bad_value_pct

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_empty_rules_list_is_rejected():
    data = _valid_config_dict()
    data["conditions"]["rules"] = []

    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(data)


def test_condition_group_and_rule_condition_can_be_used_standalone():
    """Sanity check that the nested models validate correctly in isolation,
    not just when embedded in a full StrategyConfig."""
    rule = RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)
    assert rule.indicator == "RSI"

    group = ConditionGroup(operator="OR", rules=[rule])
    assert group.operator == "OR"

    sizing = PositionSizing(type="fixed_allocation", value_pct=10)
    assert sizing.value_pct == 10