"""Unit tests for ground() -- the deterministic entity resolution and
RESEARCH/EVALUATE tie-break. Uses a duck-typed fake AssetDirectory,
same convention as elsewhere in this suite (real AssetDirectory
requires live Alpaca credentials/cache)."""

from app.agent.conversation_memory import ConversationGoal, ConversationMemory
from app.agent.pipeline.grounding import ground
from app.agent.pipeline.types import AmbiguityReason, ExtractedGoal, GoalExtractionIntent
from app.assets.asset_directory import AssetEntry, AssetSearchResult


class FakeAssetDirectory:
    def __init__(self, results_by_query: dict[str, list[AssetSearchResult]]) -> None:
        self._results_by_query = results_by_query

    def search_scored(self, query: str, limit: int = 10) -> list[AssetSearchResult]:
        return self._results_by_query.get(query, [])[:limit]


def _result(symbol: str, name: str, score: float) -> AssetSearchResult:
    return AssetSearchResult(entry=AssetEntry(symbol=symbol, name=name), score=score)


def test_single_clean_match_resolves():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nvidia"])
    directory = FakeAssetDirectory({"Nvidia": [_result("NVDA", "NVIDIA Corporation", 95.0)]})
    context = ground(extracted, "what's Nvidia doing", ConversationMemory(), directory)

    assert len(context.resolved_entities) == 1
    assert context.resolved_entities[0].entity.value == "NVDA"
    assert not context.ambiguous_entities


def test_close_scores_within_threshold_are_ambiguous():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Alphabet"])
    directory = FakeAssetDirectory({"Alphabet": [
        _result("GOOGL", "Alphabet Inc. Class A", 74.0),
        _result("GOOG", "Alphabet Inc. Class C", 73.0),
    ]})
    context = ground(extracted, "what's Alphabet doing", ConversationMemory(), directory)

    assert not context.resolved_entities
    assert len(context.ambiguous_entities) == 1
    assert context.ambiguous_entities[0].reason == AmbiguityReason.MULTIPLE_CLOSE_MATCHES
    assert set(context.ambiguous_entities[0].candidates) == {"GOOGL", "GOOG"}
    assert "1.4%" in context.ambiguous_entities[0].explanation or "gap" in context.ambiguous_entities[0].explanation


def test_wide_gap_resolves_cleanly_not_ambiguous():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Apple"])
    directory = FakeAssetDirectory({"Apple": [
        _result("AAPL", "Apple Inc.", 95.0),
        _result("APLE", "Apple Hospitality REIT", 77.0),
    ]})
    context = ground(extracted, "what's Apple doing", ConversationMemory(), directory)

    assert len(context.resolved_entities) == 1
    assert context.resolved_entities[0].entity.value == "AAPL"


def test_no_matches_is_unresolved_not_ambiguous():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nonexistent Corp"])
    directory = FakeAssetDirectory({})
    context = ground(extracted, "what about Nonexistent Corp", ConversationMemory(), directory)

    assert len(context.unresolved_entities) == 1
    assert context.unresolved_entities[0].reason == AmbiguityReason.NO_MATCH


def test_evaluate_without_evaluative_language_downgrades_to_research():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.EVALUATE, mentioned_entities=["Tesla"])
    directory = FakeAssetDirectory({"Tesla": [_result("TSLA", "Tesla, Inc.", 90.0)]})
    context = ground(extracted, "Tesla's been dropping a lot lately", ConversationMemory(), directory)

    assert context.intent == GoalExtractionIntent.RESEARCH


def test_evaluate_with_evaluative_language_stays_evaluate():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.EVALUATE, mentioned_entities=["Tesla"])
    directory = FakeAssetDirectory({"Tesla": [_result("TSLA", "Tesla, Inc.", 90.0)]})
    context = ground(extracted, "should I buy Tesla?", ConversationMemory(), directory)

    assert context.intent == GoalExtractionIntent.EVALUATE


def test_continue_with_no_active_goal_is_flagged():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.CONTINUE)
    context = ground(extracted, "continue", ConversationMemory(), FakeAssetDirectory({}))

    assert context.continue_with_nothing_active is True


def test_continue_with_active_goal_is_not_flagged():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.CONTINUE)
    memory = ConversationMemory(active_goal=ConversationGoal(summary="dividend portfolio", established_at_turn=1))
    context = ground(extracted, "continue", memory, FakeAssetDirectory({}))

    assert context.continue_with_nothing_active is False


def test_invalid_candidate_agent_from_llm_is_dropped_not_guessed():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.BUILD, candidate_agents=["strategy_builder", "made_up_agent"])
    context = ground(extracted, "buy AAPL below 180", ConversationMemory(), FakeAssetDirectory({}))

    assert len(context.confirmed_agents) == 1
    assert context.confirmed_agents[0].value == "strategy_builder"
    
def test_no_explicit_entity_falls_back_to_primary_focus():
    from app.agent.conversation_memory import EntityReference

    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=[])
    memory = ConversationMemory(
        primary_focus=EntityReference(kind="symbol", value="NVDA", display_name="NVIDIA Corporation (NVDA)")
    )
    context = ground(extracted, "what about its 52-week low", memory, FakeAssetDirectory({}))

    assert len(context.resolved_entities) == 1
    assert context.resolved_entities[0].entity.value == "NVDA"
    assert context.resolved_concepts == []


def test_learn_intent_with_no_entity_falls_back_to_recent_concept_not_primary_focus():
    from app.agent.conversation_memory import ConceptReference, EntityReference

    extracted = ExtractedGoal(intent=GoalExtractionIntent.LEARN, mentioned_entities=[])
    memory = ConversationMemory(
        primary_focus=EntityReference(kind="symbol", value="NVDA", display_name="NVIDIA Corporation (NVDA)"),
        recent_concepts=[ConceptReference(name="RSI", introduced_by="technical_analyst")],
    )
    context = ground(extracted, "what does that mean", memory, FakeAssetDirectory({}))

    assert not context.resolved_entities
    assert len(context.resolved_concepts) == 1
    assert context.resolved_concepts[0].name == "RSI"
    
def test_concept_mention_resolves_as_concept_not_attempted_as_asset():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["RSI"])
    context = ground(extracted, "what's the RSI", ConversationMemory(), FakeAssetDirectory({}))

    assert len(context.resolved_concepts) == 1
    assert context.resolved_concepts[0].name == "RSI"
    assert not context.resolved_entities
    assert not context.unresolved_entities


def test_asset_and_concept_mentioned_together_resolve_independently():
    extracted = ExtractedGoal(intent=GoalExtractionIntent.RESEARCH, mentioned_entities=["Nvidia", "RSI"])
    directory = FakeAssetDirectory({"Nvidia": [_result("NVDA", "NVIDIA Corporation", 95.0)]})
    context = ground(extracted, "what's Nvidia's RSI", ConversationMemory(), directory)

    assert len(context.resolved_entities) == 1
    assert context.resolved_entities[0].entity.value == "NVDA"
    assert len(context.resolved_concepts) == 1
    assert context.resolved_concepts[0].name == "RSI"