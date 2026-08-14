"""Unit tests for InvestmentAnalystAgent -- the synthesis LLM call is
faked (FakeLLMService), never real. Covers: convergent evidence,
conflicting evidence, missing evidence, the SELL ownership gate being
enforced in CODE regardless of what the LLM outputs, and that
kind/subject/contributing_agents are always deterministic, never
trusted from the LLM."""

from app.agent.agent_contracts import (
    AgentName,
    CapabilityResult,
    Conclusion,
    ResultKind,
    SynthesizedConclusion,
)
from app.agent.agents.investment_analyst_agent import InvestmentAnalystAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.llm_service import LLMService
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext, ResolvedEntity


class FakeLLMService(LLMService):
    def __init__(self, conclusion: SynthesizedConclusion) -> None:
        self._conclusion = conclusion

    def generate_structured(self, messages, response_model, schema_name):
        return self._conclusion

    def generate_text(self, messages):
        raise NotImplementedError


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol, entity=EntityReference(kind="symbol", value=symbol, display_name=symbol),
        explanation="test fixture",
    )


def _context(resolved_entities=None, prior_results=None) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EVALUATE, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], raw_message="should I buy this?",
    )
    return AgentExecutionContext(
        grounded_context=grounded, memory=ConversationMemory(), prior_results=prior_results or [],
    )


def _synthesized(conclusion: Conclusion, confidence: str = "moderate") -> SynthesizedConclusion:
    return SynthesizedConclusion(
        conclusion=conclusion, supporting_evidence=["technical picture is constructive"],
        assumptions=[], confidence=confidence, invalidating_conditions=["a sharp reversal in momentum"],
    )


def test_no_contributing_evidence_is_inconclusive():
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.INCONCLUSIVE)))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=[]))

    assert len(results) == 1
    assert results[0].recommendation is None
    assert "don't have any specialist findings" in results[0].facts[0]


def test_convergent_evidence_can_reach_buy():
    prior = [
        CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["RSI is 24"], evidence_signal="supportive"),
        CapabilityResult(agent=AgentName.RISK_ADVISOR, description="risk", facts=["low correlation"], evidence_signal="supportive"),
    ]
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.BUY, confidence="high")))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=prior))

    rec = results[0].recommendation
    assert rec is not None
    assert rec.conclusion == Conclusion.BUY
    assert rec.kind == "asset"
    assert set(rec.contributing_agents) == {AgentName.TECHNICAL_ANALYST, AgentName.RISK_ADVISOR}


def test_conflicting_evidence_can_reach_wait():
    prior = [
        CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["RSI is 24"], evidence_signal="supportive"),
        CapabilityResult(agent=AgentName.RISK_ADVISOR, description="risk", facts=["high correlation, elevated volatility"], evidence_signal="concerning"),
    ]
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.WAIT)))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=prior))

    assert results[0].recommendation.conclusion == Conclusion.WAIT


def test_sell_is_downgraded_to_wait_when_position_not_confirmed_held():
    prior = [
        CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["RSI is 82"], evidence_signal="concerning"),
        CapabilityResult(agent=AgentName.PORTFOLIO_ANALYST, description="history", facts=["no recent history"], held_position=False),
    ]
    # LLM (faked) incorrectly tries to recommend SELL despite no confirmed holding.
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.SELL)))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=prior))

    assert results[0].recommendation.conclusion == Conclusion.WAIT  # hard-gated, not SELL


def test_sell_is_allowed_when_position_confirmed_held():
    prior = [
        CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["RSI is 82"], evidence_signal="concerning"),
        CapabilityResult(agent=AgentName.PORTFOLIO_ANALYST, description="history", facts=["held"], held_position=True),
    ]
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.SELL)))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=prior))

    assert results[0].recommendation.conclusion == Conclusion.SELL


def test_error_and_refusal_results_are_excluded_from_contributing_agents():
    prior = [
        CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="ok", facts=["RSI is 24"], evidence_signal="supportive"),
        CapabilityResult(agent=AgentName.MARKET_RESEARCH, kind=ResultKind.ERROR, description="failed"),
    ]
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.WATCH)))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=prior))

    assert results[0].recommendation.contributing_agents == [AgentName.TECHNICAL_ANALYST]


def test_recommendation_cannot_carry_a_draft_change():
    # Structural guarantee already enforced by CapabilityResult's own
    # validator (test_agent_contracts.py) -- this just confirms
    # InvestmentAnalystAgent never even attempts to set draft_change.
    prior = [CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="ok", facts=["RSI is 24"], evidence_signal="supportive")]
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.BUY)))
    results = agent.execute(_context(resolved_entities=[_resolved("NVDA")], prior_results=prior))

    assert results[0].draft_change is None


def test_strategy_kind_when_no_asset_entity_resolved():
    prior = [CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="ok", facts=["RSI-based rules tend to react faster than SMA-based ones"], evidence_signal="neutral")]
    agent = InvestmentAnalystAgent(FakeLLMService(_synthesized(Conclusion.WATCH)))
    results = agent.execute(_context(resolved_entities=[], prior_results=prior))

    assert results[0].recommendation.kind == "strategy"
    assert results[0].recommendation.subject == []