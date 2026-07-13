"""Agent module: understand, clarify, translate, validate, explain.
Never executes trades directly — writes to a Strategy only while it's
in draft state, via the existing strategy_service, unchanged.
"""