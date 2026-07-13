"""Unit tests for FileConversationStore, using pytest's tmp_path
fixture so nothing touches the real conversations/ directory."""

import pytest

from app.agent.file_conversation_store import FileConversationStore


def test_get_returns_none_for_unknown_conversation(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    assert store.get("nonexistent") is None


def test_save_then_get_returns_same_messages(tmp_path):
    store = FileConversationStore(directory=tmp_path)
    messages = [
        {"role": "user", "content": "Buy Apple below $180"},
        {"role": "assistant", "content": "Got it."},
    ]

    store.save("conv-1", messages)
    result = store.get("conv-1")

    assert result == messages


def test_save_overwrites_previous_messages(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    store.save("conv-1", [{"role": "user", "content": "first"}])
    store.save("conv-1", [{"role": "user", "content": "second"}])

    result = store.get("conv-1")

    assert result == [{"role": "user", "content": "second"}]


def test_multiple_conversations_are_independent(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    store.save("conv-1", [{"role": "user", "content": "one"}])
    store.save("conv-2", [{"role": "user", "content": "two"}])

    assert store.get("conv-1") == [{"role": "user", "content": "one"}]
    assert store.get("conv-2") == [{"role": "user", "content": "two"}]


def test_directory_is_created_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist" / "yet"

    store = FileConversationStore(directory=nested)
    store.save("conv-1", [{"role": "user", "content": "hi"}])

    assert nested.exists()
    assert store.get("conv-1") == [{"role": "user", "content": "hi"}]


@pytest.mark.parametrize("bad_id", ["../escape", "a/b", "a\\b", "a.b", "", "a b"])
def test_unsafe_conversation_id_is_rejected(tmp_path, bad_id):
    store = FileConversationStore(directory=tmp_path)

    with pytest.raises(ValueError):
        store.save(bad_id, [{"role": "user", "content": "test"}])


def test_safe_conversation_id_with_hyphens_and_underscores_is_accepted(tmp_path):
    store = FileConversationStore(directory=tmp_path)

    store.save("user_123-session-abc", [{"role": "user", "content": "hi"}])

    assert store.get("user_123-session-abc") == [{"role": "user", "content": "hi"}]