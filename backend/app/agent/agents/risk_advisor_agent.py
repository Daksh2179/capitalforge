"""RiskAdvisorAgent: portfolio-wide risk summary (deployment %, cash
reserve %, largest single-position concentration, all against the
REAL configured RiskLimits) and per-candidate risk commentary
(correlation with existing holdings, reusing the Opportunity Engine's
portfolio_impact_score unchanged; relative volatility, computed here
for the first time from the same real daily_returns() series already
used for correlation -- one new, small, local statistic on already-
real data, not a new data source).

Never assumes a hypothetical position size: correlation and relative
volatility are size-independent facts about the candidate itself;
concentration impact depends on an allocation nobody has specified
yet, and this Agent says so honestly rather than guessing one.

Needs both a database Session (for the confirmed strategy's real
RiskLimits and latest PortfolioSnapshot) and a MarketDataProvider (for
real bars) -- the first Agent needing both, since it's genuinely
combining PortfolioAnalystAgent's and TechnicalAnalystAgent's data
needs.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.pipeline.types import AgentExecutionContext
from app.schemas.strategy import StrategyConfig
from app.services import strategy_service, trading_cycle_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.provider import MarketDataProvider
from app.trading_engine.opportunity.portfolio_impact import MIN_OVERLAPPING_OBSERVATIONS, daily_returns, portfolio_impact_score
from app.workers.evaluation_job import LOOKBACK_DAYS, build_risk_limits


def _portfolio_from_snapshot(snapshot) -> Portfolio:
    positions = {
        symbol: Position(
            symbol=symbol,
            quantity=data.get("quantity", 0.0),
            average_entry_price=data.get("average_entry_price", 0.0),
            current_price=data.get("current_price"),
        )
        for symbol, data in snapshot.positions_json.items()
    }
    return Portfolio(cash=snapshot.cash_balance, positions=positions)


def _volatility(bars: list[MarketBar]) -> float | None:
    """Standard deviation of daily_returns() -- the exact same real
    return series already used for correlation, one new statistic on
    it, not a new data source. Same MIN_OVERLAPPING_OBSERVATIONS floor
    as correlation, for consistency."""
    returns = daily_returns(bars)
    if len(returns) < MIN_OVERLAPPING_OBSERVATIONS:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return variance ** 0.5


def _weighted_average_holdings_volatility(
    portfolio: Portfolio, bars_by_symbol: dict[str, list[MarketBar]]
) -> float | None:
    terms: list[tuple[float, float]] = []
    for symbol, position in portfolio.positions.items():
        bars = bars_by_symbol.get(symbol)
        if not bars:
            continue
        vol = _volatility(bars)
        if vol is None:
            continue
        weight = position.market_value or 0.0
        if weight <= 0:
            continue
        terms.append((vol, weight))
    if not terms:
        return None
    total_weight = sum(w for _, w in terms)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in terms) / total_weight


class RiskAdvisorAgent:
    name = AgentName.RISK_ADVISOR

    def __init__(self, db: Session, market_data: MarketDataProvider) -> None:
        self._db = db
        self._market_data = market_data

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if context.strategy_id is None:
            return [CapabilityResult(
                agent=self.name, description="No active strategy to assess risk for",
                facts=["I don't have an active strategy to assess right now."],
            )]

        strategy = strategy_service.get_strategy(self._db, strategy_id=context.strategy_id)
        if strategy is None or strategy.current_version is None:
            return [CapabilityResult(
                agent=self.name, description="No confirmed strategy version found",
                facts=["I don't have a confirmed strategy to assess right now."],
            )]

        config = StrategyConfig.model_validate(strategy.current_version.config_json)
        risk_limits = build_risk_limits(config.portfolio_rules)

        snapshots = trading_cycle_service.list_portfolio_snapshots(self._db, strategy_id=context.strategy_id, limit=1)
        if not snapshots:
            return [CapabilityResult(
                agent=self.name, description="No portfolio snapshot recorded yet",
                facts=["I don't have a recorded portfolio snapshot yet to assess risk against."],
            )]

        portfolio = _portfolio_from_snapshot(snapshots[0])

        if grounded.resolved_entities:
            return [self._assess_candidate(resolved, portfolio) for resolved in grounded.resolved_entities]

        return [self._summarize_portfolio_risk(portfolio, risk_limits)]

    def _summarize_portfolio_risk(self, portfolio: Portfolio, risk_limits) -> CapabilityResult:
        total = portfolio.total_value
        if total <= 0:
            return CapabilityResult(
                agent=self.name, description="Portfolio has no recorded value",
                facts=["The portfolio has no recorded value yet."],
            )

        deployed_pct = portfolio.positions_value / total * 100
        cash_pct = portfolio.cash / total * 100
        facts = [
            f"Currently {deployed_pct:.1f}% deployed (limit: {risk_limits.max_portfolio_deployment_pct * 100:.0f}%), "
            f"{cash_pct:.1f}% in cash (minimum reserve: {risk_limits.min_cash_reserve_pct * 100:.0f}%)."
        ]

        if portfolio.positions:
            largest_symbol, largest_position = max(
                portfolio.positions.items(), key=lambda kv: kv[1].market_value or 0.0
            )
            largest_pct = (largest_position.market_value or 0.0) / total * 100
            facts.append(
                f"Largest single position is {largest_symbol} at {largest_pct:.1f}% of total value "
                f"(single-position limit: {risk_limits.max_position_pct * 100:.0f}%)."
            )

        if risk_limits.max_open_positions is not None:
            facts.append(f"Holding {len(portfolio.positions)} of a maximum {risk_limits.max_open_positions} positions.")

        return CapabilityResult(agent=self.name, description="Summarized portfolio-wide risk", facts=facts)

    def _assess_candidate(self, resolved, portfolio: Portfolio) -> CapabilityResult:
        symbol = resolved.entity.value
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=LOOKBACK_DAYS)

        candidate_bars = self._market_data.get_historical_bars(symbol, Timeframe.DAY, start, end)
        if not candidate_bars:
            return CapabilityResult(
                agent=self.name, description=f"No price history available for {symbol}",
                facts=[f"I don't have enough price history for {symbol} to assess risk."],
                affected_entities=[resolved.entity],
            )

        bars_by_symbol = {symbol: candidate_bars}
        for held_symbol in portfolio.positions:
            held_bars = self._market_data.get_historical_bars(held_symbol, Timeframe.DAY, start, end)
            if held_bars:
                bars_by_symbol[held_symbol] = held_bars

        correlation = portfolio_impact_score(symbol, candidate_bars, portfolio, bars_by_symbol)
        candidate_vol = _volatility(candidate_bars)
        holdings_vol = _weighted_average_holdings_volatility(portfolio, bars_by_symbol)

        facts = []
        if correlation is not None:
            facts.append(
                f"{symbol} has a correlation of {correlation:.2f} with your current holdings, "
                f"weighted by position size."
            )
        else:
            facts.append(f"I don't have enough overlapping history to assess {symbol}'s correlation with your current holdings.")

        if candidate_vol is not None and holdings_vol is not None:
            relation = "more" if candidate_vol > holdings_vol else "less"
            facts.append(f"{symbol}'s daily price swings have recently been {relation} volatile than your current holdings' average.")
        elif candidate_vol is not None:
            facts.append(f"{symbol}'s daily returns have varied by about {candidate_vol * 100:.2f}% on average recently.")

        facts.append(
            "I don't know what size position you'd take, so I can't say how much this would change "
            "your overall concentration -- only how it relates to what you already hold."
        )

        # Sign only -- no invented magnitude threshold. Negative
        # correlation is unambiguously diversifying; positive is
        # unambiguously concentrating; the sign itself needs no
        # justification the way a specific cutoff would.
        evidence_signal = None
        if correlation is not None:
            if correlation < 0:
                evidence_signal = "supportive"
            elif correlation > 0:
                evidence_signal = "concerning"
            else:
                evidence_signal = "neutral"

        return CapabilityResult(
            agent=self.name, description=f"Assessed correlation and relative volatility for {symbol}",
            facts=facts, affected_entities=[resolved.entity], evidence_signal=evidence_signal,
        )