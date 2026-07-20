"""Unit tests for FileConversationStore, using pytest's tmp_path
fixture so nothing touches the real conversations/ directory."""

import pytest

from app.agent.conversation_store import ConversationSession
from app.agent.file_conversation_store import FileConversationStore
from app.schemas.strategy import (
    AssetRule,
    CapitalAllocation,
    ConditionGroup,
    ExitRules,
    PortfolioRules,
    RuleCondition,
    StrategyConfig,
)


def _sample_draft() -> StrategyConfig:
    return StrategyConfig(
        portfolio_rules=PortfolioRules(),
        asset_rules=[
            AssetRule(
                symbol="AAPL",
                buy_conditions=ConditionGroup(
                    operator="AND",
                    rules=[RuleCondition(indicator="PRICE", period=1, operator="less_than", value=180)],
                ),
                sell_conditions=ConditionGroup(operator="AND", rules=[]),
                capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10),
                exit=ExitRules(),
            )
        ],
    )


def test_get_returns_none_for_unknown_conversation(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    assert store.get("nonexistent") is None


def test_save_then_get_returns_same_session(tmp_path):
    store = FileConversationStore(directory=tmp_path)
    session = ConversationSession(
        messages=[
            {"role": "user", "content": "Buy Apple below $180"},
            {"role": "assistant", "content": "Got it."},
        ],
        draft=_sample_draft(),
    )

    store.save("conv-1", session)
    result = store.get("conv-1")

    assert result is not None
    assert result.messages == session.messages
    assert result.draft is not None
    assert result.draft.asset_rules[0].symbol == "AAPL"


def test_session_with_no_draft_round_trips_as_none(tmp_path):
    store = FileConversationStore(directory=tmp_path)
    session = ConversationSession(messages=[{"role": "user", "content": "hi"}], draft=None)

    store.save("conv-1", session)
    result = store.get("conv-1")

    assert result is not None
    assert result.draft is None


def test_save_overwrites_previous_session(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    store.save("conv-1", ConversationSession(messages=[{"role": "user", "content": "first"}]))
    store.save("conv-1", ConversationSession(messages=[{"role": "user", "content": "second"}]))

    result = store.get("conv-1")

    assert result is not None
    assert result.messages == [{"role": "user", "content": "second"}]


def test_multiple_conversations_are_independent(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    store.save("conv-1", ConversationSession(messages=[{"role": "user", "content": "one"}]))
    store.save("conv-2", ConversationSession(messages=[{"role": "user", "content": "two"}]))

    result1 = store.get("conv-1")
    result2 = store.get("conv-2")

    assert result1 is not None and result1.messages == [{"role": "user", "content": "one"}]
    assert result2 is not None and result2.messages == [{"role": "user", "content": "two"}]


def test_directory_is_created_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist" / "yet"

    store = FileConversationStore(directory=nested)
    store.save("conv-1", ConversationSession(messages=[{"role": "user", "content": "hi"}]))

    assert nested.exists()
    result = store.get("conv-1")
    assert result is not None
    assert result.messages == [{"role": "user", "content": "hi"}]


@pytest.mark.parametrize("bad_id", ["../escape", "a/b", "a\\b", "a.b", "", "a b"])
def test_unsafe_conversation_id_is_rejected(tmp_path, bad_id):
    store = FileConversationStore(directory=tmp_path)

    with pytest.raises(ValueError):
        store.save(bad_id, ConversationSession(messages=[{"role": "user", "content": "test"}]))


def test_safe_conversation_id_with_hyphens_and_underscores_is_accepted(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    store.save("user_123-session-abc", ConversationSession(messages=[{"role": "user", "content": "hi"}]))

    result = store.get("user_123-session-abc")
    assert result is not None
    assert result.messages == [{"role": "user", "content": "hi"}]