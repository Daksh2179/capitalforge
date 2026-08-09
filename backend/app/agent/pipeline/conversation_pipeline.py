"""ConversationPipeline: the orchestrator. Goal Extraction -> Grounding
-> Execution Plan -> execute each planned step -> Memory update.

Not wired into api/agent.py. Standalone, fully tested infrastructure —
migrated into the live API only once enough Agents exist that
switching increases capability rather than decreasing it.

MarketResearchAgent is the first Agent to consume GroundedContext
directly (StrategyBuilderAgent is a permanent exception, carrying
legacy ConversationState alongside it) -- every future Agent added
here follows MarketResearchAgent's simpler pattern: agent.execute(context).
"""

from dataclasses import dataclass

from app.agent.agent_contracts import AgentName
from app.agent.agents.market_research_agent import MarketResearchAgent
from app.agent.agents.strategy_builder_agent import StrategyBuilderAgent
from app.agent.conversation_memory import ConversationMemory
from app.agent.conversation_state import ConversationState
from app.agent.memory_update_policy import apply_execution_update, apply_goal_update
from app.agent.pipeline.goal_extractor import GoalExtractor
from app.agent.pipeline.grounding import ground
from app.agent.pipeline.planner import build_execution_plan
from app.agent.pipeline.types import (
    ConversationExecutionPlan,
    ConversationExecutionStep,
    ConversationStepStatus,
    GroundedContext,
)
from app.schemas.strategy import StrategyConfig
from app.agent.agents.technical_analyst_agent import TechnicalAnalystAgent

_DISPLAY_NAMES: dict[AgentName, str] = {
    AgentName.STRATEGY_BUILDER: "Strategy Building",
    AgentName.STRATEGY_EDITOR: "Strategy Editing",
    AgentName.STRATEGY_EXPLAINER: "Strategy Explanation",
    AgentName.MARKET_RESEARCH: "Market Research",
    AgentName.TECHNICAL_ANALYST: "Technical Analysis",
    AgentName.FUNDAMENTAL_ANALYST: "Fundamental Analysis",
    AgentName.PORTFOLIO_ANALYST: "Portfolio Analysis",
    AgentName.PERFORMANCE_ANALYST: "Performance Analysis",
    AgentName.RISK_ADVISOR: "Risk Advisory",
    AgentName.INVESTMENT_ANALYST: "Investment Analysis",
}


@dataclass(frozen=True)
class PipelineResult:
    context: GroundedContext
    plan: ConversationExecutionPlan
    memory: ConversationMemory
    state: ConversationState | None


class ConversationPipeline:
    def __init__(
        self,
        goal_extractor: GoalExtractor,
        asset_directory,
        strategy_builder_agent: StrategyBuilderAgent,
        market_research_agent: MarketResearchAgent | None = None,
        technical_analyst_agent: TechnicalAnalystAgent | None = None,
    ) -> None:
        self._goal_extractor = goal_extractor
        self._asset_directory = asset_directory
        self._strategy_builder_agent = strategy_builder_agent
        self._market_research_agent = market_research_agent
        self._technical_analyst_agent = technical_analyst_agent

    def handle_turn(
        self,
        user_message: str,
        conversation_history: list[dict],
        draft: StrategyConfig | None,
        memory: ConversationMemory,
        state: ConversationState | None,
        turn: int,
    ) -> PipelineResult:
        extracted = self._goal_extractor.extract(user_message, conversation_history, memory)
        context = ground(extracted, user_message, memory, self._asset_directory)

        memory = apply_goal_update(
            memory,
            goal_relation=context.goal_relation.value if context.goal_relation else None,
            goal_summary=context.goal_summary,
            turn=turn,
        )

        plan = build_execution_plan(context)
        new_state = state
        finalized_steps: list[ConversationExecutionStep] = []

        for planned_step in plan.steps:
            if planned_step.agent == AgentName.STRATEGY_BUILDER:
                results, new_state, _raw = self._strategy_builder_agent.execute(
                    user_message, conversation_history, draft, state
                )
                finalized_steps.append(ConversationExecutionStep(
                    agent=planned_step.agent, status=ConversationStepStatus.EXECUTED, results=results,
                ))
            elif planned_step.agent == AgentName.MARKET_RESEARCH and self._market_research_agent is not None:
                results = self._market_research_agent.execute(context)
                finalized_steps.append(ConversationExecutionStep(
                    agent=planned_step.agent, status=ConversationStepStatus.EXECUTED, results=results,
                ))
            elif planned_step.agent == AgentName.TECHNICAL_ANALYST and self._technical_analyst_agent is not None:
                results = self._technical_analyst_agent.execute(context)
                finalized_steps.append(ConversationExecutionStep(
                    agent=planned_step.agent, status=ConversationStepStatus.EXECUTED, results=results,
                ))
            else:
                # Every other Agent doesn't exist yet -- an honest,
                # explicit "not implemented" beats a wrong answer or a
                # silent fallback to StrategyBuilder.
                display = _DISPLAY_NAMES.get(planned_step.agent, planned_step.agent.value)
                finalized_steps.append(ConversationExecutionStep(
                    agent=planned_step.agent, status=ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED,
                    reason=f"I understood this as a {display} request, but that Agent hasn't been implemented yet.",
                ))

        final_plan = ConversationExecutionPlan(steps=finalized_steps)
        memory = apply_execution_update(memory, final_plan.executed_results, turn=turn)

        return PipelineResult(context=context, plan=final_plan, memory=memory, state=new_state)