"""Unit tests for ResponseComposer -- priority ordering, clarification
arbitration/merging, and progressive disclosure. Exercised directly
against a ConversationExecutionPlan, same standalone-first discipline
as every prior Agent before it was wired into ConversationPipeline."""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest, ResultKind
from app.agent.pipeline.response_composer import compose
from app.agent.pipeline.types import (
    ConversationExecutionPlan,
    ConversationExecutionStep,
    ConversationStepStatus,
    DetailLevel,
)


def _executed(agent: AgentName, *results: CapabilityResult) -> ConversationExecutionStep:
    return ConversationExecutionStep(agent=agent, status=ConversationStepStatus.EXECUTED, results=list(results))


def test_error_result_surfaces_before_normal_facts():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.MARKET_RESEARCH, CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="NVDA facts", facts=["NVDA is at $184."])),
        _executed(AgentName.STRATEGY_BUILDER, CapabilityResult(agent=AgentName.STRATEGY_BUILDER, kind=ResultKind.ERROR, description="Something went wrong.")),
    ])
    response = compose(plan)

    assert response.segments[0].text == "Something went wrong."
    assert "NVDA is at $184." in response.text


def test_single_clarification_surfaces_and_suppresses_nothing_else():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.MARKET_RESEARCH, CapabilityResult(
            agent=AgentName.MARKET_RESEARCH, description="asked which asset",
            clarification=ClarificationRequest(question_text="Which did you mean: GOOGL, GOOG?", candidates=["GOOGL", "GOOG"]),
        )),
    ])
    response = compose(plan)

    assert response.surfaced_clarification is not None
    assert response.deferred_clarification_count == 0


def test_two_agents_raising_the_same_ambiguity_are_merged_not_duplicated():
    shared = ["GOOGL", "GOOG"]
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.MARKET_RESEARCH, CapabilityResult(
            agent=AgentName.MARKET_RESEARCH, description="asked",
            clarification=ClarificationRequest(question_text="Which asset for research?", candidates=shared),
        )),
        _executed(AgentName.TECHNICAL_ANALYST, CapabilityResult(
            agent=AgentName.TECHNICAL_ANALYST, description="asked",
            clarification=ClarificationRequest(question_text="Which asset for technicals?", candidates=shared),
        )),
    ])
    response = compose(plan)

    assert response.deferred_clarification_count == 0  # merged into ONE, not two
    assert set(response.surfaced_clarification.candidates) == {"GOOGL", "GOOG"}


def test_two_agents_raising_different_ambiguities_defer_the_second():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.MARKET_RESEARCH, CapabilityResult(
            agent=AgentName.MARKET_RESEARCH, description="asked",
            clarification=ClarificationRequest(question_text="Which company?", candidates=["GOOGL", "GOOG"]),
        )),
        _executed(AgentName.TECHNICAL_ANALYST, CapabilityResult(
            agent=AgentName.TECHNICAL_ANALYST, description="asked",
            clarification=ClarificationRequest(question_text="Which indicator?", candidates=["SMA", "EMA"]),
        )),
    ])
    response = compose(plan)

    assert response.deferred_clarification_count == 1
    assert set(response.surfaced_clarification.candidates) == {"GOOGL", "GOOG"}  # first in plan order


def test_normal_detail_shows_at_most_one_interpretation_across_the_whole_turn():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.TECHNICAL_ANALYST, CapabilityResult(
            agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["RSI is 24."], interpretation="Oversold by convention.",
        )),
        _executed(AgentName.RISK_ADVISOR, CapabilityResult(
            agent=AgentName.RISK_ADVISOR, description="risk", facts=["Volatility is elevated."], interpretation="Higher than the 90-day average.",
        )),
    ])
    response = compose(plan, detail_level=DetailLevel.NORMAL)

    interpretation_count = sum(1 for s in response.segments if s.text in ("Oversold by convention.", "Higher than the 90-day average."))
    assert interpretation_count == 1


def test_expanded_detail_shows_every_interpretation():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.TECHNICAL_ANALYST, CapabilityResult(
            agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["RSI is 24."], interpretation="Oversold by convention.",
        )),
        _executed(AgentName.RISK_ADVISOR, CapabilityResult(
            agent=AgentName.RISK_ADVISOR, description="risk", facts=["Volatility is elevated."], interpretation="Higher than the 90-day average.",
        )),
    ])
    response = compose(plan, detail_level=DetailLevel.EXPANDED)

    assert "Oversold by convention." in response.text
    assert "Higher than the 90-day average." in response.text


def test_multiple_agents_facts_all_appear_not_just_the_first():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.MARKET_RESEARCH, CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="price", facts=["NVDA is at $184."])),
        _executed(AgentName.TECHNICAL_ANALYST, CapabilityResult(agent=AgentName.TECHNICAL_ANALYST, description="rsi", facts=["NVDA's RSI is 24."])),
    ])
    response = compose(plan)

    assert "NVDA is at $184." in response.text
    assert "NVDA's RSI is 24." in response.text


def test_not_implemented_steps_appear_last():
    plan = ConversationExecutionPlan(steps=[
        _executed(AgentName.MARKET_RESEARCH, CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="price", facts=["NVDA is at $184."])),
        ConversationExecutionStep(
            agent=AgentName.FUNDAMENTAL_ANALYST, status=ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED,
            reason="I understood this as a Fundamental Analysis request, but that Agent hasn't been implemented yet.",
        ),
    ])
    response = compose(plan)

    assert response.segments[-1].text == "I understood this as a Fundamental Analysis request, but that Agent hasn't been implemented yet."


def test_empty_plan_produces_empty_response():
    response = compose(ConversationExecutionPlan(steps=[]))

    assert response.segments == []
    assert response.text == ""
    assert response.surfaced_clarification is None