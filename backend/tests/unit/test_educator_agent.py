"""Unit tests for EducatorAgent."""

from app.agent.agents.educator_agent import EducatorAgent
from app.agent.conversation_memory import ConceptReference, ConversationMemory
from app.agent.pipeline.types import AgentExecutionContext, DetailLevel, GoalExtractionIntent, GroundedContext


def _context(
    intent: GoalExtractionIntent = GoalExtractionIntent.LEARN,
    resolved_concepts: list | None = None,
    detail_level: DetailLevel = DetailLevel.NORMAL,
) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=intent, goal_relation=None, goal_summary=None,
        resolved_concepts=resolved_concepts or [], detail_level=detail_level, raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory())


def test_known_concept_returns_normal_explanation_by_default():
    agent = EducatorAgent()
    context = _context(resolved_concepts=[ConceptReference(name="RSI", introduced_by="grounding")])

    results = agent.execute(context)

    assert len(results) == 1
    assert "Relative Strength Index" in results[0].facts[0]
    assert results[0].introduced_concepts[0].name == "RSI"


def test_expanded_detail_returns_longer_explanation():
    agent = EducatorAgent()
    context = _context(
        resolved_concepts=[ConceptReference(name="RSI", introduced_by="grounding")],
        detail_level=DetailLevel.EXPANDED,
    )

    results = agent.execute(context)

    assert len(results[0].facts[0]) > 100
    assert "predict" in results[0].facts[0]


def test_no_concept_resolved_reports_honest_gap():
    agent = EducatorAgent()
    context = _context(resolved_concepts=[])

    results = agent.execute(context)

    assert "not sure which concept" in results[0].facts[0]


def test_multiple_concepts_each_get_their_own_explanation():
    agent = EducatorAgent()
    context = _context(resolved_concepts=[
        ConceptReference(name="RSI", introduced_by="grounding"),
        ConceptReference(name="SMA", introduced_by="grounding"),
    ])

    results = agent.execute(context)

    assert len(results) == 2
    names = {r.introduced_concepts[0].name for r in results}
    assert names == {"RSI", "SMA"}