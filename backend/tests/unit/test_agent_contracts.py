"""Unit tests for the shared Agent contract types -- primarily the
mutual-exclusivity guarantee, since that's the one rule this layer
exists to enforce structurally rather than by convention."""

import pytest

from app.agent.agent_contracts import AgentName, CapabilityResult, Conclusion, Recommendation
from app.agent.translation.translation_result import AppliedOperation


def _recommendation() -> Recommendation:
    return Recommendation(
        kind="asset", subject=[], conclusion=Conclusion.WAIT,
        supporting_evidence=["price near 52-week low"], assumptions=["no new data since last close"],
        confidence="moderate", invalidating_conditions=["a large volume spike"],
        contributing_agents=[AgentName.MARKET_RESEARCH],
    )


def test_result_with_only_draft_change_is_valid():
    result = CapabilityResult(
        agent=AgentName.STRATEGY_BUILDER, description="Added buy condition for AAPL",
        draft_change=AppliedOperation(operation="set_buy_condition", symbol="AAPL", description="RSI(14) < 30"),
    )
    assert result.recommendation is None


def test_result_with_only_recommendation_is_valid():
    result = CapabilityResult(
        agent=AgentName.INVESTMENT_ANALYST, description="Evaluated AAPL on request",
        recommendation=_recommendation(),
    )
    assert result.draft_change is None


def test_result_with_both_draft_change_and_recommendation_is_rejected():
    with pytest.raises(ValueError, match="mutually exclusive|cannot carry both"):
        CapabilityResult(
            agent=AgentName.STRATEGY_BUILDER, description="invalid",
            draft_change=AppliedOperation(operation="set_buy_condition", symbol="AAPL", description="x"),
            recommendation=_recommendation(),
        )


def test_result_with_neither_is_valid():
    result = CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="Reported AAPL's price")
    assert result.draft_change is None
    assert result.recommendation is None
    
def test_limitations_defaults_to_empty_list():
    result = CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="x")
    assert result.limitations == []