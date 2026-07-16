# Architecture

Documents the system architecture for CapitalForge.

## Current state (Milestone 1: Create a Strategy)

Implemented: Strategy and StrategyVersion models, versioning logic in
strategy_service.py, and a minimal FastAPI layer (create strategy,
retrieve strategy, create new version). No trading engine, no broker
integration, no agent/LLM features, no worker, no frontend yet.

See docs/decisions.md for the reasoning behind specific technical choices
made in this milestone.

## Planned direction

- Deterministic trading engine (indicators, rule evaluation, risk
  management, signal generation) — trading_engine/
- Execution and market data via Alpaca Paper Trading — trading_engine/execution/,
  trading_engine/market_data/
- LLM-assisted strategy drafting and post-trade explanations — agent/
- Scheduled background evaluation loop — workers/
- Robinhood MCP as a future broker adapter, after Alpaca-based paper
  trading has proven itself