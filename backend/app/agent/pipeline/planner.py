"""Builds a ConversationExecutionPlan from a GroundedContext. Only one
real ordering rule exists: InvestmentAnalystAgent, if confirmed, is
always scheduled last -- it's the only Agent whose entire job depends
on other Agents' results from the same turn (see AgentExecutionContext.
prior_results). Everything else preserves Grounding's original order,
which already reflects its own relevance judgment. This is
deliberately narrow -- a general dependency/ordering framework was
explicitly ruled out; this is one targeted rule, not infrastructure.
"""

from app.agent.agent_contracts import AgentName
from app.agent.pipeline.types import ConversationExecutionPlan, ConversationExecutionStep, ConversationStepStatus, GroundedContext


def build_execution_plan(context: GroundedContext) -> ConversationExecutionPlan:
    agents = list(context.confirmed_agents)
    if AgentName.INVESTMENT_ANALYST in agents:
        agents = [a for a in agents if a != AgentName.INVESTMENT_ANALYST] + [AgentName.INVESTMENT_ANALYST]

    return ConversationExecutionPlan(steps=[
        ConversationExecutionStep(agent=agent, status=ConversationStepStatus.PLANNED)
        for agent in agents
    ])