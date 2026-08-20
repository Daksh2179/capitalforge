"""ConversationPipeline: the orchestrator. Goal Extraction -> Grounding
-> Execution Plan -> execute each planned step -> apply any declared
portfolio mutations -> Memory update -> Response Composer.

Execution is no longer purely sequential. Real Agents make real
network calls (Alpaca, Finnhub, Groq), and running unrelated ones
one-after-another was adding real, needless latency (a single turn
touching MarketResearch + TechnicalAnalyst + FundamentalAnalyst was
paying for three sequential round-trips for no structural reason).

Four phases, in order:
1. STRATEGY_BUILDER/STRATEGY_EDITOR (sequential, mutates draft/state --
   the only step that does).
2. Independent, I/O-bound Agents that never touch the shared database
   Session (MarketResearch, TechnicalAnalyst, Educator,
   StrategyExplainer, FundamentalAnalyst) -- run CONCURRENTLY via a
   thread pool. Real, since a Python thread blocked on network I/O
   releases the GIL; this is a genuine latency win, not a fake one.
3. Agents that DO share the one request-scoped SQLAlchemy Session
   (PortfolioAnalyst, RiskAdvisor, PerformanceAnalyst, BacktestAnalyst)
   -- sequential with each other, deliberately. SQLAlchemy Sessions
   are not thread-safe; running these concurrently would risk real
   data corruption, not just be inelegant.
4. InvestmentAnalyst (if present) -- always last, per planner.py's one
   ordering rule, since it needs every other step's results already
   accumulated.

Output order in the final plan always matches the ORIGINAL planned
order, regardless of which phase or what order things actually
finished executing in -- ResponseComposer's priority logic depends on
that ordering being meaningful, not on wall-clock completion order.

Portfolio mutations: no Agent ever calls portfolio_service directly --
PortfolioAnalystAgent only ever DECLARES a PortfolioChange on its
CapabilityResult. apply_portfolio_changes (injected here, optional,
same additive pattern as every other pipeline capability) is the sole
code path that performs the real mutation, running AFTER every Agent
has finished reasoning but BEFORE compose() renders text and BEFORE
Memory records anything -- so both the response and Memory always
reflect what genuinely happened, never a prediction of what was about
to happen.
"""

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.agents.backtest_analyst_agent import BacktestAnalystAgent
from app.agent.agents.educator_agent import EducatorAgent
from app.agent.agents.fundamental_analyst_agent import FundamentalAnalystAgent
from app.agent.agents.investment_analyst_agent import InvestmentAnalystAgent
from app.agent.agents.market_research_agent import MarketResearchAgent
from app.agent.agents.performance_analyst_agent import PerformanceAnalystAgent
from app.agent.agents.portfolio_analyst_agent import PortfolioAnalystAgent
from app.agent.agents.risk_advisor_agent import RiskAdvisorAgent
from app.agent.agents.strategy_builder_agent import StrategyBuilderAgent
from app.agent.agents.strategy_explainer_agent import StrategyExplainerAgent
from app.agent.agents.technical_analyst_agent import TechnicalAnalystAgent
from app.agent.conversation_memory import ConversationMemory
from app.agent.conversation_state import ConversationState
from app.agent.memory_update_policy import apply_execution_update, apply_goal_update
from app.agent.pipeline.goal_extractor import GoalExtractor
from app.agent.pipeline.grounding import ground
from app.agent.pipeline.planner import build_execution_plan
from app.agent.pipeline.response_composer import ComposedResponse, compose
from app.agent.pipeline.types import (
    AgentExecutionContext,
    ConversationExecutionPlan,
    ConversationExecutionStep,
    ConversationStepStatus,
    GroundedContext,
)
from app.schemas.strategy import StrategyConfig


class _Agent(Protocol):
    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]: ...


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
    AgentName.EDUCATOR: "Educational Explanation",
    AgentName.BACKTEST_ANALYST: "Backtest Analysis",
}

_DB_SHARED_AGENTS = {
    AgentName.PORTFOLIO_ANALYST, AgentName.RISK_ADVISOR,
    AgentName.PERFORMANCE_ANALYST, AgentName.BACKTEST_ANALYST,
}
_SEQUENTIAL_FIRST = {AgentName.STRATEGY_BUILDER, AgentName.STRATEGY_EDITOR}


@dataclass(frozen=True)
class PipelineResult:
    context: GroundedContext
    plan: ConversationExecutionPlan
    memory: ConversationMemory
    state: ConversationState | None
    draft: StrategyConfig | None
    response: ComposedResponse


class ConversationPipeline:
    def __init__(
        self,
        goal_extractor: GoalExtractor,
        asset_directory,
        strategy_builder_agent: StrategyBuilderAgent,
        market_research_agent: MarketResearchAgent | None = None,
        technical_analyst_agent: TechnicalAnalystAgent | None = None,
        educator_agent: EducatorAgent | None = None,
        strategy_explainer_agent: StrategyExplainerAgent | None = None,
        portfolio_analyst_agent: PortfolioAnalystAgent | None = None,
        risk_advisor_agent: RiskAdvisorAgent | None = None,
        fundamental_analyst_agent: FundamentalAnalystAgent | None = None,
        investment_analyst_agent: InvestmentAnalystAgent | None = None,
        performance_analyst_agent: PerformanceAnalystAgent | None = None,
        backtest_analyst_agent: BacktestAnalystAgent | None = None,
        apply_portfolio_changes: Callable[[uuid.UUID | None, list[CapabilityResult]], list[CapabilityResult]] | None = None,
    ) -> None:
        self._goal_extractor = goal_extractor
        self._asset_directory = asset_directory
        self._strategy_builder_agent = strategy_builder_agent
        self._agents: dict[AgentName, _Agent] = {
            k: v for k, v in {
                AgentName.MARKET_RESEARCH: market_research_agent,
                AgentName.TECHNICAL_ANALYST: technical_analyst_agent,
                AgentName.EDUCATOR: educator_agent,
                AgentName.STRATEGY_EXPLAINER: strategy_explainer_agent,
                AgentName.PORTFOLIO_ANALYST: portfolio_analyst_agent,
                AgentName.RISK_ADVISOR: risk_advisor_agent,
                AgentName.FUNDAMENTAL_ANALYST: fundamental_analyst_agent,
                AgentName.PERFORMANCE_ANALYST: performance_analyst_agent,
                AgentName.BACKTEST_ANALYST: backtest_analyst_agent,
            }.items() if v is not None
        }
        self._investment_analyst_agent = investment_analyst_agent
        self._apply_portfolio_changes = apply_portfolio_changes

    def handle_turn(
        self,
        user_message: str,
        conversation_history: list[dict],
        draft: StrategyConfig | None,
        memory: ConversationMemory,
        state: ConversationState | None,
        turn: int,
        strategy_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> PipelineResult:
        extracted = self._goal_extractor.extract(user_message, conversation_history, memory)
        context = ground(extracted, user_message, memory, self._asset_directory)

        memory = apply_goal_update(
            memory,
            goal_relation=context.goal_relation.value if context.goal_relation else None,
            goal_summary=context.goal_summary,
            turn=turn,
        )

        exec_context = AgentExecutionContext(
            grounded_context=context, memory=memory, draft=draft, strategy_id=strategy_id, user_id=user_id,
        )

        plan = build_execution_plan(context)
        new_state = state
        new_draft = draft
        step_output: dict[int, tuple[ConversationStepStatus, list[CapabilityResult] | None]] = {}

        # Phase 1: builder/editor, sequential -- the only step that
        # mutates draft/state.
        for i, planned_step in enumerate(plan.steps):
            if planned_step.agent in _SEQUENTIAL_FIRST:
                builder_results, new_state, raw_translation_result = self._strategy_builder_agent.execute(
                    user_message, conversation_history, draft, state
                )
                new_draft = raw_translation_result.draft
                step_output[i] = (ConversationStepStatus.EXECUTED, builder_results)

        # Phase 2: independent, non-database Agents -- concurrent.
        concurrent_indices = [
            i for i, s in enumerate(plan.steps)
            if s.agent not in _SEQUENTIAL_FIRST and s.agent != AgentName.INVESTMENT_ANALYST
            and s.agent not in _DB_SHARED_AGENTS and s.agent in self._agents
        ]
        if concurrent_indices:
            with ThreadPoolExecutor(max_workers=len(concurrent_indices)) as pool:
                futures = {i: pool.submit(self._agents[plan.steps[i].agent].execute, exec_context) for i in concurrent_indices}
                for i, future in futures.items():
                    step_output[i] = (ConversationStepStatus.EXECUTED, future.result())

        # Phase 3: database-sharing Agents -- sequential with each other.
        for i, planned_step in enumerate(plan.steps):
            if planned_step.agent in _DB_SHARED_AGENTS and planned_step.agent in self._agents:
                step_output[i] = (ConversationStepStatus.EXECUTED, self._agents[planned_step.agent].execute(exec_context))

        # Fill in "not implemented" for anything untouched above.
        for i, planned_step in enumerate(plan.steps):
            if i not in step_output:
                step_output[i] = (ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED, None)

        finalized_steps: list[ConversationExecutionStep] = []
        accumulated_results: list[CapabilityResult] = []
        investment_analyst_index: int | None = None

        for i, planned_step in enumerate(plan.steps):
            if planned_step.agent == AgentName.INVESTMENT_ANALYST:
                investment_analyst_index = i
                continue  # handled in phase 4, after accumulation below
            status, results = step_output[i]
            if status == ConversationStepStatus.EXECUTED and results is not None:
                finalized_steps.append(ConversationExecutionStep(agent=planned_step.agent, status=status, results=results))
                accumulated_results.extend(results)
            else:
                display = _DISPLAY_NAMES.get(planned_step.agent, planned_step.agent.value)
                finalized_steps.append(ConversationExecutionStep(
                    agent=planned_step.agent, status=ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED,
                    reason=f"I understood this as a {display} request, but that Agent hasn't been implemented yet.",
                ))

        # Phase 4: InvestmentAnalyst, if planned -- always last, with
        # everything accumulated above.
        if investment_analyst_index is not None:
            if self._investment_analyst_agent is not None:
                investment_context = AgentExecutionContext(
                    grounded_context=context, memory=memory, draft=draft, strategy_id=strategy_id,
                    user_id=user_id, prior_results=accumulated_results,
                )
                investment_results = self._investment_analyst_agent.execute(investment_context)
                finalized_steps.append(ConversationExecutionStep(
                    agent=AgentName.INVESTMENT_ANALYST, status=ConversationStepStatus.EXECUTED, results=investment_results,
                ))
                accumulated_results.extend(investment_results)
            else:
                display = _DISPLAY_NAMES.get(AgentName.INVESTMENT_ANALYST, AgentName.INVESTMENT_ANALYST.value)
                finalized_steps.append(ConversationExecutionStep(
                    agent=AgentName.INVESTMENT_ANALYST, status=ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED,
                    reason=f"I understood this as a {display} request, but that Agent hasn't been implemented yet.",
                ))

        final_plan = ConversationExecutionPlan(steps=finalized_steps)

        # Apply any declared portfolio mutations -- the ONLY place any
        # Agent's declared PortfolioChange actually becomes real, and
        # only right before composing/recording, so both reflect truth.
        if self._apply_portfolio_changes is not None:
            final_plan = ConversationExecutionPlan(steps=[
                ConversationExecutionStep(
                    agent=step.agent, status=step.status, reason=step.reason,
                    results=self._apply_portfolio_changes(user_id, step.results),
                )
                for step in final_plan.steps
            ])

        memory = apply_execution_update(memory, final_plan.executed_results, turn=turn)
        response = compose(final_plan, context.detail_level)

        return PipelineResult(
            context=context, plan=final_plan, memory=memory, state=new_state, draft=new_draft, response=response,
        )