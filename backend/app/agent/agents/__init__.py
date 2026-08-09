"""Agent implementations. StrategyBuilderAgent is the first; each
later Agent (TechnicalAnalystAgent, PortfolioAnalystAgent, etc.)
follows the same shape: wrap an existing domain service unchanged,
translate its native result into list[CapabilityResult].
"""