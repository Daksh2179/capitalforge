"""Unit tests for apply_portfolio_changes -- the sole deterministic
boundary that ever calls portfolio_service on the conversational side."""

import uuid

from app.agent.agent_contracts import AgentName, CapabilityResult, PortfolioChange, PortfolioChangeType
from app.agent.conversation_memory import EntityReference
from app.agent.pipeline.portfolio_mutations import apply_portfolio_changes
from app.services import portfolio_service


def _entity(symbol: str) -> EntityReference:
    return EntityReference(kind="symbol", value=symbol, display_name=symbol)


def test_add_new_symbol_reports_added(db_session):
    user_id = uuid.uuid4()
    result = CapabilityResult(
        agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("AAPL")],
        portfolio_change=PortfolioChange(change_type=PortfolioChangeType.ADD, symbol="AAPL"),
    )

    updated = apply_portfolio_changes(db_session, user_id, [result])

    assert "Added AAPL" in updated[0].facts[0]
    assert any(h.symbol == "AAPL" for h in portfolio_service.list_holdings(db_session, user_id=user_id))


def test_add_already_present_symbol_reports_already_present_not_duplicate(db_session):
    user_id = uuid.uuid4()
    portfolio_service.add_holding(db_session, user_id=user_id, symbol="AAPL")
    result = CapabilityResult(
        agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("AAPL")],
        portfolio_change=PortfolioChange(change_type=PortfolioChangeType.ADD, symbol="AAPL"),
    )

    updated = apply_portfolio_changes(db_session, user_id, [result])

    assert "already on your portfolio list" in updated[0].facts[0]
    assert len(portfolio_service.list_holdings(db_session, user_id=user_id)) == 1  # no duplicate


def test_remove_existing_symbol_reports_removed(db_session):
    user_id = uuid.uuid4()
    portfolio_service.add_holding(db_session, user_id=user_id, symbol="AAPL")
    result = CapabilityResult(
        agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("AAPL")],
        portfolio_change=PortfolioChange(change_type=PortfolioChangeType.REMOVE, symbol="AAPL"),
    )

    updated = apply_portfolio_changes(db_session, user_id, [result])

    assert "Removed AAPL" in updated[0].facts[0]
    assert portfolio_service.list_holdings(db_session, user_id=user_id) == []


def test_remove_absent_symbol_reports_nothing_to_remove_not_a_false_success(db_session):
    user_id = uuid.uuid4()
    result = CapabilityResult(
        agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("AAPL")],
        portfolio_change=PortfolioChange(change_type=PortfolioChangeType.REMOVE, symbol="AAPL"),
    )

    updated = apply_portfolio_changes(db_session, user_id, [result])

    assert "wasn't on your portfolio list" in updated[0].facts[0]


def test_multiple_changes_in_one_turn_each_report_independently(db_session):
    user_id = uuid.uuid4()
    portfolio_service.add_holding(db_session, user_id=user_id, symbol="AAPL")
    results = [
        CapabilityResult(
            agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("AAPL")],
            portfolio_change=PortfolioChange(change_type=PortfolioChangeType.ADD, symbol="AAPL"),
        ),
        CapabilityResult(
            agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("NVDA")],
            portfolio_change=PortfolioChange(change_type=PortfolioChangeType.ADD, symbol="NVDA"),
        ),
    ]

    updated = apply_portfolio_changes(db_session, user_id, results)

    assert "already on your portfolio list" in updated[0].facts[0]
    assert "Added NVDA" in updated[1].facts[0]


def test_limitations_are_preserved_through_the_rewrite(db_session):
    user_id = uuid.uuid4()
    result = CapabilityResult(
        agent=AgentName.PORTFOLIO_ANALYST, description="x", affected_entities=[_entity("AAPL")],
        limitations=["Removing AAPL does not sell your existing shares."],
        portfolio_change=PortfolioChange(change_type=PortfolioChangeType.REMOVE, symbol="AAPL"),
    )

    updated = apply_portfolio_changes(db_session, user_id, [result])

    assert updated[0].limitations == ["Removing AAPL does not sell your existing shares."]


def test_no_user_id_leaves_results_unchanged(db_session):
    result = CapabilityResult(
        agent=AgentName.PORTFOLIO_ANALYST, description="original", affected_entities=[_entity("AAPL")],
        portfolio_change=PortfolioChange(change_type=PortfolioChangeType.ADD, symbol="AAPL"),
    )

    updated = apply_portfolio_changes(db_session, None, [result])

    assert updated[0].description == "original"  # never applied, never rewritten


def test_result_without_portfolio_change_passes_through_unchanged(db_session):
    result = CapabilityResult(agent=AgentName.PORTFOLIO_ANALYST, description="unrelated", facts=["some fact"])

    updated = apply_portfolio_changes(db_session, uuid.uuid4(), [result])

    assert updated[0] is result