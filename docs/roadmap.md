- Milestone 2: Market data layer — COMPLETE. MarketBar, Timeframe,
  MarketDataProvider interface, AlpacaMarketData implementation,
  integration tests against the real Alpaca paper API.
- Milestone 3: Indicators — RSI, SMA, EMA as pure functions over
  list[MarketBar], IndicatorResult domain type, unit tests per
  indicator. No knowledge of Alpaca or any data source. NEXT.
- Milestone 3: Indicators — COMPLETE. calculate_sma, calculate_ema,
  calculate_rsi (Wilder's), 13 unit tests, no external dependencies.

- Milestone 4 / Batch E: Persistence + worker loop — COMPLETE.
  Order/DecisionLog/PortfolioSnapshot ORM models, migration applied,
  trading_cycle_service (domain->ORM boundary), evaluation_job
  (orchestrator), scheduler (APScheduler wiring). Verified with 6
  passing unit tests covering the full evaluate->risk->order->log->
  snapshot pipeline against fake broker/market-data implementations.

## Phase 2: Paper Trading — COMPLETE

- Batch A: Domain types (Signal, Order, Position, Portfolio) + rule evaluator
- Batch B: Risk manager
- Batch C: Execution adapter (Broker interface + AlpacaBroker)
- Batch D: Backtest engine (ideal-fill simulator, daily-only V1 constraint)
- Batch E: Persistence (Order/DecisionLog/PortfolioSnapshot) + worker orchestrator
- Batch F: Performance metrics (total return, max drawdown, Sharpe, win rate)

Known, explicitly documented gaps carried forward (not oversights):
- No slippage modeling — backtest results are optimistic by design until
  a slippage model is deliberately chosen as its own milestone.
- No SELL/exit logic — evaluate_strategy only ever produces BUY or HOLD;
  percentage-based stop_loss_pct/take_profit_pct exits against open
  positions remain unbuilt. win_rate_pct has no real caller until this
  exists.
- StrategyConfig has no timeframe field — V1 is daily-only by explicit
  constraint (V1_SUPPORTED_TIMEFRAME in workers/evaluation_job.py).

Next: Phase 3 (AI agent features) per the original roadmap, or resolve
the exit-logic gap first — worth a real decision before starting Phase 3,
not an automatic default either way.

## Phase 4: Frontend

0. Backend gap closure (small, precedes or runs alongside Chat):
   Wire ConversationStore to /agent/translate via a conversation_id.

1. Frontend foundation:
   Application shell, routing, layouts, API client, typed schemas,
   TanStack Query setup, global providers, navigation. No feature
   pages.

2. Onboarding flow:
   Welcome -> Trading Mode -> Dashboard. Manual Paper Trading visible
   as "Coming Soon" (disabled). Establishes the real entry flow before
   any feature page exists, so nothing is built behind a temporary
   placeholder route that later needs rewiring.

3. AI Agent page (centerpiece):
   Overview, Chat, Agent Rules, History.

4. Dashboard.

5. Activity:
   Equity curve, positions, orders, decision log.

6. Settings.

7. Polish:
   Skeleton loading states, empty states, error states,
   success/confirmation feedback, responsive layouts, accessibility,
   keyboard navigation, and small purposeful animations/transitions.