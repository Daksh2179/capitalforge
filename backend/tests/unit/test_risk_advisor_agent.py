"""Unit tests for RiskAdvisorAgent -- real db_session data (like
PortfolioAnalystAgent) plus fake bars (like TechnicalAnalystAgent),
since this Agent genuinely combines both data needs."""

import uuid
from datetime import datetime, timedelta, timezone

from app.agent.agents.risk_advisor_agent import RiskAdvisorAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext, ResolvedEntity
from app.models.portfolio_snapshot import PortfolioSnapshot
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


def _create_strategy_with_snapshot(db_session, cash, positions_json, portfolio_rules=None):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": portfolio_rules or {}, "asset_rules": []},
        source="manual",
    )
    db_session.refresh(strategy)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=cash, positions_json=positions_json,
        total_value=cash + sum(p["quantity"] * p["current_price"] for p in positions_json.values()),
    ))
    db_session.commit()
    return strategy


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol, entity=EntityReference(kind="symbol", value=symbol, display_name=symbol),
        explanation="test fixture",
    )


def _context(strategy_id, resolved_entities=None) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.RESEARCH, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy_id)


def test_no_strategy_id_reports_honest_gap(db_session):
    agent = RiskAdvisorAgent(db_session, FakeMarketDataProvider({}))
    results = agent.execute(_context(strategy_id=None))
    assert "don't have an active strategy" in results[0].facts[0]


def test_portfolio_summary_reports_real_configured_limits(db_session):
    strategy = _create_strategy_with_snapshot(
        db_session, cash=2000.0,
        positions_json={"AAPL": {"quantity": 10, "average_entry_price": 180.0, "current_price": 190.0}},
        portfolio_rules={"max_allocation_pct": 90, "cash_reserve_pct": 5},
    )
    agent = RiskAdvisorAgent(db_session, FakeMarketDataProvider({}))
    results = agent.execute(_context(strategy.id))

    assert "AAPL" in results[0].facts[1]
    assert "20%" in results[0].facts[1]  # max_position_pct default, unaffected by the overridden fields


def test_no_snapshot_yet_reports_honest_gap(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": []}, source="manual",
    )
    agent = RiskAdvisorAgent(db_session, FakeMarketDataProvider({}))
    results = agent.execute(_context(strategy.id))
    assert "don't have a recorded portfolio snapshot" in results[0].facts[0]


def test_candidate_correlation_and_volatility_reported_without_assuming_size(db_session):
    rising = [100.0 + i for i in range(30)]
    strategy = _create_strategy_with_snapshot(
        db_session, cash=5000.0,
        positions_json={"TECH1": {"quantity": 10, "average_entry_price": 100.0, "current_price": 129.0}},
    )
    market_data = FakeMarketDataProvider({
        "TECH1": _bars("TECH1", rising),
        "TECH2": _bars("TECH2", [c + 5 for c in rising]),  # correlated shape
    })
    agent = RiskAdvisorAgent(db_session, market_data)
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("TECH2")]))

    facts_text = " ".join(results[0].facts)
    assert "correlation" in facts_text
    assert "volatile" in facts_text or "returns have varied" in facts_text
    assert "don't know what size position" in facts_text


def test_candidate_with_no_price_history_reports_honest_gap(db_session):
    strategy = _create_strategy_with_snapshot(db_session, cash=5000.0, positions_json={})
    agent = RiskAdvisorAgent(db_session, FakeMarketDataProvider({}))
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("NVDA")]))

    assert "don't have enough price history" in results[0].facts[0]