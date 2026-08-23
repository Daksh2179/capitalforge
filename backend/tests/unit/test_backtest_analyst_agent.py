"""Unit tests for BacktestAnalystAgent -- real db_session data (like
PortfolioAnalystAgent) plus fake bars/translation service."""

import uuid
from datetime import datetime, timedelta, timezone

from app.agent.agents.backtest_analyst_agent import BacktestAnalystAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext, ResolvedEntity
from app.agent.translation.translation_result import TranslationResult, TranslationStatus
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.schemas.strategy import AssetRule, CapitalAllocation, ConditionGroup, ExitRules, RuleCondition, StrategyConfig
from app.services import strategy_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars_by_symbol: dict[str, list[MarketBar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars_by_symbol.get(symbol, [])


def _bars(symbol: str, closes: list[float]) -> list[MarketBar]:
    base = datetime.now(timezone.utc) - timedelta(days=len(closes))
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                  open=c, high=c + 1, low=c - 1, close=c, volume=100_000.0)
        for i, c in enumerate(closes)
    ]


def _rule(symbol: str) -> AssetRule:
    return AssetRule(
        symbol=symbol,
        buy_conditions=ConditionGroup(operator="AND", rules=[
            RuleCondition(indicator="PRICE", period=1, operator="less_than", value=99999)
        ]),
        sell_conditions=ConditionGroup(operator="AND", rules=[
            RuleCondition(indicator="PRICE", period=1, operator="greater_than", value=0)
        ]),
        capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=50),
        exit=ExitRules(),
    )


class FakeTranslationService:
    def __init__(self, result: TranslationResult) -> None:
        self._result = result

    def translate(self, user_message, conversation_history, draft, state):
        return self._result, None


def _create_strategy_with_rule(db_session, symbol="AAPL"):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3, "portfolio_rules": {}, "asset_rules": [_rule(symbol).model_dump(mode="json")],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)
    return strategy


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol, entity=EntityReference(kind="symbol", value=symbol, display_name=symbol),
        explanation="test fixture",
    )


def _context(strategy_id=None, resolved_entities=None, raw_message="backtest my strategy") -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.REVIEW, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], raw_message=raw_message,
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy_id)


def test_backtests_current_strategy_with_real_balance(db_session):
    strategy = _create_strategy_with_rule(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=5000.0, positions_json={}, total_value=5000.0,
    ))
    db_session.commit()

    market_data = FakeMarketDataProvider({"AAPL": _bars("AAPL", [100.0 + i for i in range(30)])})
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context(strategy_id=strategy.id))

    assert len(results) == 1
    assert "AAPL" in results[0].facts[0]
    assert "$5,000.00" in results[0].limitations[0]


def test_no_recorded_balance_falls_back_to_default(db_session):
    strategy = _create_strategy_with_rule(db_session)
    market_data = FakeMarketDataProvider({"AAPL": _bars("AAPL", [100.0] * 30)})
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context(strategy_id=strategy.id))

    assert "$100,000.00" in results[0].limitations[0]
    assert "default" in results[0].limitations[0]


def test_multi_rule_strategy_discloses_independent_backtest_limitation(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3, "portfolio_rules": {},
            "asset_rules": [_rule("AAPL").model_dump(mode="json"), _rule("MSFT").model_dump(mode="json")],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)
    market_data = FakeMarketDataProvider({
        "AAPL": _bars("AAPL", [100.0] * 30), "MSFT": _bars("MSFT", [200.0] * 30),
    })
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context(strategy_id=strategy.id))

    assert len(results) == 2
    assert any("does not model how they would actually compete" in lim for r in results for lim in r.limitations)


def test_hypothetical_marker_triggers_second_backtest(db_session):
    strategy = _create_strategy_with_rule(db_session)
    hyp_config = StrategyConfig(portfolio_rules={}, asset_rules=[_rule("AAPL")])
    hypothetical = TranslationResult(status=TranslationStatus.UPDATED_DRAFT, draft=hyp_config)

    market_data = FakeMarketDataProvider({"AAPL": _bars("AAPL", [100.0 + i for i in range(30)])})
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(hypothetical))

    results = agent.execute(_context(strategy_id=strategy.id, raw_message="what if I used RSI 25 instead?"))

    assert len(results) == 2
    assert "hypothetical" in results[1].facts[0].lower()


def test_plain_backtest_request_never_calls_translation_service(db_session):
    strategy = _create_strategy_with_rule(db_session)

    class ExplodingTranslationService:
        def translate(self, *args, **kwargs):
            raise AssertionError("should not be called for a non-hypothetical message")

    market_data = FakeMarketDataProvider({"AAPL": _bars("AAPL", [100.0] * 30)})
    agent = BacktestAnalystAgent(db_session, market_data, ExplodingTranslationService())

    results = agent.execute(_context(strategy_id=strategy.id, raw_message="backtest my strategy for 3 months"))

    assert len(results) == 1  # only the current-strategy backtest, no exception


def test_benchmark_symbol_not_in_strategy_runs_buy_and_hold(db_session):
    strategy = _create_strategy_with_rule(db_session)
    market_data = FakeMarketDataProvider({
        "AAPL": _bars("AAPL", [100.0] * 30), "SPY": _bars("SPY", [400.0 + i for i in range(30)]),
    })
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context(
        strategy_id=strategy.id, resolved_entities=[_resolved("SPY")],
        raw_message="would I have done better just holding SPY?",
    ))

    assert len(results) == 2
    assert any("holding SPY" in r.facts[0] for r in results)


def test_no_strategy_no_benchmark_reports_honest_gap(db_session):
    market_data = FakeMarketDataProvider({})
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context())

    assert "don't have a confirmed strategy" in results[0].facts[0]
    
def _create_strategy_with_rule_and_pool(db_session, symbol="AAPL", total_capital_usd=3000.0):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3,
            "portfolio_rules": {"total_capital_usd": total_capital_usd},
            "asset_rules": [_rule(symbol).model_dump(mode="json")],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)
    return strategy


def test_declared_pool_preferred_over_real_account_balance(db_session):
    strategy = _create_strategy_with_rule_and_pool(db_session, total_capital_usd=3000.0)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=5000.0, positions_json={}, total_value=5000.0,
    ))
    db_session.commit()

    market_data = FakeMarketDataProvider({"AAPL": _bars("AAPL", [100.0 + i for i in range(30)])})
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context(strategy_id=strategy.id))

    # The declared $3,000 pool wins over the real $5,000 recorded
    # balance -- a backtest of THIS strategy should reflect what it's
    # actually allowed to manage, not the account's full real value.
    assert "$3,000.00" in results[0].limitations[0]
    assert "declared trading pool" in results[0].limitations[0]


def test_declared_pool_used_even_with_no_recorded_snapshot(db_session):
    strategy = _create_strategy_with_rule_and_pool(db_session, total_capital_usd=1500.0)
    market_data = FakeMarketDataProvider({"AAPL": _bars("AAPL", [100.0] * 30)})
    agent = BacktestAnalystAgent(db_session, market_data, FakeTranslationService(TranslationResult(status=TranslationStatus.ERROR)))

    results = agent.execute(_context(strategy_id=strategy.id))

    assert "$1,500.00" in results[0].limitations[0]
    assert "declared trading pool" in results[0].limitations[0]