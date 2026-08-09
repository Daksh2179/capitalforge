"""Unit tests for memory_update_policy -- tracing the same scenarios
worked through by hand during design (the dividend-portfolio / KO-PEP
session, and the individual stress-test findings), now as real,
checkable behavior."""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest
from app.agent.conversation_memory import ConceptReference, ConversationMemory, EntityReference, ThreadState
from app.agent.memory_update_policy import apply_execution_update, apply_goal_update


def _entity(value: str, kind: str = "symbol") -> EntityReference:
    return EntityReference(kind=kind, value=value, display_name=value)


def test_new_goal_relation_establishes_active_goal():
    memory = ConversationMemory()
    updated = apply_goal_update(
        memory, goal_relation="NEW", goal_summary="building a dividend-focused portfolio", turn=1
    )
    assert updated.active_goal is not None
    assert updated.active_goal.summary == "building a dividend-focused portfolio"
    assert updated.active_goal.status == "ACTIVE"


def test_subtask_relation_leaves_existing_goal_untouched():
    memory = apply_goal_update(ConversationMemory(), goal_relation="NEW", goal_summary="dividend portfolio", turn=1)
    updated = apply_goal_update(memory, goal_relation="SUBTASK", goal_summary="compare KO and PEP", turn=2)
    assert updated.active_goal.summary == "dividend portfolio"


def test_abandon_and_replace_sets_a_new_goal():
    memory = apply_goal_update(ConversationMemory(), goal_relation="NEW", goal_summary="dividend portfolio", turn=1)
    updated = apply_goal_update(memory, goal_relation="ABANDON_AND_REPLACE", goal_summary="growth stocks", turn=2)
    assert updated.active_goal.summary == "growth stocks"


def test_none_goal_relation_is_a_no_op():
    memory = apply_goal_update(ConversationMemory(), goal_relation="NEW", goal_summary="dividend portfolio", turn=1)
    updated = apply_goal_update(memory, goal_relation=None, goal_summary=None, turn=2)
    assert updated.active_goal.summary == "dividend portfolio"


def test_single_entity_mention_sets_primary_focus_only():
    result = CapabilityResult(
        agent=AgentName.MARKET_RESEARCH, description="Reported on NVDA",
        affected_entities=[_entity("NVDA")],
    )
    updated = apply_execution_update(ConversationMemory(), [result], turn=1)
    assert updated.primary_focus.value == "NVDA"
    assert updated.comparison_focus is None


def test_two_entity_comparison_sets_both_foci_last_named_as_primary():
    result = CapabilityResult(
        agent=AgentName.MARKET_RESEARCH, description="Compared KO and PEP",
        affected_entities=[_entity("KO"), _entity("PEP")],
    )
    updated = apply_execution_update(ConversationMemory(), [result], turn=2)
    assert updated.primary_focus.value == "PEP"
    assert updated.comparison_focus.value == "KO"


def test_introduced_concept_is_recorded_and_resolvable_later():
    result = CapabilityResult(
        agent=AgentName.TECHNICAL_ANALYST, description="Reported NVDA's RSI",
        affected_entities=[_entity("NVDA")],
        introduced_concepts=[ConceptReference(name="RSI", introduced_by=AgentName.TECHNICAL_ANALYST.value)],
    )
    updated = apply_execution_update(ConversationMemory(), [result], turn=2)
    assert updated.recent_concepts[0].name == "RSI"


def test_reasoning_none_is_preserved_verbatim_not_fabricated():
    result = CapabilityResult(
        agent=AgentName.STRATEGY_BUILDER, description="Set AAPL buy condition RSI(14) < 30",
        reasoning=None,  # the user supplied 30 directly
        affected_entities=[_entity("AAPL")],
    )
    updated = apply_execution_update(ConversationMemory(), [result], turn=3)
    assert updated.recent_events[0].reasoning is None


def test_clarification_creates_a_waiting_for_user_thread():
    result = CapabilityResult(
        agent=AgentName.STRATEGY_BUILDER, description="Asked for specific dividend candidates",
        clarification=ClarificationRequest(question_text="Do you have specific stocks in mind?"),
    )
    updated = apply_execution_update(ConversationMemory(), [result], turn=1)
    assert len(updated.threads) == 1
    assert updated.threads[0].state == ThreadState.WAITING_FOR_USER


def test_resolves_prior_thread_marks_oldest_open_thread_answered():
    memory = apply_execution_update(
        ConversationMemory(),
        [CapabilityResult(
            agent=AgentName.STRATEGY_BUILDER, description="Asked for specific stocks",
            clarification=ClarificationRequest(question_text="Any stocks in mind?"),
        )],
        turn=1,
    )
    updated = apply_execution_update(
        memory,
        [CapabilityResult(
            agent=AgentName.MARKET_RESEARCH, description="Compared KO and PEP",
            affected_entities=[_entity("KO"), _entity("PEP")],
            resolves_prior_thread=True,
        )],
        turn=2,
    )
    assert updated.threads[0].state == ThreadState.RESOLVED
    assert updated.threads[0].resolution_reason == "answered"


def test_recent_entities_dedup_moves_existing_entity_to_front_not_duplicate():
    memory = apply_execution_update(
        ConversationMemory(),
        [CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="AAPL", affected_entities=[_entity("AAPL")])],
        turn=1,
    )
    memory = apply_execution_update(
        memory,
        [CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="NVDA", affected_entities=[_entity("NVDA")])],
        turn=2,
    )
    updated = apply_execution_update(
        memory,
        [CapabilityResult(agent=AgentName.MARKET_RESEARCH, description="AAPL again", affected_entities=[_entity("AAPL")])],
        turn=3,
    )
    values = [e.value for e in updated.recent_entities]
    assert values == ["AAPL", "NVDA"]  # not ["AAPL", "NVDA", "AAPL"]


def test_recent_events_capped_at_five():
    memory = ConversationMemory()
    for i in range(7):
        memory = apply_execution_update(
            memory,
            [CapabilityResult(agent=AgentName.MARKET_RESEARCH, description=f"event {i}")],
            turn=i,
        )
    assert len(memory.recent_events) == 5
    assert memory.recent_events[0].description == "event 6"