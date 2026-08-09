"""ConversationMemory: the generalized successor to ConversationState.
Represents what the conversation is currently about -- never the live
facts themselves. See docs/conversation_principles.md, "Conversation
Memory -- governing principles," for the rules that govern any future
change to this schema:

- References, not data: no cached prices, indicators, snapshots, or
  DecisionLog rows. Every Agent re-fetches live data every turn.
- No Agent owns Memory: only memory_update_policy.py writes this.
- Reconstructibility test: if a field could be deterministically
  rebuilt from persisted history without the LLM reasoning again, it
  doesn't belong here.
- Expiry is semantic, never a fixed TTL.

ConversationState is not removed by this file -- StrategyBuilderAgent
(not yet built) is what actually migrates callers from one to the
other. Until that migration, both coexist.
"""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EntityReference(BaseModel):
    """A resolved reference -- never raw user text. Symbol resolution's
    OUTPUT lives here; what the user typed never does."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # "symbol" | "asset_rule" | "strategy"
    value: str
    display_name: str


class ConceptReference(BaseModel):
    """A concept (e.g. "RSI") introduced into the conversation --
    resolvable by "that"/"this" just as naturally as an entity."""

    model_config = ConfigDict(extra="forbid")

    name: str
    introduced_by: str  # AgentName value; str here to avoid a circular
                         # import with agent_contracts.py, which itself
                         # imports EntityReference/ConceptReference from
                         # this module.
    related_entity: EntityReference | None = None


class TimeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    resolved_start: datetime
    resolved_end: datetime


class ThreadState(str, enum.Enum):
    OPEN = "open"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_DATA = "waiting_for_data"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class ConversationThread(BaseModel):
    """Unfinished conversational work in general -- clarification is
    one instance of this, not the whole concept. This is what lets
    "explain RSI... [detour]... continue that" reopen prior work
    instead of inventing something new."""

    model_config = ConfigDict(extra="forbid")

    raised_by: str  # AgentName value
    description: str
    about: EntityReference | None = None
    state: ThreadState = ThreadState.OPEN
    raised_at_turn: int
    resolution_reason: str | None = None
    # One of "answered" | "focus_changed" | "goal_changed" | "abandoned"
    # | "entity_gone" when state becomes RESOLVED or EXPIRED. Always
    # semantic -- never set due to a turn-count TTL.


class ConversationEvent(BaseModel):
    """What actually happened this turn, generalized beyond draft
    edits. Strategy Explainer's correctness depends entirely on
    reasoning being genuinely nullable: None means the user supplied
    the value directly, and Strategy Explainer must say so rather than
    fabricate a technical justification."""

    model_config = ConfigDict(extra="forbid")

    agent: str  # AgentName value
    description: str
    reasoning: str | None = None
    related_entities: list[EntityReference] = []
    timestamp: datetime


class ConversationGoal(BaseModel):
    """The grounded version of what the user is ultimately trying to
    accomplish -- not raw Goal Extraction output. Deliberately
    minimal; entity-level detail lives in primary_focus/
    comparison_focus, not duplicated here."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    status: str = "ACTIVE"  # "ACTIVE" | "PAUSED" | "COMPLETED" | "ABANDONED"
    established_at_turn: int


class ConversationMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_goal: ConversationGoal | None = None
    primary_focus: EntityReference | None = None
    comparison_focus: EntityReference | None = None
    recent_concepts: list[ConceptReference] = []
    active_time_reference: TimeReference | None = None
    recent_entities: list[EntityReference] = []
    recent_events: list[ConversationEvent] = []
    threads: list[ConversationThread] = []
    active_strategy_id: uuid.UUID | None = None