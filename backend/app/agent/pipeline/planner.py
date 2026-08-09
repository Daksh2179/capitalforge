"""Builds a ConversationExecutionPlan from a GroundedContext. V1 is
deliberately trivial -- one PLANNED step per confirmed Agent, in
order, no dependencies. This gives the pipeline a place to grow
ordering/dependency/fan-out logic later without another rewrite, the
same evolution path the trading engine's Opportunity Engine followed.
"""

from app.agent.pipeline.types import ConversationExecutionPlan, ConversationExecutionStep, ConversationStepStatus, GroundedContext


def build_execution_plan(context: GroundedContext) -> ConversationExecutionPlan:
    return ConversationExecutionPlan(steps=[
        ConversationExecutionStep(agent=agent, status=ConversationStepStatus.PLANNED)
        for agent in context.confirmed_agents
    ])