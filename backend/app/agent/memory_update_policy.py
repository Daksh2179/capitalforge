"""memory_update_policy: the one place ConversationMemory is ever
written. No Agent owns Memory -- Agents only produce CapabilityResults;
this module decides what survives, exactly the way Risk Manager is the
single source of truth for capital/position rules rather than letting
each caller reimplement its own version.

Two entry points, matching the two update points in the pipeline
(docs/conversation_principles.md):

  apply_goal_update      -- pre-routing, driven by Goal Extraction's
                             output (goal_relation/goal_summary). Not
                             yet wired to a real Goal Extraction
                             component -- these are passed as plain
                             values until that component exists.
  apply_execution_update -- post-execution, driven by the turn's
                             CapabilityResults.

Both are pure functions: (old_memory, new_signals, turn) -> new_memory.
Never in-place mutation, matching StrategyConfig/draft_updater's own
discipline.
"""

from datetime import datetime, timezone

from app.agent.agent_contracts import CapabilityResult
from app.agent.conversation_memory import (
    ConversationEvent,
    ConversationGoal,
    ConversationMemory,
    ConversationThread,
    ThreadState,
)

_MAX_RECENT = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def apply_goal_update(
    memory: ConversationMemory,
    *,
    goal_relation: str | None,  # "NEW" | "CONTINUATION" | "SUBTASK" | "ABANDON_AND_REPLACE" | None
    goal_summary: str | None,
    turn: int,
) -> ConversationMemory:
    if goal_relation is None:
        return memory

    if goal_relation in ("CONTINUATION", "SUBTASK"):
        # The existing goal governs this turn's sub-task; nothing about
        # the goal itself changes. (A future hierarchical ConversationGoal
        # -- Current Task / Previous Tasks / Completed Tasks, per
        # decisions.md -- is where SUBTASK would eventually record the
        # sub-task explicitly; V1 intentionally leaves that undifferentiated.)
        return memory

    if goal_relation == "NEW":
        if goal_summary is None:
            return memory
        return memory.model_copy(update={
            "active_goal": ConversationGoal(summary=goal_summary, status="ACTIVE", established_at_turn=turn)
        })

    if goal_relation == "ABANDON_AND_REPLACE":
        if goal_summary is None:
            return memory
        return memory.model_copy(update={
            "active_goal": ConversationGoal(summary=goal_summary, status="ACTIVE", established_at_turn=turn)
        })

    return memory


def apply_execution_update(
    memory: ConversationMemory,
    results: list[CapabilityResult],
    turn: int,
) -> ConversationMemory:
    if not results:
        return memory

    updated = memory

    # Focus: the last distinct entity mentioned across this turn's
    # results becomes primary_focus; the one immediately before it (if
    # different) becomes comparison_focus. This is what resolves both
    # "it"/"that" (single entity, primary_focus alone) and an explicit
    # two-entity comparison ("compare KO and PEP") in the same rule --
    # see docs/decisions.md for why a two-slot design was chosen over
    # a list, and why it still holds for 3+-entity comparisons (the
    # full set is available in that turn's GroundedContext regardless;
    # Memory only needs a reasonable choice for *future* pronoun
    # resolution, not a complete record of the turn).
    all_entities = [e for r in results for e in r.affected_entities]
    if all_entities:
        new_primary = all_entities[-1]
        new_comparison = None
        for entity in reversed(all_entities[:-1]):
            if entity != new_primary:
                new_comparison = entity
                break
        updated = updated.model_copy(update={
            "primary_focus": new_primary,
            "comparison_focus": new_comparison,
        })

    # Concepts: dedup by name, most-recent first, capped -- same
    # pattern as recently_referenced_symbols in ConversationState today.
    new_concepts = list(updated.recent_concepts)
    for result in results:
        for concept in result.introduced_concepts:
            new_concepts = [c for c in new_concepts if c.name != concept.name]
            new_concepts.insert(0, concept)
    updated = updated.model_copy(update={"recent_concepts": new_concepts[:_MAX_RECENT]})

    # Entities: same dedup-and-cap pattern.
    new_recent_entities = list(updated.recent_entities)
    for entity in all_entities:
        new_recent_entities = [e for e in new_recent_entities if not (e.kind == entity.kind and e.value == entity.value)]
        new_recent_entities.insert(0, entity)
    updated = updated.model_copy(update={"recent_entities": new_recent_entities[:_MAX_RECENT]})

    # Events: always recorded, one per result, reasoning carried through
    # verbatim (including None -- never fabricated here or anywhere else).
    new_events = list(updated.recent_events)
    for result in results:
        new_events.insert(0, ConversationEvent(
            agent=result.agent.value, description=result.description,
            reasoning=result.reasoning, related_entities=result.affected_entities,
            timestamp=_utcnow(),
        ))
    updated = updated.model_copy(update={"recent_events": new_events[:_MAX_RECENT]})

    # Threads: resolve the oldest still-open thread if any result
    # signals it answered one. NOTE: matching by "oldest open," not by
    # which entity it's about -- a real limitation until Grounding
    # exists to match a resolution to the specific thread it actually
    # answers. Documented here rather than silently assumed correct.
    new_threads = list(updated.threads)
    if any(r.resolves_prior_thread for r in results):
        for i, thread in enumerate(new_threads):
            if thread.state in (ThreadState.OPEN, ThreadState.WAITING_FOR_USER, ThreadState.WAITING_FOR_DATA):
                new_threads[i] = thread.model_copy(update={
                    "state": ThreadState.RESOLVED, "resolution_reason": "answered",
                })
                break

    for result in results:
        if result.clarification is not None:
            new_threads.append(ConversationThread(
                raised_by=result.agent.value, description=result.clarification.question_text,
                about=result.clarification.about, state=ThreadState.WAITING_FOR_USER,
                raised_at_turn=turn,
            ))

    updated = updated.model_copy(update={"threads": new_threads})

    return updated