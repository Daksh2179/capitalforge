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

## Phase 5: Autonomous Portfolio Management

Backend

- Opportunity Engine — COMPLETE. Liquidity feasibility (Stage 1a),
  correlation-weighted portfolio-impact evaluation against existing
  holdings (Stage 2, weighted by position value, incremental against
  the evolving simulated portfolio), FIFO-by-created_at procedural
  fallback (Stage 3), shared capital_allocation resolver used
  identically by the Risk Manager and the planner, DecisionLog's
  plan_outcome/risk_approved two-axis model. Stage 0 (circuit breakers)
  deliberately deferred — see decisions.md.
- AssetRule stable identity (id/created_at/updated_at) — COMPLETE,
  implemented as a prerequisite once list-position ordering was found
  to be unstable across edits.
- evaluation_job SELL-first restructure, once-per-cycle portfolio
  snapshot — COMPLETE.

Frontend (not started)

- AI Agent improvements
- Live monitoring cards
- Execution Plan / plan_outcome visibility in the History tab
  (currently invisible: a deferred/skipped BUY produces a DecisionLog
  row but no Order, so nothing in the UI surfaces it yet)
- Opportunity explanations

## Phase 6: Documentation, Testing & Stabilization (current)

1. docs/decisions.md, docs/roadmap.md, docs/architecture.md updated to
   reflect the Opportunity Engine as actually built, not just designed.
2. End-to-end scenario/integration tests for the trading engine —
   full-cycle tests exercising SELL-first execution, multi-opportunity
   planning, and plan_outcome logging together, not just each piece in
   isolation (existing unit tests cover the pieces; this closes the
   gap between them).

Next, in order:

3. Finish the Activity page (equity curve, positions, orders, decision
   log — backend endpoints already exist, this is frontend-only work).
4. Finish the AI Agent UI (Overview, Chat, Agent Rules, History tabs
   per the Phase 4 frontend design already recorded in decisions.md).
5. Make capital_allocation genuinely optional (drop the fabricated 5%
   default on unset AssetRule.capital_allocation) — designed, not yet
   implemented; see decisions.md's Capital allocation model entry for
   the original design.
6. Polish and deployment.

## Phase 7: Conversational Intelligence

Not started. A backend capability, not a frontend concern — the chat
is the primary interface to the whole system, and it currently feels
noticeably less capable than the deterministic engine underneath it.
Maps onto the "Conversational Layers" framework already named in
Phase 4/5 planning, completing what was left partial or unbuilt, plus
categories the original framework didn't anticipate:

- Layer 0 (Conversation State) — done.
- Layer 1 (Entity Resolution) — done for exact-match/case-folding;
  needs extending to genuine alias/fuzzy matching (company name vs.
  ticker, e.g. "NextEra" / "nextera" / "NEE" as the same entity) and
  typo tolerance, neither of which the current AssetDirectory.search
  was designed to handle.
- Layer 2 (Conversational Context) — partial. Pronoun and follow-up
  resolution beyond the existing focused_symbol (e.g. "lower it to
  $170"), and last_modified_field-aware edits (e.g. "remove the sell
  rule") were flagged as unbuilt/untested, not just unpolished.
- Layer 3 (Intelligent Assumptions) — policy written down, not
  systematically implemented. Needs concrete rules for what's safe to
  assume (capitalization, aliases, last-discussed-asset, simple
  arithmetic) vs. what must still ask (sizing, ambiguous references,
  missing buy/sell conditions, conflicting instructions) — and,
  crucially, applying the same prediction-vs-structural discipline
  used for the Opportunity Engine: no assumption should ever let the
  model silently decide something material to money.
- Layer 4 (Proactive/Conversational Responses) — unbuilt. Partly
  blocked on missing sector data for portfolio-gap suggestions
  specifically; general "suggest instead of ask" behavior untried
  otherwise.
- New: typo tolerance, and natural finance terminology / colloquial
  phrasing (not requiring the user to already know ticker syntax or
  indicator names).

To be designed with the same discipline as the Opportunity Engine:
identify the full category space before patching individual bugs,
research how existing systems handle each category, and explicitly
name which flexibility is safe (spelling/aliases/context) versus which
would let the model make a judgment call it isn't entitled to make.