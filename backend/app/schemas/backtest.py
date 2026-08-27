"""Response contract for GET /strategies/{id}/backtest -- the
structured, chat-independent counterpart to BacktestAnalystAgent's
prose. Every number here comes from the existing, unmodified
run_backtest/metrics.py/simulate_buy_and_hold functions; this file
adds no calculation of its own, only typed shape around results those
functions already produce.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    # None when there wasn't enough price history in the window to run
    # a single day of simulation -- an honest gap, not a zero.
    period_start: datetime | None
    period_end: datetime | None
    starting_capital: float
    ending_capital: float | None
    total_return_pct: float | None
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    trade_count: int
    win_rate_pct: float | None


class BacktestComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The benchmark is always buy-and-hold of this same symbol over
    # the identical window -- deterministic, no entity resolution.
    symbol: str
    total_return_pct: float | None
    max_drawdown_pct: float | None


class BacktestStructuredResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # What starting_capital actually represents for this run --
    # e.g. "your strategy's declared trading pool" -- resolved via the
    # same shared helper the chat-based Agent uses, so the two paths
    # can never silently disagree on this.
    capital_label: str
    rules: list[BacktestMetrics]
    benchmarks: list[BacktestComparison]
    # Populated when the strategy has more than one rule -- each rule
    # was backtested independently with the FULL assumed balance; this
    # never models the Opportunity Engine's real cross-asset capital
    # competition. See backtest_analyst_agent.py for the identical
    # disclosure used in the chat path.
    limitations: list[str] = []