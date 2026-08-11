"""StrategyExplainerAgent: answers "why" questions about past edits.

V1 scope is honest about what the system actually knows: if a past
edit's ConversationEvent has real reasoning recorded (currently only
the capital-allocation-default case, from draft_updater.py), report
it. Otherwise, correctly say the user specified the value directly --
never fabricate a technical justification for a value nobody chose.

recent_events is capped at 5 -- an edit older than that genuinely
isn't recoverable this way. This Agent says so honestly rather than
guessing, matching the same "reconstructibility" discipline used
throughout Conversation Memory's design.

Reads Memory read-only via AgentExecutionContext; never writes it.
"""

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.pipeline.types import AgentExecutionContext


class StrategyExplainerAgent:
    name = AgentName.STRATEGY_EXPLAINER

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context
        memory = context.memory

        if not grounded.resolved_entities:
            return [CapabilityResult(
                agent=self.name, description="Nothing to explain -- no rule was identified this turn",
                facts=["I'm not sure which rule you're asking about."],
            )]

        results: list[CapabilityResult] = []
        for resolved in grounded.resolved_entities:
            symbol = resolved.entity.value
            matching_event = next(
                (e for e in memory.recent_events if any(ent.value == symbol for ent in e.related_entities)),
                None,
            )

            if matching_event is None:
                results.append(CapabilityResult(
                    agent=self.name, description=f"No recent record of an edit to {symbol}",
                    facts=[f"I don't have a record of a recent change to {symbol} in this conversation."],
                    affected_entities=[resolved.entity],
                ))
                continue

            if matching_event.reasoning:
                fact = f"For {symbol}: {matching_event.reasoning}"
            else:
                fact = f"For {symbol}, you specified that value directly -- I didn't choose it."

            results.append(CapabilityResult(
                agent=self.name, description=f"Explained the {symbol} edit",
                facts=[fact], affected_entities=[resolved.entity],
            ))
        return results