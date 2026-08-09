"""Shared types for the conversation pipeline: ExtractedGoal (Goal
Extraction's LLM output), the entity-resolution outcomes Grounding
produces, GroundedContext, and the ConversationExecutionPlan --
deliberately mirroring the trading engine's ExecutionPlan shape
(Opportunity/ExecutionPlanEntry/PlanOutcome) rather than a plain list
of confirmed Agents, so this has the same room to grow dependencies,
ordering, and partial completion later without another rewrite.
"""

import enum
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.conversation_memory import ConceptReference,EntityReference


class GoalExtractionIntent(str, enum.Enum):
    LEARN = "learn"
    RESEARCH = "research"
    DECIDE = "decide"
    BUILD = "build"
    EDIT = "edit"
    EXPLAIN = "explain"
    REVIEW = "review"
    EVALUATE = "evaluate"
    CONTINUE = "continue"


class GoalRelation(str, enum.Enum):
    NEW = "new"
    CONTINUATION = "continuation"
    SUBTASK = "subtask"
    ABANDON_AND_REPLACE = "abandon_and_replace"


class ExtractedGoal(BaseModel):
    """Goal Extraction's entire output. Deliberately thin -- a
    hypothesis, not a verdict. It never decides ambiguity, confidence,
    or final routing; Grounding is free to override every field here
    except intent/goal_relation/goal_summary (pure language
    understanding, which IS Goal Extraction's job)."""

    model_config = ConfigDict(extra="forbid")

    intent: GoalExtractionIntent
    goal_relation: GoalRelation | None = None
    goal_summary: str | None = None
    mentioned_entities: list[str] = []
    candidate_agents: list[str] = []  # AgentName values as raw strings; corrected by Grounding


class AmbiguityReason(str, enum.Enum):
    MULTIPLE_CLOSE_MATCHES = "multiple_close_matches"
    NO_MATCH = "no_match"
    # LOW_CONFIDENCE is reserved, not yet used: a floor on absolute
    # match score (distinct from the relative gap MULTIPLE_CLOSE_MATCHES
    # already covers) has no empirical basis yet, same discipline as
    # the ambiguity threshold itself -- add it once real data justifies
    # a specific number, not before.
    LOW_CONFIDENCE = "low_confidence"


class ResolvedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    entity: EntityReference
    explanation: str


class AmbiguousEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    reason: AmbiguityReason
    candidates: list[str] = []
    explanation: str


class UnresolvedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    reason: AmbiguityReason = AmbiguityReason.NO_MATCH
    explanation: str


class GroundedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: GoalExtractionIntent
    goal_relation: GoalRelation | None
    goal_summary: str | None
    resolved_entities: list[ResolvedEntity] = []
    resolved_concepts: list[ConceptReference] = []
    ambiguous_entities: list[AmbiguousEntity] = []
    unresolved_entities: list[UnresolvedEntity] = []
    confirmed_agents: list[AgentName] = []
    continue_with_nothing_active: bool = False
    raw_message: str


class ConversationStepStatus(str, enum.Enum):
    PLANNED = "planned"
    EXECUTED = "executed"
    SKIPPED_NOT_IMPLEMENTED = "skipped_not_implemented"


@dataclass(frozen=True)
class ConversationExecutionStep:
    agent: AgentName
    status: ConversationStepStatus
    reason: str | None = None
    results: list[CapabilityResult] = field(default_factory=list)


@dataclass(frozen=True)
class ConversationExecutionPlan:
    steps: list[ConversationExecutionStep] = field(default_factory=list)

    @property
    def executed_results(self) -> list[CapabilityResult]:
        return [r for step in self.steps if step.status == ConversationStepStatus.EXECUTED for r in step.results]