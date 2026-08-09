"""The Opportunity Engine: a portfolio-level planner that decides,
once per evaluation cycle, which of several simultaneously-triggered
BUY opportunities actually get funded when capital, position slots, or
liquidity can't accommodate all of them.

See docs/decisions.md for why this exists and what it deliberately
does NOT do: it never ranks opportunities by predicted quality (no
indicator-magnitude scoring, no confirmation-stacking). Its only
inputs are structural facts about the portfolio and the candidates'
own liquidity -- capital, position count, cash reserve, correlation
with existing holdings, and trading volume. Everything not decided by
those falls back to a deterministic procedural policy (FIFO by
AssetRule.created_at, then id).
"""