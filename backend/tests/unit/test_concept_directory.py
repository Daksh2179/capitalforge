"""Unit tests for ConceptDirectory."""

from app.agent.concepts.concept_directory import ConceptDirectory


def test_lookup_resolves_canonical_name_case_insensitively():
    entry = ConceptDirectory().lookup("rsi")
    assert entry is not None
    assert entry.canonical_name == "RSI"
    assert entry.category == "indicator"
    assert entry.registry_name == "RSI"


def test_lookup_resolves_alias():
    entry = ConceptDirectory().lookup("relative strength index")
    assert entry.canonical_name == "RSI"


def test_lookup_resolves_generic_moving_average_as_concept_not_indicator():
    entry = ConceptDirectory().lookup("moving average")
    assert entry.canonical_name == "MOVING_AVERAGE"
    assert entry.category == "concept"
    assert entry.registry_name is None


def test_lookup_resolves_generic_technicals_request():
    entry = ConceptDirectory().lookup("technicals")
    assert entry.canonical_name == "TECHNICAL_ANALYSIS"


def test_lookup_returns_none_for_unrelated_text():
    directory = ConceptDirectory()
    assert directory.lookup("Apple") is None
    assert directory.lookup("banana") is None