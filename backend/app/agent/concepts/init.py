"""ConceptDirectory: deterministic lookup for trading/analysis
concepts and named indicators. Same discipline as AssetDirectory --
no fuzzy AI, no heuristics, an explicit table anyone can extend. One
shared vocabulary for Grounding, reused by TechnicalAnalystAgent and,
later, EducatorAgent -- rather than each maintaining its own keyword
list.
""" 