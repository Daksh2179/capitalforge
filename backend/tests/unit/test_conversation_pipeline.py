"""Unit tests for ConversationPipeline -- the full turn lifecycle,
exercised end-to-end against fakes. Confirms: STRATEGY_BUILDER executes
for real, every other confirmed Agent produces the explicit
"identified but not implemented" wording rather than a silent
fallback or a fabricated answer, and Memory only ever reflects real
executions."""

from app.agent.agent_contracts import AgentName
from app.agent.agents.strategy_builder_agent import StrategyBuilderAgent
from app.agent.conversation_memory import ConversationMemory
from app.agent.llm_service import LLMService
from app.agent.pipeline.conversation_pipeline import ConversationPipeline
from app.agent.pipeline.goal_extractor import GoalExtractor
from app.agent.pipeline.types import ConversationStepStatus, DetailLevel, ExtractedGoal, GoalExtractionIntent
from app.agent.translation.parsed_intent import IntentBatch, ParsedIntent
from app.agent.translation.translation_service import TranslationService
from app.assets.asset_directory import AssetEntry, AssetSearchResult
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeGoalExtractionLLM(LLMService):
    def __init__(self, goal: ExtractedGoal) -> None:
        self._goal = goal

    def generate_structured(self, messages, response_model, schema_name):
        return self._goal

    def generate_text(self, messages):
        raise NotImplementedError


class FakeTranslationLLM(LLMService):
    def __init__(self, batch: IntentBatch) -> None:
        self._batch = batch

    def generate_structured(self, messages, response_model, schema_name):
        return self._batch

    def generate_text(self, messages):
        raise NotImplementedError


class FakeMarketDataProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, timeframe, start, end):
        return []


class FakeAssetDirectory:
    def search_scored(self, query, limit=10):
        return [AssetSearchResult(entry=AssetEntry(symbol=query.upper(), name=query), score=95.0)]
    
    def search(self, query, limit=10):
        return [result.entry for result in self.search_scored(query, limit)]


def _pipeline(goal: ExtractedGoal, batch: IntentBatch) -> ConversationPipeline:
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    translation_service = TranslationService(FakeTranslationLLM(batch), FakeMarketDataProvider(), FakeAssetDirectory())
    strategy_builder = StrategyBuilderAgent(translation_service)
    return ConversationPipeline(goal_extractor, FakeAssetDirectory(), strategy_builder)


def test_build_turn_executes_strategy_builder_for_real():
    goal = ExtractedGoal(intent=GoalExtractionIntent.BUILD, candidate_agents=["strategy_builder"])
    batch = IntentBatch(intents=[
        ParsedIntent(operation="set_buy_condition", intent_type="objective", symbol="AAPL",
                     indicator="PRICE", period=1, operator="less_than", value=180, raw_text="Buy Apple below $180")
    ])
    result = _pipeline(goal, batch).handle_turn("Buy Apple below $180", [], None, ConversationMemory(), None, turn=1)

    assert len(result.plan.steps) == 1
    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert result.plan.steps[0].agent == AgentName.STRATEGY_BUILDER
    assert len(result.memory.recent_events) == 1


def test_unimplemented_agent_produces_explicit_not_implemented_step():
    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, candidate_agents=["market_research"])
    result = _pipeline(goal, IntentBatch(intents=[])).handle_turn(
        "what's Nvidia doing", [], None, ConversationMemory(), None, turn=1
    )

    assert len(result.plan.steps) == 1
    step = result.plan.steps[0]
    assert step.status == ConversationStepStatus.SKIPPED_NOT_IMPLEMENTED
    assert step.agent == AgentName.MARKET_RESEARCH
    assert "Market Research" in step.reason
    assert "hasn't been implemented" in step.reason


def test_unimplemented_agent_never_pollutes_memory():
    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, candidate_agents=["market_research"])
    result = _pipeline(goal, IntentBatch(intents=[])).handle_turn(
        "what's Nvidia doing", [], None, ConversationMemory(), None, turn=1
    )

    # No real Agent executed, so nothing should be recorded as having
    # happened -- Memory only ever reflects real executions.
    assert len(result.memory.recent_events) == 0
    
def test_market_research_agent_executes_for_real_when_provided():
    from app.agent.agents.market_research_agent import MarketResearchAgent
    from app.trading_engine.domain.market_bar import MarketBar
    from app.trading_engine.market_data.provider import MarketDataProvider
    from datetime import datetime, timedelta, timezone

    class FakeRealMarketDataProvider(MarketDataProvider):
        def get_historical_bars(self, symbol, timeframe, start, end):
            base = datetime.now(timezone.utc) - timedelta(days=30)
            return [
                MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                          open=100.0, high=105.0, low=95.0, close=100.0 + i, volume=100_000.0)
                for i in range(30)
            ]

    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nvidia"],
                          candidate_agents=["market_research"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    market_research_agent = MarketResearchAgent(FakeRealMarketDataProvider())
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, market_research_agent)
    result = pipeline.handle_turn("what's Nvidia doing", [], None, ConversationMemory(), None, turn=1)

    assert len(result.plan.steps) == 1
    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert result.plan.steps[0].agent == AgentName.MARKET_RESEARCH
    assert "NVIDIA" in result.plan.steps[0].results[0].facts[0]
    assert len(result.memory.recent_events) == 1
    
def test_technical_analyst_agent_executes_for_real_when_provided():
    from app.agent.agents.technical_analyst_agent import TechnicalAnalystAgent
    from app.trading_engine.domain.market_bar import MarketBar
    from app.trading_engine.market_data.provider import MarketDataProvider
    from datetime import datetime, timedelta, timezone

    class FakeIndicatorMarketDataProvider(MarketDataProvider):
        def get_historical_bars(self, symbol, timeframe, start, end):
            base = datetime.now(timezone.utc) - timedelta(days=30)
            return [
                MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                          open=130.0 - i, high=130.0 - i, low=130.0 - i, close=130.0 - i, volume=100_000.0)
                for i in range(30)
            ]

    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nvidia", "RSI"],
                          candidate_agents=["technical_analyst"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    technical_analyst_agent = TechnicalAnalystAgent(FakeIndicatorMarketDataProvider())
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(
        goal_extractor, directory, strategy_builder, technical_analyst_agent=technical_analyst_agent,
    )
    result = pipeline.handle_turn("what's Nvidia's RSI", [], None, ConversationMemory(), None, turn=1)

    assert len(result.plan.steps) == 1
    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert result.plan.steps[0].agent == AgentName.TECHNICAL_ANALYST
    assert "RSI" in result.plan.steps[0].results[0].facts[0]
    
def test_pipeline_result_carries_a_composed_response():
    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nvidia"],
                          candidate_agents=["market_research"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()

    from app.agent.agents.market_research_agent import MarketResearchAgent
    from app.trading_engine.domain.market_bar import MarketBar
    from app.trading_engine.market_data.provider import MarketDataProvider
    from datetime import datetime, timedelta, timezone

    class FakeRealMarketDataProvider(MarketDataProvider):
        def get_historical_bars(self, symbol, timeframe, start, end):
            base = datetime.now(timezone.utc) - timedelta(days=30)
            return [
                MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                          open=100.0, high=105.0, low=95.0, close=100.0 + i, volume=100_000.0)
                for i in range(30)
            ]

    market_research_agent = MarketResearchAgent(FakeRealMarketDataProvider())
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, market_research_agent=market_research_agent)
    result = pipeline.handle_turn("what's Nvidia doing", [], None, ConversationMemory(), None, turn=1)

    assert result.response.text != ""
    assert "NVIDIA" in result.response.text


def test_composed_response_reflects_detail_level_from_grounding():
    goal = ExtractedGoal(intent=GoalExtractionIntent.CONTINUE, mentioned_entities=[])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder)
    result = pipeline.handle_turn("explain more", [], None, ConversationMemory(), None, turn=1)

    assert result.context.detail_level == DetailLevel.EXPANDED
    
def test_educator_agent_executes_for_real_when_provided():
    from app.agent.agents.educator_agent import EducatorAgent

    goal = ExtractedGoal(intent=GoalExtractionIntent.LEARN, mentioned_entities=["RSI"],
                          candidate_agents=["educator"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    educator_agent = EducatorAgent()
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, educator_agent=educator_agent)
    result = pipeline.handle_turn("what does RSI mean?", [], None, ConversationMemory(), None, turn=1)

    assert len(result.plan.steps) == 1
    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert result.plan.steps[0].agent == AgentName.EDUCATOR
    assert "Relative Strength Index" in result.response.text
    assert result.memory.recent_concepts[0].name == "RSI"
    
def test_strategy_editor_routes_to_the_same_strategy_builder_agent():
    goal = ExtractedGoal(intent=GoalExtractionIntent.EDIT, candidate_agents=["strategy_editor"])
    batch = IntentBatch(intents=[
        ParsedIntent(operation="set_stop_loss", intent_type="objective", symbol="AAPL", value=8, raw_text="change stop loss to 8%")
    ])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    translation_service = TranslationService(FakeTranslationLLM(batch), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder)
    result = pipeline.handle_turn("change stop loss to 8%", [], None, ConversationMemory(), None, turn=1)

    assert result.plan.steps[0].agent == AgentName.STRATEGY_EDITOR
    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED


def test_strategy_explainer_agent_executes_for_real_when_provided():
    from app.agent.agents.strategy_explainer_agent import StrategyExplainerAgent
    from app.agent.conversation_memory import ConversationEvent, EntityReference
    from datetime import datetime, timezone

    goal = ExtractedGoal(intent=GoalExtractionIntent.EXPLAIN, mentioned_entities=["Nvidia"],
                          candidate_agents=["strategy_explainer"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    strategy_explainer = StrategyExplainerAgent()
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    memory = ConversationMemory(recent_events=[
        ConversationEvent(
            agent="strategy_builder", description="Set NVIDIA buy condition", reasoning=None,
            related_entities=[EntityReference(kind="symbol", value="NVIDIA", display_name="Nvidia (NVIDIA)")],
            timestamp=datetime.now(timezone.utc),
        )
    ])

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, strategy_explainer_agent=strategy_explainer)
    result = pipeline.handle_turn("why did you set that?", [], None, memory, None, turn=1)

    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert "you specified that value directly" in result.response.text
    
def test_portfolio_analyst_agent_executes_for_real_when_provided(db_session):
    from app.agent.agents.portfolio_analyst_agent import PortfolioAnalystAgent
    from app.models.portfolio_snapshot import PortfolioSnapshot
    from app.services import strategy_service
    from datetime import datetime, timezone
    import uuid as uuid_module

    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid_module.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": []},
        source="manual",
    )
    db_session.refresh(strategy)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=5000.0, positions_json={}, total_value=5000.0,
    ))
    db_session.commit()

    goal = ExtractedGoal(intent=GoalExtractionIntent.REVIEW, candidate_agents=["portfolio_analyst"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    portfolio_analyst = PortfolioAnalystAgent(db_session)
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, portfolio_analyst_agent=portfolio_analyst)
    result = pipeline.handle_turn(
        "how's this strategy doing", [], None, ConversationMemory(), None, turn=1, strategy_id=strategy.id,
    )

    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert "5000.00" in result.response.text
    
def test_risk_advisor_agent_executes_for_real_when_provided(db_session):
    from app.agent.agents.risk_advisor_agent import RiskAdvisorAgent
    from app.models.portfolio_snapshot import PortfolioSnapshot
    from app.services import strategy_service
    from datetime import datetime, timezone
    import uuid as uuid_module

    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid_module.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": []},
        source="manual",
    )
    db_session.refresh(strategy)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=3000.0, positions_json={"AAPL": {"quantity": 10, "average_entry_price": 180.0, "current_price": 190.0}},
        total_value=4900.0,
    ))
    db_session.commit()

    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, candidate_agents=["risk_advisor"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    risk_advisor = RiskAdvisorAgent(db_session, FakeMarketDataProvider())
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, risk_advisor_agent=risk_advisor)
    result = pipeline.handle_turn(
        "how risky is my portfolio", [], None, ConversationMemory(), None, turn=1, strategy_id=strategy.id,
    )

    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert "AAPL" in result.response.text
    
def test_fundamental_analyst_agent_executes_for_real_when_provided():
    from app.agent.agents.fundamental_analyst_agent import FundamentalAnalystAgent

    class FakeFinnhubClient:
        def get_profile(self, symbol):
            return {"name": "NVIDIA Corp", "finnhubIndustry": "Semiconductors", "marketCapitalization": 3200000.0}

        def get_metrics(self, symbol):
            return {"metric": {"peBasicExclExtraTTM": 45.2, "dividendYieldIndicatedAnnual": 0.03}}

    goal = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nvidia"],
                          candidate_agents=["fundamental_analyst"])
    goal_extractor = GoalExtractor(FakeGoalExtractionLLM(goal))
    directory = FakeAssetDirectory()
    fundamental_analyst = FundamentalAnalystAgent(FakeFinnhubClient())
    translation_service = TranslationService(FakeTranslationLLM(IntentBatch(intents=[])), FakeMarketDataProvider(), directory)
    strategy_builder = StrategyBuilderAgent(translation_service)

    pipeline = ConversationPipeline(goal_extractor, directory, strategy_builder, fundamental_analyst_agent=fundamental_analyst)
    result = pipeline.handle_turn("what's Nvidia's P/E ratio", [], None, ConversationMemory(), None, turn=1)

    assert len(result.plan.steps) == 1
    assert result.plan.steps[0].status == ConversationStepStatus.EXECUTED
    assert result.plan.steps[0].agent == AgentName.FUNDAMENTAL_ANALYST
    assert "45.2" in result.response.text