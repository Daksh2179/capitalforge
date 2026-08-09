# Architecture

CapitalForge is a self-hosted AI trading agent that continuously manages a user-defined portfolio using deterministic trading rules.

The user defines *what* should happen. The agent continuously evaluates markets and executes those rules autonomously.

---

# Design Principles

- Deterministic trading decisions.
- Conversational configuration, deterministic execution.
- Portfolio-wide planning.
- Separation of responsibilities.
- Explainability over prediction.
- Self-hosted first.
- AI assists the user, never invents user intent.

---

# High-Level Architecture

Frontend
↓
Conversation API
↓
Conversation Engine
↓
Translation
↓
Validation
↓
Strategy Management
↓
Worker
↓
Trading Engine
↓
Opportunity Engine
↓
Risk Manager
↓
Broker

---

# Core Components

## Frontend

Primary interface for interacting with the AI trading agent.

Major pages:

- Markets
- Dashboard
- AI Agent
- Activity
- Settings

The AI Agent page is the centerpiece of the application.

---

## Conversation Engine

Responsible for maintaining conversational context independently of chat history.

Responsibilities include:

- Conversation State
- Entity Resolution
- Conversational Context
- Intelligent Assumptions
- Response Generation

The conversation engine owns deterministic conversation state.

Chat history is not the state.

---

## Translation

Converts natural language into deterministic strategy changes.

Never executes trades.

Never evaluates markets.

Only modifies drafts.

---

## Validation

Ensures confirmed strategies are internally consistent before persistence.

No LLM involvement.

Entirely deterministic.

---

## Strategy Management

Owns:

- Strategy
- StrategyVersion

Confirmed strategies become read-only trading policies.

---

## Worker

Continuously evaluates every active strategy.

For every evaluation cycle:

- determine whether a position exists
- evaluate exits if invested
- otherwise evaluate entries

The worker contains no trading logic itself.

It orchestrates the trading pipeline.

---

## Trading Engine

Responsible for:

- market data
- indicators
- rule evaluation
- signal generation

Produces BUY, SELL or HOLD signals.

Never manages portfolio-wide capital allocation.

---

## Opportunity Engine

A portfolio-level planner, not a ranking engine. It never scores an
opportunity by predicted quality — every input is a structural fact
about the portfolio or the candidate's own executability, never a
claim about which asset will perform better. See decisions.md for the
full set of approaches this deliberately rejected and why.

Operates in stages, over a simulated copy of the real portfolio that
is discarded once planning ends:

1. **Liquidity feasibility** — can this position size realistically be
   filled without moving the price against the user, independent of
   anything else in the plan. Candidate-intrinsic, checked once, before
   any ordering.
2. **Portfolio-impact evaluation** — each remaining candidate's
   correlation with the portfolio's *current* holdings (weighted by
   each holding's market value), recomputed against the planner's own
   evolving simulated portfolio as earlier candidates get committed.
   Prefers diversifying the portfolio over concentrating it. Unknown
   correlation (too little shared price history, or nothing held yet)
   falls back to procedure rather than being treated as zero.
3. **Procedural tie-break** — deterministic FIFO by AssetRule's
   immutable created_at, then id, whenever portfolio impact can't
   differentiate two candidates.
4. **Feasibility validation** — capital, cash reserve, and open-position
   limits, delegated to the same Risk Manager used everywhere else in
   the engine (evaluate_risk), called here against the simulated
   portfolio. The planner never reimplements these rules; it only
   decides when to consult them and against what state.

A circuit-breaker stage (e.g. a portfolio-level drawdown halt on new
buys) is a deliberately deferred, not-yet-built extension point — see
decisions.md for why a half-designed version was rejected in favor of
none.

Produces an Execution Plan: an in-memory-only object (never persisted
— DecisionLog/Order/PortfolioSnapshot already cover the durable audit
trail), where each entry is either skipped, deferred, or selected, with
a human-readable reason. SELL signals bypass the Opportunity Engine
entirely and execute immediately once collected, since they're never
ranked or contested for capital — this also means SELL proceeds are
available to the same cycle's BUY planning.

Every selected entry is still re-validated against the real, live
portfolio via a second evaluate_risk call immediately before an order
is placed — the plan only decided what to *attempt*; reality gets the
final say, exactly as every signal always has, whether or not it came
through the planner.

---

# Evaluation Cycle

Every evaluation cycle follows:

1. Fetch bars once for every asset_rule's symbol and every currently
   held symbol (the latter needed for portfolio-impact evaluation even
   when a held position has no asset_rule of its own).
2. Evaluate every asset_rule's signal (SELL if a position exists and
   its conditions or percentage exit trigger, BUY if flat and entry
   conditions trigger, otherwise HOLD/unevaluated — logged immediately,
   nothing further to decide).
3. Execute every SELL signal immediately against the real broker.
4. Refresh the real portfolio (SELL proceeds now available) and build
   this cycle's BUY Opportunities.
5. The Opportunity Engine builds an Execution Plan.
6. Execute the plan's selected entries in order, each re-validated
   against the real portfolio via the Risk Manager immediately before
   execution.
7. Record exactly one PortfolioSnapshot for the completed cycle.

This process repeats continuously while the agent is running.

Every decision — SELL, HOLD/unevaluated, and every BUY outcome — is
logged, with two independent axes: plan_outcome (did the Opportunity
Engine ever give this candidate a real chance; null for anything that
never reached it) and risk_approved (did the real portfolio, at actual
execution time, approve it). A candidate can be selected by the
planner and still rejected by the Risk Manager's real, live check —
those represent genuinely different decisions and are never conflated.