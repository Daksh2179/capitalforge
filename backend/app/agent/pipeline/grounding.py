"""Grounding: the deterministic step that turns Goal Extraction's
hypothesis into something trustworthy. Never self-reported by the
LLM — every judgment here is checkable against real data (AssetDirectory
scores, ConceptDirectory, ConversationMemory) and comes with an
explanation, per docs/conversation_principles.md.

AMBIGUITY_THRESHOLD is documented as an implementation constant, not a
product decision — see docs/decisions.md for the real score-distribution
investigation that produced it.

Concept recognition (RSI, SMA, "moving average", "technicals") is
checked BEFORE asset resolution for every mentioned entity — a mention
that matches ConceptDirectory is a concept, never attempted against
AssetDirectory. This ordering matters: without it, "RSI" would be
searched as if it might be a ticker and correctly fail to match
anything, silently becoming an UnresolvedEntity instead of the concept
it actually is.
"""

from app.agent.concepts.concept_directory import ConceptDirectory
from app.agent.conversation_memory import ConceptReference, ConversationMemory, EntityReference
from app.agent.pipeline.types import (
    AmbiguityReason,
    AmbiguousEntity,
    DetailLevel,
    ExtractedGoal,
    GoalExtractionIntent,
    GoalRelation,
    GroundedContext,
    ResolvedEntity,
    UnresolvedEntity,
)
from app.assets.asset_directory import AssetDirectory
from app.agent.agent_contracts import AgentName

AMBIGUITY_THRESHOLD = 0.05

_V1_EVALUATIVE_MARKERS = [
    "should i", "should we", "which is stronger", "which is better",
    "recommend", "worth it", "better than", "is it a good", "what do you think",
]

_V1_EXPAND_MARKERS = ["why", "explain more", "go deeper", "tell me more", "in more detail", "can you elaborate"]


def _is_evaluative(raw_message: str) -> bool:
    lowered = raw_message.lower()
    return any(marker in lowered for marker in _V1_EVALUATIVE_MARKERS)


def _detect_detail_level(raw_message: str) -> DetailLevel:
    """V1 uses explicit depth-request language as the trigger, same
    discipline as _is_evaluative -- documented starting point, not a
    permanent design. Checked independently of intent: "tell me more"
    carries the same meaning whether Goal Extraction happened to
    classify the turn as CONTINUE or something else."""
    lowered = raw_message.lower()
    if any(marker in lowered for marker in _V1_EXPAND_MARKERS):
        return DetailLevel.EXPANDED
    return DetailLevel.NORMAL


def _infer_implicit_reference(
    intent: GoalExtractionIntent, memory: ConversationMemory
) -> tuple[ResolvedEntity | None, ConceptReference | None]:
    """Only consulted when Goal Extraction found no explicit entity
    mentions this turn -- the pronoun/follow-up case ("what about its
    52-week low", "explain that")."""
    if intent == GoalExtractionIntent.LEARN and memory.recent_concepts:
        return None, memory.recent_concepts[0]

    if memory.primary_focus:
        return (
            ResolvedEntity(
                raw_text="(implicit)",
                entity=memory.primary_focus,
                explanation=(
                    f"No entity mentioned this turn; inferred {memory.primary_focus.display_name} "
                    f"from the current conversational focus."
                ),
            ),
            None,
        )

    return None, None


def _resolve_entity(
    raw_text: str, asset_directory: AssetDirectory
) -> ResolvedEntity | AmbiguousEntity | UnresolvedEntity:
    matches = asset_directory.search_scored(raw_text, limit=3)

    if not matches:
        return UnresolvedEntity(
            raw_text=raw_text, reason=AmbiguityReason.NO_MATCH,
            explanation=f"No matches found for {raw_text!r}.",
        )

    top = matches[0]

    if len(matches) == 1:
        return ResolvedEntity(
            raw_text=raw_text,
            entity=EntityReference(kind="symbol", value=top.entry.symbol,
                                    display_name=f"{top.entry.name} ({top.entry.symbol})"),
            explanation=f"{top.entry.symbol} scored {top.score:.1f}; no other candidates.",
        )

    second = matches[1]
    gap_pct = (top.score - second.score) / top.score if top.score else 0.0

    if gap_pct < AMBIGUITY_THRESHOLD:
        return AmbiguousEntity(
            raw_text=raw_text, reason=AmbiguityReason.MULTIPLE_CLOSE_MATCHES,
            candidates=[m.entry.symbol for m in matches],
            explanation=(
                f"{top.entry.symbol} scored {top.score:.1f} and {second.entry.symbol} "
                f"scored {second.score:.1f} ({gap_pct * 100:.1f}% gap, below the "
                f"{AMBIGUITY_THRESHOLD * 100:.0f}% threshold)."
            ),
        )

    return ResolvedEntity(
        raw_text=raw_text,
        entity=EntityReference(kind="symbol", value=top.entry.symbol,
                                display_name=f"{top.entry.name} ({top.entry.symbol})"),
        explanation=(
            f"{top.entry.symbol} scored {top.score:.1f} vs next candidate "
            f"{second.entry.symbol} at {second.score:.1f} ({gap_pct * 100:.1f}% gap)."
        ),
    )


def ground(
    extracted: ExtractedGoal,
    raw_message: str,
    memory: ConversationMemory,
    asset_directory: AssetDirectory,
    concept_directory: ConceptDirectory | None = None,
) -> GroundedContext:
    concept_directory = concept_directory or ConceptDirectory()

    intent = extracted.intent
    if intent == GoalExtractionIntent.EVALUATE and not _is_evaluative(raw_message):
        intent = GoalExtractionIntent.RESEARCH

    resolved: list[ResolvedEntity] = []
    ambiguous: list[AmbiguousEntity] = []
    unresolved: list[UnresolvedEntity] = []
    resolved_concepts: list[ConceptReference] = []

    if extracted.mentioned_entities:
        for raw_mention in extracted.mentioned_entities:
            concept_entry = concept_directory.lookup(raw_mention)
            if concept_entry is not None:
                resolved_concepts.append(
                    ConceptReference(name=concept_entry.canonical_name, introduced_by="grounding")
                )
                continue

            outcome = _resolve_entity(raw_mention, asset_directory)
            if isinstance(outcome, ResolvedEntity):
                resolved.append(outcome)
            elif isinstance(outcome, AmbiguousEntity):
                ambiguous.append(outcome)
            else:
                unresolved.append(outcome)
    else:
        implicit_entity, implicit_concept = _infer_implicit_reference(intent, memory)
        if implicit_entity:
            resolved.append(implicit_entity)
        if implicit_concept:
            resolved_concepts.append(implicit_concept)

    confirmed_agents: list[AgentName] = []
    for raw_agent in extracted.candidate_agents:
        try:
            confirmed_agents.append(AgentName(raw_agent))
        except ValueError:
            continue

    continue_with_nothing_active = (
        intent == GoalExtractionIntent.CONTINUE and memory.active_goal is None
    )

    goal_relation = None if extracted.goal_relation == GoalRelation.NONE else extracted.goal_relation

    return GroundedContext(
        intent=intent,
        goal_relation=goal_relation,
        goal_summary=extracted.goal_summary,
        resolved_entities=resolved,
        resolved_concepts=resolved_concepts,
        ambiguous_entities=ambiguous,
        unresolved_entities=unresolved,
        confirmed_agents=confirmed_agents,
        continue_with_nothing_active=continue_with_nothing_active,
        detail_level=_detect_detail_level(raw_message),
        raw_message=raw_message,
    )