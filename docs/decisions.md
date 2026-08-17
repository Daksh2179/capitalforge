# Decisions

Logs significant engineering decisions and their rationale.

## Database

- **UUID primary keys**, not auto-incrementing integers, across all tables.
  Avoids leaking record counts, works cleanly across the audit trail once
  decision_logs/orders/trades exist, and is the more common professional
  default.

- **JSONB for StrategyVersion.config_json**, not relational rule tables.
  Rules are naturally nested (AND/OR groups of conditions), not flat rows.
  Strict Pydantic validation at the API boundary (extra="forbid" throughout)
  provides the safety a relational schema would otherwise give, without the
  join complexity or migration overhead every time a new indicator or
  condition type is added.

- **StrategyVersion has no updated_at column.** Its absence is a deliberate
  signal: rows in this table are immutable once created, never modified,
  only superseded by a new row. Strategy (the parent) does have updated_at,
  since its state and current_version_id genuinely change over its lifetime.

- **version_number is computed as MAX(existing) + 1, not COUNT(*) + 1**,
  and is enforced unique per strategy_id via a database-level constraint.
  Correct even if versions were ever deleted, and the constraint turns a
  hypothetical race condition into a loud integrity error rather than
  silent data corruption.

- **Sync SQLAlchemy 2.0 with psycopg (v3), not async.** This is a
  solo-user application with a scheduled background loop, not a
  high-concurrency web server. Async would add real complexity (async
  sessions, async test fixtures) for concurrency headroom this project
  doesn't need. Revisit only if the project later needs to serve many
  concurrent users.

## Local development environment

- **Postgres runs in Docker (docker-compose), remapped to host port 5433**,
  not the default 5432. A native Windows PostgreSQL install already binds
  127.0.0.1:5432 on this machine, intercepting connections meant for the
  container. Remapping avoids the conflict without touching Windows'
  network configuration.

- **Tests run against a real Postgres database (capitalforge_test)**,
  not SQLite, even for what might look like unit-level checks. SQLite's
  JSON handling and constraint enforcement differ from Postgres in ways
  that would give false confidence in tests passing locally.

- **Test isolation uses a transaction-per-test rollback pattern.**
  Schema (all tables) is created once per test session and dropped once
  at the end; each individual test runs inside a transaction that's rolled
  back afterward, so tests never leak data into one another regardless of
  order, without needing to delete rows manually between tests.

## Tooling

- **uv** for Python dependency management, not Poetry. Faster, proper
  lockfile support, increasingly the current default for new Python
  projects.

- **Alembic added as a main dependency, not a dev dependency.** Unlike
  ruff/mypy (which only run against source code, never at runtime),
  Alembic is how the schema gets created and evolved in every environment,
  including a future deployed one. It needs to be present outside of dev.

- **mypy has one documented suppression**: `Settings()` in
  app/core/config.py uses `# type: ignore[call-arg]`. This is a known,
  common false positive with pydantic-settings: BaseSettings fills
  required fields from the environment at runtime, but mypy can't see
  that and analyzes the call as if every non-default field needed to be
  passed explicitly as an argument.

## Architecture (carried forward from the design phase)

- **Alpaca Paper Trading is the sole V1 broker and market data provider.**
  No in-process PaperBroker simulator. Robinhood MCP is deferred to a
  future milestone, once the Alpaca-based system has proven itself. Using
  one provider for both execution and market data avoids drift between
  what the trading engine evaluates and what actually fills.

- **The deterministic trading engine and the agent (LLM) module never
  call each other directly.** The agent may only write to a Strategy
  while it's in the draft state; once a strategy progresses past draft,
  the agent's only access is read-only, for generating explanations from
  decision logs after the fact.

  ## Market data layer (Milestone 2)

- **No Alpaca SDK types may cross the adapter boundary.** The trading
  engine owns trading logic; Alpaca only provides market data and order
  execution. AlpacaMarketData and (later) AlpacaBroker are the only
  files permitted to import from alpaca-py. Every other module only
  ever sees our own domain types (MarketBar now, Signal/Order/Position/
  Portfolio as they're introduced). Verified empirically: fetched real
  bars across AAPL, KPTI, TLRY, GRPN, and SNDL, confirmed every returned
  object is a plain MarketBar with no leaked Alpaca or pandas types.

- **trading_engine/domain/ replaces the earlier shared/types/ placeholder**
  as the home for shared engine value types (MarketBar, Timeframe now;
  Signal, Order, Position, Portfolio to follow as their milestones
  arrive). Ownership is clearer this way: these are trading-engine
  concepts specifically, not generically cross-cutting ones.

- **MarketBar is a plain frozen dataclass, not a Pydantic model.** Unlike
  schemas/, which validates untrusted input at API boundaries, MarketBar
  is only ever constructed internally by our own adapter code from
  already-trusted provider responses. frozen=True enforces immutability
  directly; Pydantic's validation overhead isn't needed here.

- **Timeframe is our own enum, translated to alpaca-py's TimeFrame only
  inside AlpacaMarketData**, via a module-level mapping dict. This
  applies the same boundary rule in the request direction, not just the
  response direction: no caller of MarketDataProvider should need to
  construct or know about Alpaca's TimeFrame/TimeFrameUnit.

- **Using the free IEX feed**, not SIP, per our Alpaca research. Real
  coverage confirmed even on thin/low-priced names (SNDL, ~100-500
  trades/day) returning complete daily bars with no gaps in the tested
  window. Known, accepted limitation: IEX represents ~2.5% of market
  volume; SIP would require a paid Algo Trader Plus subscription.

- **trade_count requires explicit int() conversion at the boundary.**
  alpaca-py types Bar.trade_count as float | None even though it's
  conceptually a whole number; MarketBar.trade_count stays int | None
  since that's the correct domain type, the SDK's looser typing doesn't
  get inherited.

- **get_stock_bars' dict-vs-BarSet return type is narrowed explicitly**
  with an isinstance check that raises if the unexpected dict branch
  (only possible with raw_data=True, which we never pass) is ever hit.
  Satisfies mypy and fails loudly rather than silently if SDK behavior
  ever changes.

  ## Indicators (Milestone 3)

- Indicators are deterministic, stateless, pure functions — no classes,
  no internal state. Signature pattern: calculate_X(bars, period) ->
  list[float | None], aligned by index to the input list[MarketBar].
- No IndicatorResult wrapper: MarketBar already carries timestamps,
  a second aligned structure would be redundant abstraction with no
  current consumer.
- Insufficient history returns None per position, never zero, never
  raises. RSI needs period+1 bars minimum (period price changes);
  SMA/EMA need period bars.
- RSI uses Wilder's smoothing, the industry-standard interpretation,
  not simple rolling-average RSI.
- Indicators know nothing about Alpaca, databases, or APIs — input is
  only list[MarketBar].

  ## Indicators (Milestone 3) — complete

- Indicators are deterministic, stateless, pure functions — no classes,
  no internal state, no side effects. Signature pattern:
  calculate_X(bars: list[MarketBar], period: int) -> list[float | None],
  aligned by index to the input (result[i] corresponds to bars[i]).
- No IndicatorResult wrapper: MarketBar already carries timestamps via
  the input list; a second aligned structure would duplicate that
  alignment with no current consumer. Revisit only if a real need for
  extra per-value metadata emerges.
- Insufficient history returns None per position, never zero, never
  raises. SMA/EMA need `period` bars minimum; RSI needs `period + 1`
  bars (period price changes require period+1 prices).
- RSI uses Wilder's smoothing (simple average seed, then smoothed
  forward with weight 1/period), not simple rolling-average RSI, since
  Wilder's is the industry-standard interpretation.
- No indicator registry yet (string name -> function mapping). No
  current consumer exists; the rule evaluator will be the first real
  consumer once it needs to resolve a strategy config's "indicator":
  "RSI" into calculate_rsi. Add then, not speculatively now.
- No shared helper module yet between sma/ema/rsi. Each currently has
  its own minimal windowing logic; genuine duplication (e.g. if a
  future MACD needs to reuse calculate_ema internally) is the trigger
  to extract shared logic, not assumed upfront.
- Indicators know nothing about Alpaca, databases, or APIs. Verified by
  construction: sma.py, ema.py, and rsi.py import only from
  app.trading_engine.domain.market_bar, nothing else.

  ## Backtest engine (Batch D)

- **V1 backtesting intentionally assumes ideal fills: no slippage, no
  market impact, no partial fills.** This makes backtest results
  optimistic, not production-grade performance estimates — they should
  be read as "how this strategy would behave under ideal execution,"
  not "what this strategy would actually return." Slippage modeling
  (fixed bps vs. configurable vs. volume-based) is deferred to its own
  future milestone, made deliberately once backtest output is actually
  going to be trusted for a real decision, not guessed now.

- **V1 strategies operate only on Timeframe.DAY.** This is an explicit
  architectural constraint, not a silent default: StrategyConfig has
  no timeframe field yet, and the single hardcoded assumption lives in
  one named constant (V1_SUPPORTED_TIMEFRAME in workers/evaluation_job.py),
  not scattered across the codebase. When multi-timeframe support
  becomes a real requirement, StrategyConfig and the API get extended
  deliberately at that point, not retrofitted around an existing
  silent assumption.

  ## Persistence + worker loop (Batch E)

- **ORM models (Order, DecisionLog, PortfolioSnapshot) are distinct from
  their trading_engine.domain counterparts.** Translation happens only
  at the persistence boundary (services/trading_cycle_service.py), never
  inside the engine or the worker. The worker never constructs an ORM
  model directly.

- **The worker (workers/evaluation_job.py) is a pure orchestrator.** It
  contains no trading decisions, no indicator math, no risk logic —
  only calls MarketDataProvider -> evaluate_strategy -> evaluate_risk ->
  Broker -> trading_cycle_service in sequence. Verified by construction:
  the only conditionals in run_evaluation_cycle are "did we get bars"
  and "was the signal a BUY," never a judgment about whether a trade
  is a good idea.

- **workers/scheduler.py is separate from workers/evaluation_job.py**:
  scheduler.py owns APScheduler wiring and iterating active strategies;
  evaluation_job.py owns the single-strategy pipeline. Neither imports
  business logic the other doesn't already expose as a named function.

- **APScheduler has no type stubs** (no py.typed marker). A single
  targeted `# type: ignore[import-untyped]` on the import line is used,
  not a blanket mypy suppression — scoped to the one line that needs it.

## Performance metrics (Batch F)

- **Metrics are pure functions over an equity curve
  (list[tuple[datetime, float]])**, independent of whether that curve
  came from a live backtest or persisted PortfolioSnapshot history —
  both reduce to the same shape before reaching these functions.

- **sharpe_ratio uses a tolerance threshold (std_dev < 1e-9), not exact
  equality, to detect zero variance.** Floating-point compounding
  almost never produces exactly 0.0 even for genuinely constant
  returns, and dividing by a near-zero value produced a wildly
  fabricated Sharpe ratio (order of 1e+16) before this fix. Caught by
  a test that used realistic compounding rather than hand-picked exact
  values — worth remembering as a pattern when testing anything
  involving floating-point variance/division.

- **win_rate_pct has no real caller yet.** It takes trade-level realized
  P&L directly, but the backtest engine currently only ever buys —
  evaluate_strategy never produces SELL, since percentage-based exits
  (stop_loss_pct/take_profit_pct against open positions) were deferred
  back in Batch B/D. This function is tested and correct in isolation,
  but win rate cannot be meaningfully computed until exit logic exists.
  Flagged explicitly so this isn't mistaken for a finished feature.

## Exit management (Phase 2 closing batch)

- **evaluate_exit is a sibling to evaluate_strategy, not a branch
  inside it.** Exits are percentage arithmetic against a Position's
  entry price (stop_loss_pct/take_profit_pct), fundamentally different
  inputs from indicator-based AND/OR entry conditions. Same Signal
  output type, genuinely different computation — reuse without forcing
  a false unification.

- **V1 constraint: at most one open position per strategy/symbol.**
  While a position is open, only evaluate_exit runs; once flat, only
  evaluate_strategy runs. No pyramiding, no partial scaling. Enforced
  identically in both the live worker (evaluation_job.py) and the
  backtest engine, so there's no drift between the two.

- **Exits are always full-position closes, never partial.** RiskDecision
  quantity for a SELL is always the entire open position's quantity —
  avoids speculative partial-exit sizing logic not in the product spec.

- **evaluate_risk gained a SELL branch, not a separate function.** SELLs
  only need to confirm a real position exists (they reduce exposure,
  never increase it), so none of the position-limit/deployment/cash-
  reserve checks that apply to BUYs are relevant. Same RiskDecision type.

- **Broker interface required no changes.** place_order already accepted
  OrderSide.SELL from Batch C; AlpacaBroker already mapped both sides
  correctly. Confirmed by re-reading the existing code before writing
  anything new, per the standing rule against assuming a gap exists
  without checking first.

- **The backtest simulator now computes realized P&L on sell
  (apply_sell_fill), giving win_rate_pct (built in Batch F with no
  caller) its first real consumer.** BacktestResult gained trade_pnls
  alongside trades.

- Phase 2 is now complete with no known gaps in the deterministic
  trading engine's core lifecycle: open, monitor, exit, persist, measure.
  Remaining explicitly-deferred items (slippage modeling, StrategyConfig
  timeframe field) are unchanged from the earlier Phase 2 closing note —
  neither blocks correctness, both are real future work, not oversights.

- phase 3  
 ## Crossover tie-breaking (Group 1 closing note)
- crosses_above/crosses_below require strict inequality on the previous
  bar (prev_value < target_prev, not <=). If the two values are exactly
  equal at the bar immediately before a transition, that is not counted
  as a crossover — the relationship must have been genuinely on one side
  before flipping to the other. Discovered via a test that initially
  picked synthetic data landing exactly on this tie case.

## Conversation storage (Group 2)

- ConversationStore is a minimal two-method interface (get/save),
  deliberately not expanded with list_all/delete/metadata — no current
  consumer needs them. FileConversationStore (local JSON, one file per
  conversation) is the only V1 implementation, gitignored
  (backend/conversations/), so a fresh clone runs immediately with no
  database required.
- FileConversationStore does not explicitly subclass ConversationStore
  (ABC) — it satisfies the interface structurally (matching method
  signatures), verified by tests and mypy, to keep the file free of
  any import beyond the standard library. Not a hard rule; revisit if
  it ever causes confusion in practice.
- conversation_id is validated against a strict alphanumeric/hyphen/
  underscore pattern before being used to construct a file path —
  closes a path-traversal opening before conversation_id is ever fed
  by real user-facing input (Group 4).
- agent/ subfolder convention: files shared across multiple agent
  capabilities (conversation_store.py, the upcoming llm_client.py)
  live directly under agent/; files specific to one capability live
  in that capability's subfolder (translation/, explanations/). Same
  pattern as trading_engine/domain/ holding types shared across
  rules/, risk/, execution/.
- Renamed the stale agent/strategy_drafting/ folder (leftover from
  before the translation_service naming decision) to agent/translation/.

## LLM provider integration (Group 3)

- Groq (openai/gpt-oss-20b) is the LLM provider, using native strict-
  mode structured outputs (response_format: json_schema, strict: true)
  — not a third-party library like instructor, not manual JSON parsing
  with retry logic. Guarantees schema-compliant output, no validation
  retry loop needed.
- LLMClient._make_strict_compatible() recursively injects
  additionalProperties: false into every object in a Pydantic-
  generated JSON schema, including nested $defs. Groq's strict mode
  requires this on every object; Pydantic's model_json_schema() does
  not set it by default. This was a real, confirmed failure (400
  BadRequestError) before the fix, not a speculative concern — worth
  remembering since it will apply directly to StrategyConfig once
  Group 4 needs the LLM to emit one.
- messages: list[dict] is typed loosely rather than importing Groq's
  SDK message types, consistent with never letting alpaca-py or any
  other external SDK type cross out of its owning adapter file.

  ## Translation flow follow-ups (Group 4, post-initial-commit)

- get_market_context's returned MarketContext.symbol reflects the
  symbol argument passed in, not necessarily anything read off the
  bars themselves. In practice these always match against a real
  MarketDataProvider (you get back bars for the symbol you asked
  for), but this is worth naming as an explicit, relied-upon
  assumption rather than something the function actively verifies.
  Caught by a test that initially asserted the wrong behavior,
  corrected once the actual code was re-read carefully.

- intent_translator._build_condition requires period only when
  indicator != "PRICE" — PRICE has no window (calculate_price ignores
  its period argument entirely), so requiring one from the LLM would
  force either an invented meaningless value or a wrongly-rejected
  valid intent. Confirmed against a real Groq response, which
  correctly omitted period for a PRICE condition and originally broke
  the translator instead of the model. Non-PRICE indicators without a
  period now raise a clear ValueError immediately, rather than passing
  None through to Pydantic and failing with a less legible error.

  ## Validation layer (Group 5)

- validate_strategy is pure and deterministic — no LLM involvement,
  consistent with "contradictions and impossible conditions must never
  depend on model judgment." Returns every issue found, not just the
  first, so a confirmation screen can show the complete picture at once.
- ValidationIssue carries a Severity (ERROR blocks confirmation,
  WARNING doesn't). Over-100%-total-allocation is ERROR (structurally
  impossible); exceeding a configured max_allocation_pct is WARNING
  (the risk manager already enforces this correctly at trade time per
  Group 1's RiskLimits wiring — not a broken config, just worth surfacing).
- Buy/sell price contradiction is only checked when both sides use a
  literal PRICE threshold with exactly one matching condition each.
  Indicator-based conditions (RSI, crossovers, etc.) are silently
  skipped rather than guessed at — there's no direct number comparison
  to make there.
- This re-enforces "at least one condition per asset rule" and
  "asset_rules non-empty," the exact constraints deliberately relaxed
  at the schema level in Group 4. The schema allows an empty draft
  mid-conversation; this layer is what actually blocks an empty or
  incomplete strategy from being confirmed (Group 6).

  uv run mypy app

## Confirmation flow (Group 6)

- Two endpoints: POST /agent/translate (message -> TranslationResult,
  no persistence) and POST /agent/confirm (draft -> validate_strategy
  -> if any ERROR issues, reject with zero persistence -> if clean,
  persist via strategy_service with source=CHAT and confirmed_now=True).
- strategy_service.create_strategy/create_new_version gained a
  confirmed_now: bool = False parameter, defaulting False so every
  existing caller (Milestone 1's manual POST /strategies, all prior
  tests) is unaffected. Only /agent/confirm passes True. This finally
  gives StrategyVersion.confirmed_at a real value — the column existed
  unused since Milestone 1.
- ConfirmRejectedResponse/ConfirmAcceptedResponse are both returned
  with HTTP 200, not a 4xx — a rejected draft isn't a client error,
  it's a valid, expected outcome of validation the caller needs to
  read and act on (fix the draft, try again).
- Warning-only validation issues (e.g. exceeding max_allocation_pct)
  do not block confirmation — only ERROR severity does, per Group 5's
  severity split.

## Post-trade explanations (Group 7)

- LLMService gained generate_text(messages) -> str, separate from
  generate_structured. Explanations are prose, not structured data —
  forcing them through a Pydantic-schema/strict-mode path would be the
  wrong tool for a task with no schema to enforce.
- explanation_service reads DecisionLog rows where explanation_text IS
  NULL, generates via the LLM, writes back — one commit per row, so a
  failure partway through a batch doesn't lose already-generated
  explanations for earlier rows.
- Deliberately not wired into the worker loop. The worker's
  responsibility (per the orchestrator-only rule) is running the
  trading cycle; explanation generation is a separate, on-demand (or
  externally scheduled) process. Whether it later gets its own
  APScheduler job is a deployment decision, not resolved here.
- Concept explanations ("what does RSI mean") remain out of scope —
  Group 8, a small addition once this and the translation flow exist,
  not built now per the standing rule against building ahead of a
  real consumer.
- generate_text's Groq call needed its `# type: ignore[call-overload,
  arg-type]` placed on the same physical line as the call itself, not
  the line with the opening parenthesis of a multi-line call — mypy
  attributes suppression comments to the exact line the error is
  reported on.

  ## Frontend (Phase 4)

### Product framing
CapitalForge's frontend presents the AI as a continuously-working agent
executing user-defined rules, never as a chatbot that only acts while a
conversation is open, and never as a system that invents or modifies
user intent. This framing governs UI copy everywhere: "your rule
triggered a buy," never "the AI decided."

### Onboarding
Welcome -> Trading Mode -> Dashboard. Trading Mode is framed as "How
would you like to start?" (AI Trading Agent / Manual Paper Trading —
Coming Soon, disabled), not a permanent mode choice — manual trading
has no backend support today and is not built in V1.

### Navigation
Dashboard / AI Agent / Activity / Settings. Deliberately not mirroring
backend resource boundaries 1:1 (e.g. Orders and Portfolio Snapshots
are separate endpoints but one Activity page) — navigation maps to
user tasks, not API shape.

### Dashboard
Intentionally lightweight: status strip (state, last checked, next
evaluation), portfolio value with a sparkline, optional compact
Today's Summary row (evaluations/trades/rejections/waiting counts,
rendered as a single inline row, not a boxed card), and shallow
previews linking into Activity/AI Agent. Never duplicates a page that
already owns the full version of that data.

### AI Agent page
The heart of the application. Tabs: Overview, Chat, Agent Rules,
History.
- Overview: agent state, per-asset "currently monitoring" cards with
  live "distance to trigger" (current price vs. condition threshold,
  computed from existing MarketDataProvider data), and an unfiltered
  recent-evaluations feed — including "no action" entries, which serve
  as the heartbeat proving the agent is actively working.
- Chat: the communication interface only, not the page's identity.
  Draft state is visually and physically separated from the active
  Agent Rules at all times (a persistent "Draft — not yet running"
  header, distinct color from the Active-state green). Every
  UPDATED_DRAFT turn renders an inline diff from applied_operations
  ("AAPL buy price: $180 -> $175"). NEEDS_CLARIFICATION and
  NEEDS_DISAMBIGUATION render as structured cards (market-context
  range + numeric input; tappable symbol chips), not chat bubbles —
  submissions still flow through the same /agent/translate call.
  Depends on ConversationStore being wired to a real endpoint (not yet
  built — tracked as its own small backend group, see roadmap).
- Agent Rules: confirmed, read-only policy view. Per-asset rules in
  plain English (reusing the same rendering as the live draft pane),
  plus a distinct section for portfolio-wide PortfolioRules (cash
  reserve, max allocation, max open positions) that Overview's
  per-asset cards don't show.
- History: StrategyVersion history only, rendered as a diff timeline
  (what changed, source manual/chat, when) — not evaluation history.

### Activity
The canonical historical record: equity curve (full PortfolioSnapshot
history via Recharts), current positions (with distance-to-trigger
applied to stop-loss/take-profit the same way Overview applies it to
entry conditions), full order history, and the complete decision log.
Decision log defaults to "Trades & Rejections" (meaningful events),
with an explicit toggle to reveal every evaluation — an intentionally
different default than Overview's unfiltered feed, since the two
pages answer different questions ("prove it's working" vs. "show me
what mattered").

### Settings
Intentionally minimal: read-only Alpaca connection status (sourced
from Broker.get_portfolio()), no placeholder settings for capabilities
that don't exist yet (notifications, theming, account management).

### Cross-cutting rules
- Status color vocabulary, fixed everywhere: Active=green,
  Paused=amber, Draft=gray.
- Explanation-first rendering: wherever a DecisionLog entry appears
  (Dashboard, Overview, Activity), the explanation text is primary,
  visible content, never hidden behind a tooltip or expand action.
- "Distance to trigger" is a reusable pattern (current value vs.
  threshold), applied on Overview's monitoring cards and Activity's
  Positions section.
- Vocabulary rule applies everywhere, including Settings and error
  copy: user actions and rules are the subject, never "the AI decided."

### Multi-user readiness (no auth in V1)
All API calls route through one central current-user seam (a single
hook/function), even though it returns a fixed constant today. Adding
real auth later should require changing that one seam, not searching
the codebase for inline user_id references.

### Visual philosophy
Professional trading platform aesthetic (Bloomberg/TradingView/
Zerodha-adjacent), not AI-demo styling. No gradients-as-AI-signifier,
robot/brain iconography, circuit-board or hexagon motifs. Lucide icons
only, chosen per feature, not "AI flavor." No logo/favicon generation —
placeholder only, final branding deferred.

## Conversation wiring (Phase 4, backend group)

- ConversationStore is keyed by a frontend-generated conversation_id
  (crypto.randomUUID()), not a backend-owned identifier. A conversation
  genuinely begins before any Strategy exists — forcing early strategy
  creation just to hold a conversation would work against the
  draft-before-confirmation model established in Groups 4-6. Backend
  still owns all conversation contents, persistence, and lifecycle;
  only the identifier's origin is client-side.
- ConversationStore's stored value widened from a bare message list to
  a ConversationSession {messages, draft}. Restoring a conversation on
  reload means restoring the working draft too, not just the
  transcript — otherwise the frontend would have to reconstruct state
  that already exists on the backend.
- /agent/translate and /agent/confirm no longer accept draft or
  conversation_history as request parameters. Both are always loaded
  from the stored ConversationSession server-side — closes an
  integrity gap where a client could otherwise assert an arbitrary or
  stale draft.
- TranslationService is completely unchanged — confirmed by re-reading
  its signature before wiring anything. Only who supplies
  (message, history, draft) changed, not the function itself.
- FileConversationStore now formally subclasses ConversationStore(ABC),
  superseding the "structural typing, not a formal subclass" decision
  from Group 2. That earlier choice caused a genuine mypy failure once
  a function needed to return ConversationStore as a declared type
  (api/agent.py's dependency provider) — mypy checks ABC conformance
  nominally, not structurally. Same pattern now used consistently
  across every adapter (Broker, MarketDataProvider, LLMService,
  ConversationStore).
- Test helper pitfall worth remembering: app.dependency_overrides.clear()
  wipes every override, including get_db — when a test needs to
  reset only one dependency override mid-test (e.g. swapping
  TranslationService between translate calls), use
  del app.dependency_overrides[specific_dependency] instead, or the
  next call silently runs against the real dev database instead of
  the test's isolated transaction.

  ## Markets page scope (Phase 4, final)

- Markets page philosophy: a few polished, purposeful sections, not
  feature parity with Robinhood/Webull/TradingView. Every section must
  justify its API cost and UX value before being added.
- Frozen scope: Market Snapshot (SPY/QQQ/DIA strip), Search (fuzzy,
  the primary journey for known intent), Featured Stocks (a small
  curated/hardcoded list, not algorithmic), Stock Detail Page (real
  chart per symbol). Nothing beyond these four without deliberate
  justification.
- Explicitly, permanently out of scope for Markets: Top Gainers/Losers,
  Most Active, New Listings, personal watchlists, news, sector
  browsing. Not "later" — these don't fit the product's intentionally
  curated philosophy, independent of whether the underlying data is
  ever confirmed available.
- Search behavior is state-driven, not replace-vs-append: no query
  shows Featured Stocks; a query with matches shows only results; a
  query with no matches shows "No results found" with Featured Stocks
  still visible beneath it, so the page never dead-ends.

## Capital allocation model (Phase 4) — implementation confirmed

- PositionSizing renamed to CapitalAllocation throughout the backend
  and frontend (AssetRule.capital_allocation, three types:
  percentage_of_portfolio, fixed_capital, share_count). Naming
  deliberately reflects ongoing capital management, not one-time
  purchase size — see the earlier design entry for why.
- Risk manager branches on allocation type to compute requested_value,
  then flows through all pre-existing checks unchanged. New
  PortfolioRules.total_capital_usd is an optional ceiling, checked via
  RiskLimits.total_capital_usd, alongside (not replacing) existing
  checks.
- validation.py's allocation over-commitment check only sums
  percentage_of_portfolio allocations — the only commensurable type
  across assets; fixed_capital and share_count aren't meaningfully
  addable into a portfolio-wide percentage.
- Confirmed via Claude Code implementation pass: 215 tests passing,
  ruff/mypy clean. Two stale tests deleted (asserted a min_length=1
  constraint already deliberately relaxed back in Group 4 for
  in-progress drafts) — not a regression, a cleanup of tests that had
  outlived the design they were written against.

## AssetRule identity (Phase 5)

- **AssetRule gained id/created_at/updated_at.** Reading draft_updater.py
  before designing the Opportunity Engine's tie-break policy surfaced a
  real problem: asset_rules list position was never a stable ordering —
  _apply_asset_fragment moves an edited rule to the end of the list on
  every single edit (adding a condition, changing allocation, anything),
  so "list order = creation order" was false the moment a rule was ever
  touched twice. FIFO by list position would have silently tie-broken by
  most-recently-edited, not actually-created-first.
- id/created_at/updated_at all default via Pydantic default_factory
  (uuid4() / now()), so no existing call site that constructs an
  AssetRule without them breaks — draft_updater is what actually
  guarantees the semantic contract (id and created_at survive every
  edit unchanged; updated_at bumps on every edit), not the schema itself.
- schema_version bumped 2 -> 3, same precedent as the 1 -> 2 bump: old
  StrategyVersion rows fail validation on load. No production data at
  stake, dev-only.
- Verified isolated to the backend: checked frontend types/strategy.ts,
  formatStrategy.ts, and AppliedOperationsDiff.tsx before implementing.
  TypeScript interfaces here are structural (no runtime validator), the
  frontend never constructs a StrategyConfig client-side (drafts always
  come from /translate or /confirm responses), and the diff view renders
  the backend's pre-built description string per operation rather than
  diffing AssetRule objects field-by-field — so the new fields, and
  updated_at changing on every edit, are both invisible to existing
  frontend code. Only a stale `schema_version: 2` TS literal needed
  fixing, for correctness, not because anything depended on it.
- Exposed a real, separate bug once identity fields existed:
  request.config.model_dump() (not mode="json") left UUID objects in
  the dict handed to SQLAlchemy's JSONB column, which uses stdlib
  json.dumps internally and can't serialize UUID. Fixed at both call
  sites (api/strategies.py, api/agent.py) via model_dump(mode="json").
  This gap existed before AssetRule had any UUID field; it just had
  nothing to trip on it until now.

## Opportunity Engine (Phase 5)

Extensive research preceded this (systematic portfolio management,
capital rationing/knapsack theory, risk parity, FIFO/pro-rata order
allocation, technical-analysis "confirmation" literature, liquidity/
market-impact practice) before any design was locked. Full reasoning
trail lives in the conversation history; only the resulting decisions
and the categories explicitly rejected are recorded here.

- **The engine is a portfolio planner, not a ranking engine.** It never
  scores an opportunity by predicted quality. Its only legitimate inputs
  are structural facts: capital/cash-reserve/position-count headroom,
  liquidity relative to a candidate's own trading volume, and
  correlation with the portfolio's *existing* holdings. Everything else
  falls back to a deterministic procedural policy (FIFO by
  AssetRule.created_at, then id).
- **Explicitly rejected, and why:** indicator-magnitude ranking (RSI
  depth, distance-below-threshold, EMA separation) — asserts that "more
  of X" predicts a better outcome, the same shape of claim as the
  reward-to-risk idea rejected earlier, regardless of how deterministic
  the computation is. Volume confirmation and multi-timeframe alignment
  — both explicitly justified in their own literature by "higher win
  rate," i.e. still a prediction, just relabeled "confirmation." Kelly
  criterion — requires an estimated win probability, a direct forecast.
  Capital-allocation size as a priority signal — conflates a deployment
  constraint ("may use up to this much") with an opportunity-quality
  judgment; rejected in favor of not needing it once correlation-based
  portfolio-impact evaluation was adopted.
- **Adopted: correlation-weighted-by-position-value against existing
  holdings.** Passes the test the rejected approaches fail: preferring
  a less-correlated candidate is a claim about portfolio risk exposure,
  not about which asset performs better — symmetric regardless of
  market direction. Weighting by each holding's current market value
  (not a simple average) reflects that a larger existing position
  contributes more to concentration than a smaller one; still purely
  structural, no forecast involved.
- **Correlation is evaluated incrementally**, against the planner's own
  evolving simulated portfolio, not just the portfolio's state at the
  start of the cycle. A static-only comparison collapses to FIFO for
  every candidate whenever the real portfolio starts empty (nothing to
  correlate against), which defeats the purpose the moment more than
  one candidate targets the same sector on a fresh account.
- **Unknown correlation (insufficient overlapping return history, or
  nothing held yet) falls back to FIFO**, never to zero — treating an
  unmeasurable correlation as "zero correlation" would silently bias
  the outcome. Per-holding: a holding with too little shared history is
  excluded from the weighted average entirely, with weights renormalized
  across whatever remains computable, rather than diluting the score
  with a fabricated data point.
- **Liquidity/market-impact feasibility (Stage 1a) is the one addition
  from outside the "confirmation" literature that survived scrutiny** —
  it's a claim about executability (can this position size be filled
  without moving the price), not about opportunity quality. Computed
  from data already fetched (MarketBar.volume, same bars used for
  signal evaluation) — no new data source. LIQUIDITY_MAX_ADV_FRACTION =
  0.01, module-level constant, not user-configurable yet. Deliberately
  permissive (never blocks) when volume history is thin or missing,
  since this is a safety layer on top of the user's own strategy, not
  a primary gate.
- **Stage 0 (circuit breakers, e.g. a drawdown-based halt on new buys)
  deliberately left entirely unbuilt.** Real portfolio-level drawdown
  halts are a documented, legitimate practice, but a 2025 Journal of
  Portfolio Management study found mechanical drawdown rules often fail
  in a specific, costly way (halting or exiting right before a
  recovery). Building a half-designed, default-on version of this was
  explicitly rejected in favor of no Stage 0 at all until it gets its
  own deliberate design pass, opt-in, with the tradeoff stated plainly.
- **capital_allocation.py extracted as a shared module** so
  risk_manager.evaluate_risk and the planner's simulation resolve a
  CapitalAllocation into a dollar amount via the exact same function —
  they can never define "requested capital" two different ways.
  risk_manager itself is otherwise behavior-identical after this
  extraction; the existing test suite passing unchanged confirmed this.
- **The planner never reimplements Risk Manager rules.** Capital/
  position-count/cash-reserve feasibility is delegated to the existing,
  unchanged evaluate_risk, called against a simulated Portfolio copy
  during planning and again against the real Portfolio at actual
  execution time. Risk Manager stays the single source of truth for
  those rules; the planner only decides when to consult it and against
  what state.
- **A real bug this surfaced during implementation:** the planner's
  simulation initially deducted Opportunity.requested_capital (frozen
  at collection time) from simulated cash, rather than the amount
  evaluate_risk actually approved. For percentage_of_portfolio
  allocations those two numbers diverge as soon as an earlier candidate
  in the same cycle gets committed (total_value shifts), which silently
  broke feasibility for later candidates. Fixed by deducting quantity *
  current_price (the real approved amount) instead —
  requested_capital is only ever valid for the Stage 1a liquidity
  check, never for cash bookkeeping.
- **ExecutionPlan is deliberately not persisted.** DecisionLog, Order,
  and PortfolioSnapshot already provide the durable audit trail a
  cycle needs; ExecutionPlan is an intermediate planning artifact with
  no current consumer for a historical record of whole plans, only for
  their outcomes. Consistent with the standing rule against persisting
  intermediate state without a real consumer.
- **Opportunity carries the real Signal from the Rule Evaluator**, never
  a reconstructed one. An earlier version of _validate_and_commit built
  a synthetic Signal internally (empty triggered_rules, rule.created_at
  as a fake timestamp) — fixed by threading the actual evaluate_strategy
  output all the way from collection through planning through execution
  and into the DecisionLog, so the audit trail's rules_triggered_json
  is never fabricated for a planned or deferred candidate.
- **DecisionLog gained plan_outcome, a second, independent axis from
  risk_approved.** plan_outcome answers "did the planner ever give this
  candidate a real chance" (null for every SELL and every HOLD/
  unevaluated row, since neither reaches the planner; one of
  skipped_liquidity/deferred/selected for a BUY row). risk_approved
  answers "did the real portfolio, at actual execution time, approve
  it" — independently. A row can be plan_outcome=selected,
  risk_approved=false: the planner chose it against its simulation, and
  the real re-check at execution time still said no, because real state
  had diverged from the simulation. Recording a planner deferral as a
  risk rejection (or vice versa) would misattribute which component
  actually made the call.
- **evaluation_job restructured into distinct phases**: collect every
  signal -> execute SELLs immediately (never ranked or contested for
  capital, so no reason to wait) -> refresh the real portfolio -> build
  Opportunities against post-SELL state -> planner builds the Execution
  Plan -> execute selected BUYs in order_in_plan order, each with a
  fresh, real evaluate_risk call immediately before execution. Bars are
  now fetched once per cycle for the union of every asset_rule's symbol
  and every currently-held symbol (the latter needed for correlation
  even when a held position has no asset_rule of its own).
- **Portfolio snapshot cadence changed from once-per-asset to once-per-
  cycle.** The old cadence only made sense when evaluation and
  execution were interleaved per-asset; now that the cycle is the real
  unit of work, multiple snapshots inside one cycle would reflect
  implementation order, not portfolio states the user ever meaningfully
  experienced.

## Documentation, testing & stabilization (Phase 6)

- **End-to-end scenario tests for the trading engine** (SELL freeing
  capital for a same-cycle BUY, FIFO competition between candidates,
  liquidity skip, correlation preference) — each verified against real
  persisted DecisionLog/Order/PortfolioSnapshot rows, not just
  in-memory assertions, closing the gap between the Opportunity
  Engine's individually-tested pieces and their actual behavior
  together in one cycle.
- **Real bug found and fixed by those tests, not invented as an
  edge case**: evaluation_job._execute_plan passed risk_decision=None
  for every DEFERRED/SKIPPED_LIQUIDITY plan entry, so
  trading_cycle_service.log_decision fell back to a generic
  "not evaluated by risk manager" string — discarding the planner's
  actual, specific reason (e.g. a liquidity explanation or which
  competing candidate won the capital). Fixed by wrapping the
  planner's entry.reason in a synthetic RiskDecision(approved=False,
  reason=entry.reason) instead of None. plan_outcome (not whether
  risk_decision is None) is what correctly signals "never reached the
  real Risk Manager" — the fix doesn't blur that distinction, it just
  stops discarding information that was already being computed.

## ResponseComposer (Phase 7)

- **Priority-ordered composition**: errors/refusals first, then the
  single most-relevant clarification, then every EXECUTED Agent's
  facts (collectively the direct answer for a multi-Agent turn, not
  just one Agent's), then at most one interpretation across the whole
  turn in NORMAL detail (all of them in EXPANDED), then honest
  "not implemented" notices last.
- **Clarification arbitration**: dedup by underlying ambiguity (shared
  candidates or shared `about` entity), merge into one natural
  question rather than picking one Agent's wording verbatim, surface
  the first distinct group in plan order. Deliberately not an
  invented Agent-priority ranking -- no evidence yet justifies one,
  and plan order already reflects a real decision (Grounding's
  inferred relevance), not an arbitrary one.
- **Progressive disclosure via DetailLevel (IntEnum, not bool)**:
  V1 has two levels, detected via the same kind of explicit lexical
  marker check as the RESEARCH/EVALUATE tie-break ("why", "explain
  more", "go deeper", etc.), independent of intent classification.
  Deliberately not boolean-shaped in the type itself, so a future
  third level doesn't require a contract change.
- **Suggested follow-ups (the original design's tier 6) deliberately
  NOT implemented.** A mediocre heuristic here is indistinguishable
  from the unsolicited-steering behavior this project has repeatedly
  refused to build (see the recommendation-philosophy discussion).
  No follow-up suggestions until there's real evidence of what's
  genuinely helpful, not before.
- **Response shape is a list of typed segments (TextSegment today),
  not a bare string** -- deliberately leaves room for richer segment
  types (tables, charts, recommendation cards) later without another
  contract change. `.text` is a V1 convenience flattening only.
- **Known, confirmed, deliberately deferred limitation**: thread
  resolution in memory_update_policy.py resolves the OLDEST open
  thread, not necessarily the one Composer actually chose to surface
  this turn. If Composer's dedup/plan-order selection ever picks a
  different clarification than the oldest-raised one, and the user
  answers it, the wrong thread could be marked resolved next turn.
  This predates Composer (memory_update_policy.py already flagged it)
  but Composer makes it more likely to matter now that more than one
  clarification can realistically coexist in a turn. Real fix needs
  Grounding to match a resolution to a specific thread by entity, not
  "whichever is oldest" -- deferred until that exists, not fixed here.
- **Not yet wired into ConversationPipeline.** Standalone, fully
  tested against ConversationExecutionPlan directly, same discipline
  as every Agent before its own wiring step.

## Conversational Intelligence — Agent roster (Phase 7 continued)

- **STRATEGY_BUILDER and STRATEGY_EDITOR route to one StrategyBuilderAgent
  implementation, not two.** draft_updater already handles create and
  edit identically (_get_or_create_asset_rule branches on symbol
  presence, nothing else). A separate StrategyEditorAgent would wrap
  the same behavior twice. The two AgentNames stay distinct in the
  roster because Goal Extraction can meaningfully classify the
  conversational-intent difference (useful for Composer's wording
  later), even though execution is one shared implementation.
  Confirmed by a real routing test, not just asserted.
- **AgentExecutionContext (GroundedContext + ConversationMemory + draft
  + strategy_id) replaced passing GroundedContext alone to every Agent
  except StrategyBuilderAgent.** One stable, growable contract instead
  of repeatedly changing every Agent's signature as new needs
  (preferences, permissions, request metadata) show up later.
- **ConversationMemory is now frozen=True.** Enforces "only
  memory_update_policy.py writes Memory" structurally — any accidental
  direct field assignment from an Agent now fails loudly instead of
  silently succeeding. model_copy (memory_update_policy's only write
  path) is unaffected by frozen=True.
- **draft_updater/AppliedOperation/CapabilityResult now thread real
  reasoning** for the one case where the system actually chooses a
  value on the user's behalf: a brand-new rule's capital_allocation
  defaulting to 5% when unspecified. Detected via a new was_created
  flag from _get_or_create_asset_rule; None in every other case
  (user-specified values are never given a fabricated justification).
  StrategyExplainerAgent's entire V1 scope depends on this field
  actually being populated somewhere real, not hypothetically.
- **PortfolioAnalystAgent and RiskAdvisorAgent both need a real
  Session and, for RiskAdvisor, a MarketDataProvider** — the first
  Agents needing live infrastructure beyond AgentExecutionContext
  alone. Both reuse existing reads (trading_cycle_service's list_*
  functions, portfolio_impact_score, build_risk_limits) rather than
  duplicating any of them. RiskAdvisorAgent added one new, small,
  local statistic (volatility via stdev of the same daily_returns()
  series already used for correlation) rather than a new shared
  module — promote to shared infrastructure only once a second real
  consumer exists, same rule that governed ConceptDirectory.
- **RiskAdvisorAgent never assumes a hypothetical position size.**
  Correlation and relative volatility are size-independent facts about
  a candidate; concentration impact depends on an allocation nobody
  has specified yet, and the Agent says so honestly rather than
  guessing one.

## Conversational Intelligence — remaining Agent roster complete (Phase 7 continued)

All eleven Agents now real, tested, and wired into ConversationPipeline.
Still not live in api/agent.py.

- **FundamentalAnalystAgent uses Finnhub, not FMP, Alpha Vantage,
  EODHD, or yfinance.** Real investigation, not a default pick:
  Alpha Vantage (25 req/day) and EODHD (20 req/day) are too
  restrictive even for occasional conversational lookups. yfinance is
  free and needs no key, but it's an unofficial scraper against
  undocumented Yahoo endpoints with no SLA — confirmed real,
  documented rate-limiting/IP-blocking issues and breakage whenever
  Yahoo changes its site, incompatible with this project's "never let
  a component silently fail" discipline. FMP's free tier (250 req/day)
  was the original candidate from the Phase 4 handoff, but Finnhub's
  free tier (~60 req/minute, ~86,400/day theoretical) is orders of
  magnitude more generous for equivalent fundamentals coverage
  (P/E, market cap, sector, dividend yield), with no card required.
  Finnhub's free tier is personal/non-commercial only — a fine fit
  for this project today, worth revisiting only if that ever changes.
- **`/stock/profile2` and `/stock/metric` field names were verified
  against real, independent sources before writing the client** —
  `name`, `finnhubIndustry`, `marketCapitalization` from profile2;
  `peBasicExclExtraTTM`, `dividendYieldIndicatedAnnual` nested under
  a `metric` key from `/stock/metric`. Deliberately no EPS field —
  no source confirmed its exact key, and a guessed field name would
  silently return `None` forever rather than error, which is worse
  than just not having the field at all.
- **`finnhub_api_key` is optional (`str | None = None`) in Settings**,
  unlike `alpaca_api_key`/`groq_api_key`. Making it required would
  crash the entire app on startup for anyone who hasn't gotten a
  Finnhub key yet, for a capability that's supposed to degrade
  honestly, not take down everything else.
- **`FundamentalAnalystAgent` distinguishes "not configured" from
  "Finnhub has no data for this symbol"** — two different reasons for
  "I don't have that," reported as two different messages, since one
  is an operational gap and the other is a genuine per-symbol data
  limit.
- **`evidence_signal` exists on `CapabilityResult`, but only two
  Agents legitimately set it.** `TechnicalAnalystAgent` sets it from
  RSI specifically (the one indicator with an actual conventional
  30/70 threshold already in use — no new threshold invented).
  `RiskAdvisorAgent` sets it from correlation's *sign only* (negative
  = supportive/diversifying, positive = concerning/concentrating —
  the sign needs no magnitude threshold to justify it). Deliberately
  left `None` forever on `MarketResearchAgent` (price/range carry no
  directional signal), `FundamentalAnalystAgent` (no researched
  valuation benchmark exists to judge a P/E ratio as "attractive" or
  "expensive" — inventing one now would be exactly the kind of
  ungrounded heuristic this project has refused everywhere else), and
  `PortfolioAnalystAgent` (its evidence is historical/contextual, not
  a directional judgment about the asset itself).
- **`held_position: bool | None` added to `CapabilityResult`, set by
  `PortfolioAnalystAgent` by checking the latest `PortfolioSnapshot`'s
  `positions_json` for the symbol.** This is the one fact
  `InvestmentAnalystAgent`'s SELL gate cannot be allowed to get wrong,
  so it needed to be a real, structural, checked value — not inferred
  from any Agent's prose.
- **Pipeline fan-in, deliberately narrow**: `planner.py` gained
  exactly one ordering rule (if `INVESTMENT_ANALYST` is confirmed,
  schedule it last), and `AgentExecutionContext` gained
  `prior_results: list[CapabilityResult]`, populated by
  `ConversationPipeline` as it accumulates results across the turn's
  loop. A general Agent-dependency framework was explicitly not
  built — this is one targeted mechanism for one Agent's real need.
- **`InvestmentAnalystAgent`'s synthesis is a real, constrained LLM
  call (`generate_structured` against `SynthesizedConclusion`), not a
  hand-written decision tree — a decision reached only after trying
  to make a rule-based version work and concluding it structurally
  can't.** Any deterministic branch on `evidence_signal` labels is
  vote-counting with extra steps ("2 supportive beats 1 concerning").
  Inventing a materiality/severity scale to weigh findings against
  each other is an ordinal scoring system wearing words instead of
  numbers — the same anti-pattern already rejected for the Opportunity
  Engine's ranking, just relabeled. Genuinely weighing which
  specialist's finding matters more *in this specific combination* is
  a language-understanding task, the same category `GoalExtractor`
  already performs — not a fact lookup a rule engine can do honestly.
  This is the correct application of the standing principle
  (deterministic code for objective facts; an LLM for genuine
  judgment), not an exception to it.
- **`SynthesizedConclusion` is deliberately narrower than
  `Recommendation` itself.** The LLM only ever produces `conclusion`,
  `supporting_evidence`, `assumptions`, `confidence`,
  `invalidating_conditions` — `kind`, `subject`, and
  `contributing_agents` are computed deterministically in code and
  never trusted from LLM output, since those are facts the code
  already knows with certainty.
- **The SELL ownership gate is enforced in code, unconditionally,
  after generation — not just requested in the prompt.** If the LLM
  returns `SELL` and `held_position` isn't confirmed `True`, it's
  downgraded to `WAIT` before the `Recommendation` is ever returned.
  The prompt also states the rule as a second layer, but the actual
  guarantee is the code path, matching how every other hard constraint
  in this project has been enforced (mutual exclusivity of
  `draft_change`/`recommendation`, the liquidity/risk checks in the
  Opportunity Engine) — never relying on an LLM "following
  instructions" alone for something that must never be wrong.
- **`PerformanceAnalystAgent` is deliberately distinct from
  `PortfolioAnalystAgent`'s "how's this strategy doing"** — Portfolio
  Analyst reports the single latest snapshot (a point); Performance
  Analyst reports return and max drawdown over the *full* snapshot
  series (a trend), needing at least two data points. Confirmed real
  gap, not worked around: `Order` has no linkage between a BUY and the
  SELL that eventually closes it — there's no round-trip "trade"
  concept in the schema at all, so win rate and per-trade P&L are
  genuinely unanswerable today. Stated honestly as a limitation, never
  approximated.