"""InvestmentAnalystAgent: the recommendation orchestrator. Performs
NO domain analysis itself -- never computes indicators, fetches
market data, or evaluates portfolio metrics. It only synthesizes
CapabilityResults the specialist Agents already produced THIS SAME
TURN (via AgentExecutionContext.prior_results, populated by
ConversationPipeline's fan-in -- see planner.py and
conversation_pipeline.py).

Only runs when Grounding classified the turn as EVALUATE (see
grounding.py's RESEARCH/EVALUATE tie-break) -- the sole gate for
unsolicited-vs-requested opinions, per docs/conversation_principles.md.

Synthesis is a genuine, constrained LLM call, not a decision tree. A
hand-written rule engine can only branch on evidence_signal labels or
their counts -- which is vote-counting with extra steps -- or invent a
materiality/severity scale, which is a numeric scoring system wearing
words instead of numbers. Weighing which specialist finding actually
matters more in a given combination is a genuine qualitative-judgment
task, the same category of task GoalExtractor already performs (real
language understanding), not a fact lookup. See docs/decisions.md for
the full reasoning that ruled out a rule-based alternative.

Guardrails enforced in CODE, not just requested in the prompt:
- kind, subject, contributing_agents are computed deterministically
  here, never trusted from the LLM -- it only ever produces the
  genuinely qualitative fields (conclusion, supporting_evidence,
  assumptions, confidence, invalidating_conditions), via
  SynthesizedConclusion, a schema narrower than Recommendation itself.
- SELL is only ever returned if PortfolioAnalystAgent's held_position
  fact (a real, structural, deterministic signal) is exactly True.
  If the LLM produces SELL without that confirmation, it is
  downgraded to WAIT here, unconditionally -- the prompt also states
  this rule, but the actual guarantee is this code, not the prompt.
- Confidence's meaning is locked verbatim in the system prompt:
  "Confidence represents the completeness, consistency and quality of
  the available evidence. It must never be interpreted as the
  probability that a trade will succeed."

Recommendation is speech only -- see CapabilityResult's mutual-
exclusivity validator (draft_change/recommendation). This Agent has no
mechanism to write to a draft, allocate capital, or place an order,
and never will.
"""

from app.agent.agent_contracts import (
    AgentName,
    CapabilityResult,
    Conclusion,
    Recommendation,
    ResultKind,
    SynthesizedConclusion,
)
from app.agent.llm_service import LLMService
from app.agent.pipeline.types import AgentExecutionContext

_SYNTHESIS_SYSTEM_PROMPT = """You are synthesizing findings from several specialist analysts into one \
investment recommendation. You do NOT have access to raw market data, indicators, or fundamentals \
yourself -- you may ONLY reason from the specialist findings provided below. Never invent a fact, \
number, or data point that isn't explicitly stated in those findings.

Confidence represents the completeness, consistency and quality of the available evidence. It must \
never be interpreted as the probability that a trade will succeed.

Rules:
1. Read each specialist's actual findings and reasoning. Do NOT count how many are "supportive" \
versus "concerning" and do not let the count determine your conclusion. Weigh the SUBSTANCE of what \
each specialist found. A single well-substantiated concern can outweigh several minor or contextual \
findings, and vice versa -- there is no fixed formula or vote count.
2. If a specialist's evidence is missing (they didn't run this turn, or found no data), state that \
explicitly as a limitation in your assumptions. Never treat missing evidence as positive, negative, \
or neutral support for a conclusion -- it is simply unavailable.
3. WAIT, WATCH, and INCONCLUSIVE are equally legitimate conclusions as BUY, SELL, and HOLD. Do not \
default to them just because evidence isn't unanimous, and do not force a directional conclusion when \
the evidence doesn't genuinely support one. Reach BUY, SELL, or HOLD when the evidence coherently \
supports it.
4. Only conclude SELL if the findings explicitly confirm the asset is CURRENTLY HELD in the \
portfolio. If ownership isn't confirmed, prefer WAIT instead of SELL, even if your assessment is \
negative -- there is nothing to sell if it isn't owned.
5. Never state or imply a probability of success, a price target, or a prediction of future price \
movement anywhere in your reasoning.
6. Your job is synthesis only -- do not introduce your own technical, fundamental, or risk judgment \
beyond what the specialists already reported."""


def _format_evidence(prior_results: list[CapabilityResult]) -> str:
    lines = []
    for result in prior_results:
        if result.agent == AgentName.INVESTMENT_ANALYST:
            continue
        label = result.agent.value.replace("_", " ").title()
        signal = f" [{result.evidence_signal}]" if result.evidence_signal else ""
        held = " [CURRENTLY HELD]" if result.held_position is True else " [NOT currently held]" if result.held_position is False else ""
        fact_text = " ".join(result.facts) if result.facts else result.description
        line = f"{label}{signal}{held}: {fact_text}"
        if result.interpretation:
            line += f" Interpretation: {result.interpretation}"
        lines.append(line)
    return "\n".join(lines)


class InvestmentAnalystAgent:
    name = AgentName.INVESTMENT_ANALYST

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context
        prior = context.prior_results

        contributing = [
            r for r in prior if r.agent != AgentName.INVESTMENT_ANALYST and r.kind == ResultKind.NORMAL
        ]

        if not contributing:
            return [CapabilityResult(
                agent=self.name, description="No specialist evidence available to synthesize",
                facts=["I don't have any specialist findings to synthesize into a recommendation this turn."],
            )]

        kind = "asset" if grounded.resolved_entities else "strategy"
        subject = [resolved.entity for resolved in grounded.resolved_entities]

        held_position = next(
            (r.held_position for r in prior if r.agent == AgentName.PORTFOLIO_ANALYST and r.held_position is not None),
            None,
        )

        messages = [
            {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": _format_evidence(prior)},
        ]
        synthesized = self._llm.generate_structured(messages, SynthesizedConclusion, schema_name="SynthesizedConclusion")

        conclusion = synthesized.conclusion
        if conclusion == Conclusion.SELL and held_position is not True:
            # Hard, code-enforced gate -- the prompt also states this
            # rule, but the actual guarantee is here, never trusted
            # from the LLM alone.
            conclusion = Conclusion.WAIT

        contributing_agents = [r.agent for r in contributing]

        recommendation = Recommendation(
            kind=kind, subject=subject, conclusion=conclusion,
            supporting_evidence=synthesized.supporting_evidence,
            assumptions=synthesized.assumptions,
            confidence=synthesized.confidence,
            invalidating_conditions=synthesized.invalidating_conditions,
            contributing_agents=contributing_agents,
        )

        return [CapabilityResult(
            agent=self.name, description="Synthesized a recommendation from specialist findings",
            recommendation=recommendation,
        )]