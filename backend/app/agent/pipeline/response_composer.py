"""ResponseComposer: the single place responsible for the
conversational personality of the system. Agents produce structured
facts/interpretations/clarifications; Composer decides ordering,
transitions, what to omit, what to merge, and how much depth to show.
No Agent needs to know how the conversation sounds -- that
responsibility lives here alone.

Priority order, per docs/conversation_principles.md:
  1. Errors/refusals (ResultKind.ERROR/REFUSAL) -- always surface first
  2. The single most-relevant clarification (others deduped/deferred)
  3. Direct answers (every EXECUTED result's facts, not just one --
     a multi-Agent turn's facts collectively ARE the direct answer)
  4. At most one additional interpretation/insight in NORMAL detail;
     all interpretations in EXPANDED detail
  5. Honest "not implemented yet" notices, least urgent, shown last

Deliberately does NOT take suggested follow-ups (tier 6 in the
original design) as a real capability in V1 -- see
docs/decisions.md: no half-built heuristic here, since a mediocre
"suggested follow-up" is indistinguishable from exactly the
unsolicited-steering behavior this project has repeatedly refused to
build. Revisit only with real evidence of what's genuinely helpful.

The response shape (ComposedResponse.segments) is deliberately a list
of typed segments, not a bare string -- TextSegment is the only
member today, but this leaves room for richer segment types (tables,
charts, recommendation cards) later without redesigning the contract.
`.text` is a V1 convenience flattening for callers that only handle
plain text; once richer segment types exist, callers should iterate
`segments` directly instead.
"""

from dataclasses import dataclass
from typing import Hashable

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest, ResultKind
from app.agent.pipeline.types import (
    ConversationExecutionPlan,
    ConversationStepStatus,
    DetailLevel,
)


@dataclass(frozen=True)
class TextSegment:
    text: str


# Union expands later (TableSegment, ChartSegment, RecommendationCardSegment,
# ...) -- currently a single-member alias, deliberately not a bare `str`.
ResponseSegment = TextSegment


@dataclass(frozen=True)
class ComposedResponse:
    segments: list[ResponseSegment]
    surfaced_clarification: ClarificationRequest | None
    deferred_clarification_count: int

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.segments if isinstance(s, TextSegment))


def _clarification_dedup_key(cr: ClarificationRequest) -> Hashable:
    """Two clarifications are the same underlying ambiguity if they
    share candidates (the classic "which ticker" case) or the same
    `about` entity. Absent both, there's no basis to merge them, so
    each gets its own key and is never combined with another."""
    if cr.candidates:
        return frozenset(cr.candidates)
    if cr.about is not None:
        return ("entity", cr.about.kind, cr.about.value)
    return id(cr)


def _merge_clarifications(group: list[tuple[AgentName, ClarificationRequest]]) -> ClarificationRequest:
    """The user should feel like they're answering one question, not
    whichever Agent happened to ask first -- union candidates across
    every clarification in the group rather than picking one verbatim."""
    all_candidates = sorted({c for _, cr in group for c in cr.candidates})
    about = next((cr.about for _, cr in group if cr.about is not None), None)
    if all_candidates:
        question = f"Which did you mean: {', '.join(all_candidates)}?"
    else:
        question = group[0][1].question_text
    return ClarificationRequest(question_text=question, about=about, candidates=all_candidates)


def _arbitrate_clarifications(
    items: list[tuple[AgentName, ClarificationRequest]]
) -> tuple[ClarificationRequest | None, int]:
    """Dedup by underlying ambiguity, then surface the first distinct
    group in plan order -- reusing Grounding's already-established
    relevance ordering rather than inventing a new Agent-priority
    heuristic we have no evidence to justify. Returns the number of
    DISTINCT deferred ambiguities, not the raw count of Agent
    clarifications, matching Memory's one-thread-per-ambiguity model."""
    if not items:
        return None, 0

    groups: dict[Hashable, list[tuple[AgentName, ClarificationRequest]]] = {}
    order: list[Hashable] = []
    for agent, cr in items:
        key = _clarification_dedup_key(cr)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((agent, cr))

    surfaced = _merge_clarifications(groups[order[0]])
    deferred_count = len(order) - 1
    return surfaced, deferred_count


def compose(plan: ConversationExecutionPlan, detail_level: DetailLevel = DetailLevel.NORMAL) -> ComposedResponse:
    executed = [(step.agent, r) for step in plan.steps if step.status == ConversationStepStatus.EXECUTED for r in step.results]
    not_implemented = [step for step in plan.steps if step.status == ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED]

    error_results: list[CapabilityResult] = []
    clarification_items: list[tuple[AgentName, ClarificationRequest]] = []
    normal_results: list[CapabilityResult] = []

    for agent, result in executed:
        if result.kind in (ResultKind.ERROR, ResultKind.REFUSAL):
            error_results.append(result)
        elif result.clarification is not None:
            clarification_items.append((agent, result.clarification))
        else:
            normal_results.append(result)

    surfaced_clarification, deferred_count = _arbitrate_clarifications(clarification_items)

    segments: list[ResponseSegment] = []

    for result in error_results:
        segments.append(TextSegment(result.description))

    if surfaced_clarification is not None:
        segments.append(TextSegment(surfaced_clarification.question_text))

    for result in normal_results:
        if result.facts:
            segments.append(TextSegment(" ".join(result.facts)))

    interpretations = [r.interpretation for r in normal_results if r.interpretation]
    if detail_level >= DetailLevel.EXPANDED:
        for interpretation in interpretations:
            segments.append(TextSegment(interpretation))
    elif interpretations:
        segments.append(TextSegment(interpretations[0]))

    limitations: list[str] = []
    seen_limitations: set[str] = set()
    for result in normal_results:
        for limitation in result.limitations:
            if limitation not in seen_limitations:
                seen_limitations.add(limitation)
                limitations.append(limitation)
    if limitations:
        segments.append(TextSegment("Assumptions: " + " ".join(limitations)))

    for step in not_implemented:
        if step.reason:
            segments.append(TextSegment(step.reason))

    return ComposedResponse(
        segments=segments, surfaced_clarification=surfaced_clarification,
        deferred_clarification_count=deferred_count,
    )