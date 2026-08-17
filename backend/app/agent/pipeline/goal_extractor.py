"""GoalExtractor: the one LLM call that classifies what the user is
trying to accomplish. Deliberately separate from TranslationService's
own LLM call (which converts a BUILD/EDIT request into structured
trading operations) -- these solve different problems, and combining
them risks the translation prompt slowly becoming a catch-all over
time. This call runs first, always; TranslationService's LLM call
only runs afterward, and only for turns Grounding actually routes to
StrategyBuilderAgent.

Intentionally lightweight, per docs/conversation_principles.md: this
prompt classifies intent, proposes a goal-relation judgment, and lists
raw entity mentions. It never decides ambiguity, confidence, or final
routing -- Grounding does that deterministically.
"""

from app.agent.conversation_memory import ConversationMemory
from app.agent.llm_service import LLMService
from app.agent.pipeline.types import ExtractedGoal

_SYSTEM_PROMPT = """You classify what the user is trying to accomplish \
in a conversation with a trading agent. You do NOT decide ambiguity, \
confidence, or exact routing -- a separate deterministic step handles \
that. Your only job:

1. Classify intent as exactly one of: learn, research, decide, build, \
edit, explain, review, evaluate, continue.
   - learn: asking what a concept means ("what does RSI mean?")
   - research: asking about a company/asset's current facts without \
asking for an opinion
   - decide: doesn't clearly fit another category yet
   - build: creating a new trading rule
   - edit: modifying an existing rule
   - explain: asking why a past rule/edit/decision was made
   - review: asking about past trades, rejections, or performance
   - evaluate: explicitly asking for an opinion, recommendation, \
ranking, or comparison ("should I buy X", "which is stronger", \
"recommend three stocks")
   - continue: resuming a prior topic without restating it \
("continue", "go back to that", "where were we")

2. If this turn changes the conversation's overarching goal, set \
goal_relation to one of: new, continuation, subtask, \
abandon_and_replace, and goal_summary to a short description. If \
nothing about the goal changed this turn, set goal_relation to \
"none" and leave goal_summary null.

3. List any company names, tickers, or concepts mentioned, EXACTLY as \
the user wrote them. Do not correct spelling or resolve them.

4. Pick candidate_agents from: strategy_builder, strategy_editor, \
strategy_explainer, market_research, technical_analyst, \
fundamental_analyst, portfolio_analyst, performance_analyst, \
risk_advisor, investment_analyst, educator. This is only a best guess \
-- a separate step will correct it -- but pick every genuinely relevant \
agent for the turn, not just one, matching these worked examples:

- "What does RSI mean?" -> intent=learn, candidate_agents=[educator]
- "What's AAPL's RSI?" -> intent=research, \
candidate_agents=[technical_analyst]
- "What's AAPL trading at?" -> intent=research, \
candidate_agents=[market_research]
- "What's AAPL's P/E ratio?" -> intent=research, \
candidate_agents=[fundamental_analyst]
- "Should I buy AAPL?" -> intent=evaluate, candidate_agents=\
[investment_analyst, technical_analyst, risk_advisor, \
fundamental_analyst, market_research] -- ALWAYS include the specialist \
agents alongside investment_analyst on an evaluate turn. \
investment_analyst only synthesizes what other agents find THIS SAME \
TURN; naming it alone gives it nothing to work with.
- "Why did you set that stop loss at 5%?" -> intent=explain, \
candidate_agents=[strategy_explainer]
- "How's my strategy doing?" / "how's my portfolio?" -> intent=review, \
candidate_agents=[portfolio_analyst]
- "How risky is my portfolio?" -> intent=review, \
candidate_agents=[risk_advisor]
- "How has my strategy performed?" / "what's my return?" -> \
intent=review, candidate_agents=[performance_analyst]
- "Buy Apple below $180" -> intent=build, \
candidate_agents=[strategy_builder]
- "Change that to $170" / "make it 8%" -> intent=edit, \
candidate_agents=[strategy_editor]

Never decide whether something is ambiguous. Never decide confidence. \
Never resolve an entity to a specific ticker.

When in doubt about which agents are relevant, include more rather \
than fewer. A wrongly-included agent just reports it found nothing \
relevant -- an honest, harmless outcome. A wrongly-omitted agent \
silently loses real capability the user asked for, which is worse. \
Questions about a user's watchlist or what they've added to their \
portfolio ("what's on my watchlist", "what have I added") also route \
to candidate_agents=[portfolio_analyst], same as questions about an \
active strategy.

"""


_MAX_HISTORY_MESSAGES = 6


def _render_memory_context(memory: ConversationMemory) -> str:
    parts = []
    if memory.active_goal:
        parts.append(f"Current overarching goal: {memory.active_goal.summary}")
    if memory.primary_focus:
        parts.append(f"Currently discussing: {memory.primary_focus.display_name}")
    if memory.comparison_focus:
        parts.append(f"Also being compared: {memory.comparison_focus.display_name}")
    if memory.recent_concepts:
        parts.append(f"Recently discussed concepts: {', '.join(c.name for c in memory.recent_concepts)}")
    return "\n".join(parts) if parts else "Nothing established in this conversation yet."


class GoalExtractor:
    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    def extract(
        self, user_message: str, conversation_history: list[dict], memory: ConversationMemory
    ) -> ExtractedGoal:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "system", "content": _render_memory_context(memory)},
            *conversation_history[-_MAX_HISTORY_MESSAGES:],
            {"role": "user", "content": user_message},
        ]
        return self._llm.generate_structured(messages, ExtractedGoal, schema_name="ExtractedGoal")