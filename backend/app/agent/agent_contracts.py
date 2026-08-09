"""The universal Agent contract types: CapabilityResult (what every
Agent returns, regardless of domain), Recommendation, and Conclusion.
No Agent implementations live here -- StrategyBuilderAgent is the
first one, built as its own step. This module exists so
memory_update_policy.py has something concrete to consume before any
real Agent exists.

See docs/conversation_principles.md for the philosophy this encodes,
in particular: draft_change and recommendation are mutually exclusive
on every CapabilityResult, permanently, enforced below at the type
level rather than left to convention.
"""

import enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agent.conversation_memory import ConceptReference, EntityReference
from app.agent.translation.translation_result import AppliedOperation


class AgentName(str, enum.Enum):
    STRATEGY_BUILDER = "strategy_builder"
    STRATEGY_EDITOR = "strategy_editor"
    STRATEGY_EXPLAINER = "strategy_explainer"
    MARKET_RESEARCH = "market_research"
    TECHNICAL_ANALYST = "technical_analyst"
    FUNDAMENTAL_ANALYST = "fundamental_analyst"
    PORTFOLIO_ANALYST = "portfolio_analyst"
    PERFORMANCE_ANALYST = "performance_analyst"
    RISK_ADVISOR = "risk_advisor"
    INVESTMENT_ANALYST = "investment_analyst"


class Conclusion(str, enum.Enum):
    """WAIT is the default safe outcome -- not trading is always a
    valid decision throughout CapitalForge. INCONCLUSIVE is a
    legitimate answer when specialists' evidence genuinely conflicts,
    reported honestly rather than forced toward a lean."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WAIT = "wait"
    WATCH = "watch"
    INCONCLUSIVE = "inconclusive"


class Recommendation(BaseModel):
    """Produced only by InvestmentAnalystAgent, only when intent
    ground to EVALUATE. confidence is about evidence quality, never
    about probability of success -- see the locked sentence in
    docs/conversation_principles.md, which this docstring restates
    deliberately rather than just referencing:

    Confidence represents the completeness, consistency and quality of
    the available evidence. It must never be interpreted as the
    probability that a trade will succeed.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str  # "asset" | "strategy"
    subject: list[EntityReference]
    conclusion: Conclusion
    supporting_evidence: list[str]
    assumptions: list[str]
    confidence: str  # "high" | "moderate" | "low"
    invalidating_conditions: list[str]
    contributing_agents: list[AgentName]


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: str
    about: EntityReference | None = None
    candidates: list[str] = []


class CapabilityResult(BaseModel):
    """What every Agent returns, regardless of domain. description is
    required -- every Agent action must be traceable back to a plain-
    language record of what happened (see docs/conversation_principles.md,
    "Traceability"), which is what description becomes once it's
    folded into a ConversationEvent.

    resolves_prior_thread and clarification are how an Agent signals
    memory changes without owning Memory itself -- memory_update_policy
    is the only thing that actually applies them.
    """

    model_config = ConfigDict(extra="forbid")

    agent: AgentName
    description: str
    reasoning: str | None = None

    facts: list[str] = []
    interpretation: str | None = None
    confidence_note: str | None = None

    draft_change: AppliedOperation | None = None
    recommendation: Recommendation | None = None

    affected_entities: list[EntityReference] = []
    introduced_concepts: list[ConceptReference] = []

    clarification: ClarificationRequest | None = None
    resolves_prior_thread: bool = False

    @model_validator(mode="after")
    def _draft_change_and_recommendation_are_mutually_exclusive(self) -> "CapabilityResult":
        if self.draft_change is not None and self.recommendation is not None:
            raise ValueError(
                "CapabilityResult cannot carry both draft_change and recommendation -- "
                "no Agent that renders an opinion may also write to the draft in the same turn."
            )
        return self