"""Unit tests for AssetDirectory's matching — the first real, direct
test coverage of search()/search_scored() rather than only exercising
it indirectly through a duck-typed fake elsewhere. Covers both the
pre-existing scoring behavior (must stay unchanged) and the specific
failures found during the real investigation in decisions.md."""

from app.assets.asset_directory import AssetDirectory, AssetEntry


def _directory_with(entries: list[AssetEntry]) -> AssetDirectory:
    directory = AssetDirectory(api_key="unused", secret_key="unused")
    directory._entries = entries  # bypass live Alpaca/cache entirely for tests
    return directory


_ENTRIES = [
    AssetEntry("AAPL", "Apple Inc."),
    AssetEntry("APLE", "Apple Hospitality REIT, Inc."),
    AssetEntry("GOOGL", "Alphabet Inc. Class A Common Stock"),
    AssetEntry("GOOG", "Alphabet Inc. Class C Capital Stock"),
    AssetEntry("META", "Meta Platforms, Inc. Class A Common Stock"),
    AssetEntry("TSLA", "Tesla, Inc. Common Stock"),
    AssetEntry("BRK.A", "Berkshire Hathaway Inc. Common Stock Class A"),
    AssetEntry("BRK.B", "Berkshire Hathaway Inc. Common Stock Class B"),
    AssetEntry("KO", "Coca-Cola Company (The) Common Stock"),
    AssetEntry("COKE", "Coca-Cola Consolidated, Inc. Common Stock"),
]


def test_previously_zero_match_queries_now_resolve():
    directory = _directory_with(_ENTRIES)
    assert directory.search("Google")[0].symbol == "GOOGL"
    assert directory.search("Facebook")[0].symbol == "META"
    assert directory.search("Coca Cola")[0].symbol in ("KO", "COKE")
    assert directory.search("Tesla Inc")[0].symbol == "TSLA"


def test_character_level_typos_remain_a_known_unaddressed_gap():
    """Normalization (punctuation/hyphens/commas) and the alias table
    (deterministic renames) are what this step actually fixed --
    neither helps with a genuine missing-letter typo like "aple" for
    "Apple", since that requires real edit-distance/fuzzy matching,
    which was explicitly out of scope here ("not fuzzy AI, not
    heuristics -- deterministic aliases only"). This test documents
    that the gap is real and still open, rather than silently
    disappearing: "aple" still confidently resolves to the WRONG
    company (Apple Hospitality REIT, whose actual ticker happens to be
    APLE) with no competing candidate and no ambiguity signal at all.
    A future, deliberately-scoped pass on typo tolerance is needed to
    close this -- not a side effect of this step.
    """
    directory = _directory_with(_ENTRIES)
    results = directory.search_scored("aple")
    symbols = [r.entry.symbol for r in results]
    assert symbols == ["APLE"]
    assert "AAPL" not in symbols


def test_exact_symbol_query_still_scores_highest_for_itself():
    directory = _directory_with(_ENTRIES)
    results = directory.search_scored("AAPL")
    assert results[0].entry.symbol == "AAPL"


def test_share_class_ambiguity_still_produces_a_near_tie():
    directory = _directory_with(_ENTRIES)
    results = directory.search_scored("Berkshire")
    top_two = sorted((r.score for r in results), reverse=True)[:2]
    assert abs(top_two[0] - top_two[1]) < 1.0  # still an effective tie, not resolved away


def test_alphabet_share_classes_still_score_close_not_identical():
    directory = _directory_with(_ENTRIES)
    results = directory.search_scored("Alphabet")
    scores = sorted((r.score for r in results), reverse=True)[:2]
    gap_pct = (scores[0] - scores[1]) / scores[0]
    assert gap_pct < 0.05  # still within the ambiguity threshold


def test_clear_winner_queries_still_have_a_wide_gap():
    directory = _directory_with(_ENTRIES)
    results = directory.search_scored("Apple")
    scores = sorted((r.score for r in results), reverse=True)
    gap_pct = (scores[0] - scores[1]) / scores[0]
    assert gap_pct > 0.10  # clear winner, well above the ambiguity threshold


def test_alias_does_not_suppress_a_genuine_literal_match():
    entries = [*_ENTRIES, AssetEntry("FB", "Some Unrelated Fictional Ticker Fund")]
    directory = _directory_with(entries)
    results = directory.search_scored("FB")
    symbols = [r.entry.symbol for r in results]
    assert "FB" in symbols
    assert "META" in symbols  # alias adds META alongside, doesn't replace the literal match


def test_no_match_returns_empty_not_an_error():
    directory = _directory_with(_ENTRIES)
    assert directory.search("Nonexistent Company Xyz") == []