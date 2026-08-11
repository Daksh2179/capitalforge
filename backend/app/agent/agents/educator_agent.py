"""EducatorAgent: canned, hand-reviewed explanations for concepts
ConceptDirectory already knows. Deliberately NOT LLM-generated --
concept definitions are static, universal facts, not live data. A
once-reviewed, deterministic explanation is strictly safer here than
a probabilistic one: zero hallucination risk on something that never
changes. This is the "Educator receives concepts and explanatory
material rather than live trading data" design from
docs/conversation_principles.md, made concrete.

Two tiers per concept (NORMAL / EXPANDED) -- genuine use of
progressive disclosure, not just a placeholder for it.
"""

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.conversation_memory import ConceptReference
from app.agent.pipeline.types import AgentExecutionContext, DetailLevel

_EXPLANATIONS: dict[str, dict[str, str]] = {
    "RSI": {
        "normal": (
            "RSI (Relative Strength Index) measures how fast and how much a price has "
            "moved recently, on a scale of 0-100. Conventionally, readings below 30 are "
            "read as oversold and above 70 as overbought."
        ),
        "expanded": (
            "RSI (Relative Strength Index) is calculated from the average size of recent "
            "up-moves versus down-moves over a chosen period (commonly 14 days), producing "
            "a value between 0 and 100. Conventionally, readings below 30 are read as "
            "oversold and above 70 as overbought -- these are widely-used conventions, not "
            "fixed rules, and different traders use different thresholds. Two analysts can "
            "look at the same RSI reading and interpret it differently. RSI describes past "
            "price behavior; it does not predict what a price will do next."
        ),
    },
    "SMA": {
        "normal": (
            "SMA (Simple Moving Average) is the average closing price over a chosen number "
            "of recent periods, smoothing out day-to-day noise to show the underlying trend."
        ),
        "expanded": (
            "SMA (Simple Moving Average) adds up the closing prices over a chosen number of "
            "periods (commonly 50 or 200 days) and divides by that number, updating each day "
            "as the oldest price drops off. It smooths short-term noise to show the "
            "underlying trend direction. Traders commonly watch whether price sits above or "
            "below a moving average, or whether a shorter average crosses a longer one, as a "
            "conventional signal of trend change -- not a guarantee of one."
        ),
    },
    "EMA": {
        "normal": (
            "EMA (Exponential Moving Average) is similar to a simple moving average, but "
            "weights recent prices more heavily, so it reacts faster to new price changes."
        ),
        "expanded": (
            "EMA (Exponential Moving Average) applies exponentially decreasing weight to "
            "older prices, so recent price changes influence the average more than a simple "
            "moving average would. This makes EMA react faster to new information but also "
            "more sensitive to short-term noise. Like SMA, it's a conventional trend-following "
            "tool, not a predictive one."
        ),
    },
    "MOVING_AVERAGE": {
        "normal": (
            "A moving average smooths out price data by averaging it over a recent window "
            "of time, making the underlying trend easier to see than raw price alone. "
            "SMA (simple) and EMA (exponential) are the two common types."
        ),
        "expanded": (
            "A moving average smooths price data by averaging it over a recent window of "
            "time. The two common types are SMA (Simple Moving Average, equal weight to "
            "every period) and EMA (Exponential Moving Average, more weight to recent "
            "periods, so it reacts faster). Both describe past price behavior; neither "
            "predicts future price movement."
        ),
    },
    "TECHNICAL_ANALYSIS": {
        "normal": (
            "Technical analysis studies price and volume patterns -- like RSI and moving "
            "averages -- to describe how an asset has been trading, using conventional "
            "readings rather than fundamentals like earnings or revenue."
        ),
        "expanded": (
            "Technical analysis studies price and volume history rather than a company's "
            "underlying financials. Common tools include RSI (momentum), moving averages "
            "(trend), and volume (conviction behind a move). Interpretation is conventional, "
            "not objective -- different traders can read the same chart differently -- and "
            "none of it predicts what a price will do next; it only describes what has "
            "already happened."
        ),
    },
}


class EducatorAgent:
    name = AgentName.EDUCATOR

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if not grounded.resolved_concepts:
            return [CapabilityResult(
                agent=self.name,
                description="Nothing to explain -- no concept was identified this turn",
                facts=["I'm not sure which concept you're asking about."],
            )]

        results: list[CapabilityResult] = []
        for concept in grounded.resolved_concepts:
            entry = _EXPLANATIONS.get(concept.name)
            if entry is None:
                results.append(CapabilityResult(
                    agent=self.name, description=f"No explanation available for {concept.name}",
                    facts=[f"I don't have a prepared explanation for {concept.name} yet."],
                ))
                continue

            tier = "expanded" if grounded.detail_level >= DetailLevel.EXPANDED else "normal"
            results.append(CapabilityResult(
                agent=self.name, description=f"Explained {concept.name}",
                facts=[entry[tier]],
                introduced_concepts=[ConceptReference(name=concept.name, introduced_by=self.name.value)],
            ))
        return results