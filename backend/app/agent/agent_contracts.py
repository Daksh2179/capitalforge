"""The universal Agent contract types: CapabilityResult (what every
Agent returns, regardless of domain), Recommendation, and Conclusion.
No Agent implementations live here -- StrategyBuilderAgent is the
first one, built as its own step.

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
    EDUCATOR = "educator"
    BACKTEST_ANALYST = "backtest_analyst"


class Conclusion(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WAIT = "wait"
    WATCH = "watch"
    INCONCLUSIVE = "inconclusive"


class ResultKind(str, enum.Enum):
    """Lets ResponseComposer apply priority ordering (errors/refusals
    surface first) structurally, without inferring anything from text
    content. NORMAL covers ordinary facts AND honest limitations
    ("I don't have data for X") -- a limitation is not a failure, it's
    correct reporting. Only a genuine system error or a deliberate
    policy refusal (e.g. a future suitability-advice decline) use the
    other two values."""

    NORMAL = "normal"
    REFUSAL = "refusal"
    ERROR = "error"


class Recommendation(BaseModel):
    """Produced only by InvestmentAnalystAgent, only when intent
    ground to EVALUATE. confidence is about evidence quality, never
    about probability of success:

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

class PortfolioChangeType(str, enum.Enum):
    ADD = "add"
    REMOVE = "remove"


class PortfolioChange(BaseModel):
    """The ONLY thing an Agent may declare about the user's
    portfolio-in-progress -- never a direct portfolio_service call.
    A separate, deterministic function (pipeline/portfolio_mutations.py)
    is the sole code path that ever performs the actual mutation,
    using the exact same portfolio_service the manual Portfolio-page
    UI calls -- one source of truth, two front doors, never two
    systems.
    """

    model_config = ConfigDict(extra="forbid")

    change_type: PortfolioChangeType
    symbol: str

class CapabilityResult(BaseModel):
    """What every Agent returns, regardless of domain. description is
    required -- every Agent action must be traceable back to a plain-
    language record of what happened.

    resolves_prior_thread and clarification are how an Agent signals
    memory changes without owning Memory itself -- memory_update_policy
    is the only thing that actually applies them.
    """

    model_config = ConfigDict(extra="forbid")

    agent: AgentName
    kind: ResultKind = ResultKind.NORMAL
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
    evidence_signal: str | None = None
    held_position: bool | None = None
    limitations: list[str] = []
    portfolio_change: PortfolioChange | None = None
    

    @model_validator(mode="after")
    def _draft_change_and_recommendation_are_mutually_exclusive(self) -> "CapabilityResult":
        if self.draft_change is not None and self.recommendation is not None:
            raise ValueError(
                "CapabilityResult cannot carry both draft_change and recommendation -- "
                "no Agent that renders an opinion may also write to the draft in the same turn."
            )
        return self
    
class SynthesizedConclusion(BaseModel):
    """The only thing InvestmentAnalystAgent's LLM call actually
    produces -- deliberately narrower than Recommendation itself.
    kind/subject/contributing_agents are known deterministically and
    are never trusted from LLM output; SELL is validated and, if
    unsupported by a confirmed held position, downgraded to WAIT in
    code, not just requested via prompt."""

    model_config = ConfigDict(extra="forbid")

    conclusion: Conclusion
    supporting_evidence: list[str]
    assumptions: list[str]
    confidence: str
    invalidating_conditions: list[str]