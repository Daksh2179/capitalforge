"""Unit tests for validate_strategy — pure function, no mocking needed."""

from app.agent.translation.validation import Severity, validate_strategy
from app.schemas.strategy import (
    AssetRule,
    CapitalAllocation,
    ConditionGroup,
    ExitRules,
    PortfolioRules,
    RuleCondition,
    StrategyConfig,
)


def _price_condition(operator: str, value: float) -> RuleCondition:
    return RuleCondition(indicator="PRICE", period=1, operator=operator, value=value)


def _valid_asset_rule(symbol: str = "AAPL", buy_price: float = 180, sell_price: float = 195) -> AssetRule:
    return AssetRule(
        symbol=symbol,
        buy_conditions=ConditionGroup(operator="AND", rules=[_price_condition("less_than", buy_price)]),
        sell_conditions=ConditionGroup(operator="AND", rules=[_price_condition("greater_than", sell_price)]),
        capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10),
        exit=ExitRules(stop_loss_pct=5, take_profit_pct=10),
    )


def test_fully_valid_config_produces_no_issues():
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[_valid_asset_rule()])

    issues = validate_strategy(config)

    assert issues == []


def test_empty_asset_rules_produces_error():
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[])

    issues = validate_strategy(config)

    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "no assets" in issues[0].message


def test_asset_rule_with_no_buy_conditions_produces_error():
    rule = AssetRule(
        symbol="AAPL",
        buy_conditions=ConditionGroup(operator="AND", rules=[]),
        sell_conditions=ConditionGroup(operator="AND", rules=[_price_condition("greater_than", 195)]),
        capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10),
        exit=ExitRules(),
    )
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule])

    issues = validate_strategy(config)

    assert any(i.severity == Severity.ERROR and "no buy conditions" in i.message for i in issues)


def test_asset_rule_with_no_sell_conditions_produces_error():
    rule = AssetRule(
        symbol="AAPL",
        buy_conditions=ConditionGroup(operator="AND", rules=[_price_condition("less_than", 180)]),
        sell_conditions=ConditionGroup(operator="AND", rules=[]),
        capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10),
        exit=ExitRules(),
    )
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule])

    issues = validate_strategy(config)

    assert any(i.severity == Severity.ERROR and "no sell conditions" in i.message for i in issues)


def test_buy_price_at_or_above_sell_price_is_error():
    rule = _valid_asset_rule(buy_price=200, sell_price=190)
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule])

    issues = validate_strategy(config)

    assert any(i.severity == Severity.ERROR and "not below sell price" in i.message for i in issues)


def test_indicator_based_conditions_skip_price_contradiction_check():
    rule = AssetRule(
        symbol="AAPL",
        buy_conditions=ConditionGroup(operator="AND", rules=[
            RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)
        ]),
        sell_conditions=ConditionGroup(operator="AND", rules=[
            RuleCondition(indicator="RSI", period=14, operator="greater_than", value=70)
        ]),
        capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10),
        exit=ExitRules(),
    )
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule])

    issues = validate_strategy(config)

    assert not any("not below sell price" in i.message for i in issues)


def test_stop_loss_at_100_percent_or_more_is_error():
    rule = _valid_asset_rule()
    rule = rule.model_copy(update={"exit": ExitRules(stop_loss_pct=100, take_profit_pct=None)})
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule])

    issues = validate_strategy(config)

    assert any(i.severity == Severity.ERROR and "cannot lose more than 100%" in i.message for i in issues)


def test_stop_loss_larger_than_take_profit_is_warning_not_error():
    rule = _valid_asset_rule()
    rule = rule.model_copy(update={"exit": ExitRules(stop_loss_pct=20, take_profit_pct=10)})
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule])

    issues = validate_strategy(config)

    matching = [i for i in issues if "risk/reward" in i.message]
    assert len(matching) == 1
    assert matching[0].severity == Severity.WARNING


def test_allocation_over_100_percent_is_error():
    rule1 = _valid_asset_rule("AAPL")
    rule1 = rule1.model_copy(update={"capital_allocation": CapitalAllocation(type="percentage_of_portfolio", percentage=70)})
    rule2 = _valid_asset_rule("NVDA")
    rule2 = rule2.model_copy(update={"capital_allocation": CapitalAllocation(type="percentage_of_portfolio", percentage=50)})
    config = StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[rule1, rule2])

    issues = validate_strategy(config)

    assert any(i.severity == Severity.ERROR and "exceeds 100%" in i.message for i in issues)


def test_allocation_exceeding_max_allocation_pct_is_warning():
    rule = _valid_asset_rule()
    rule = rule.model_copy(update={"capital_allocation": CapitalAllocation(type="percentage_of_portfolio", percentage=30)})
    config = StrategyConfig(
        portfolio_rules=PortfolioRules(max_allocation_pct=25), asset_rules=[rule]
    )

    issues = validate_strategy(config)

    matching = [i for i in issues if "max_allocation_pct limit" in i.message]
    assert len(matching) == 1
    assert matching[0].severity == Severity.WARNING
    