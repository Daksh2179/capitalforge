"""BacktestAnalystAgent: the 12th Agent, added deliberately -- the
eleven-Agent roster was a real milestone, and this expansion is named
explicitly rather than quietly grown past.

Wraps the EXISTING, unmodified backtest engine (run_backtest,
metrics.py) plus one new, small, additive function (simulate_buy_and_hold,
in benchmark.py) for benchmark comparisons. engine.py and simulator.py
are untouched.

Confirmed, real limitation, disclosed every time it applies: run_backtest
operates on ONE AssetRule at a time, each with the FULL assumed
starting capital. A multi-rule strategy backtested this way does NOT
model the Opportunity Engine's real cross-asset capital competition --
each rule is evaluated as if it had the whole balance to itself. This
is stated in every multi-rule result's `limitations`, never silently
glossed over.

Hypothetical edits ("what if I used RSI 25 instead") reuse
TranslationService's existing, already-correct parsing -- the
resulting StrategyConfig (TranslationResult.draft) is used purely
in-memory for one backtest run and is NEVER persisted, NEVER touches
the real confirmed strategy or draft. No new sandbox/copy
infrastructure was needed for this -- confirmed by reading
run_backtest's real signature (a bare AssetRule, no strategy_id at
all) before writing this Agent.

Hypothetical parsing only fires when the message contains an explicit
marker ("what if", "instead", "try changing") -- calling
TranslationService on every message routed here, including a plain
"backtest my strategy", risks it misreading a non-edit request as an
edit attempt.

Starting capital defaults to the account's real current paper balance
(from the latest PortfolioSnapshot), explicitly labeled as an assumed
SIMULATION capital, never implied to be a real investment amount. Falls
back to a stated, clearly-labeled default when no snapshot exists yet.

Time windows use a small, local, explicit keyword parser (matching
DetailLevel's own discipline) -- not a general date-NLP system.
Defaults to 90 days when nothing specific is stated.

Same-turn hypothetical/benchmark comparisons work well. A separate
follow-up turn referencing a PREVIOUS backtest result ("compare that
with...") is not yet resolvable -- ConversationMemory has no
"recent hypothetical result" concept the way it has primary_focus for
entities. Not silently pretended to work.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.conversation_memory import EntityReference
from app.agent.pipeline.types import AgentExecutionContext, ResolvedEntity
from app.agent.translation.translation_result import TranslationStatus
from app.agent.translation.translation_service import TranslationService
from app.schemas.strategy import PortfolioRules, StrategyConfig
from app.services import strategy_service, trading_cycle_service
from app.trading_engine.backtest.benchmark import simulate_buy_and_hold
from app.trading_engine.backtest.engine import run_backtest
from app.trading_engine.backtest.metrics import max_drawdown_pct, total_return_pct, win_rate_pct
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.provider import MarketDataProvider
from app.workers.evaluation_job import build_risk_limits

_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_STARTING_CASH = 100_000.0

_WINDOW_PATTERNS: list[tuple[str, int]] = [
    (r"(\d+)\s*day", 1),
    (r"(\d+)\s*week", 7),
    (r"(\d+)\s*month", 30),
    (r"(\d+)\s*year", 365),
]

_HYPOTHETICAL_MARKERS = ["what if", "instead of", "instead", "try using", "try changing", "compare with"]


def _resolve_window_days(raw_message: str) -> int:
    lowered = raw_message.lower()
    for pattern, multiplier in _WINDOW_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            return int(match.group(1)) * multiplier
    return _DEFAULT_WINDOW_DAYS


def _is_hypothetical(raw_message: str) -> bool:
    lowered = raw_message.lower()
    return any(marker in lowered for marker in _HYPOTHETICAL_MARKERS)


class BacktestAnalystAgent:
    name = AgentName.BACKTEST_ANALYST

    def __init__(self, db: Session, market_data: MarketDataProvider, translation_service: TranslationService) -> None:
        self._db = db
        self._market_data = market_data
        self._translation_service = translation_service

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context
        raw_message = grounded.raw_message

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=_resolve_window_days(raw_message))
        starting_cash, capital_label = self._resolve_starting_cash(context.strategy_id)

        current_config = self._load_confirmed_config(context.strategy_id) if context.strategy_id else None
        results: list[CapabilityResult] = []

        if current_config is not None and current_config.asset_rules:
            multi_rule = len(current_config.asset_rules) > 1
            for rule in current_config.asset_rules:
                results.append(self._backtest_rule(
                    rule, current_config.portfolio_rules, start, end, starting_cash, capital_label,
                    multi_rule, label="Your current rule for",
                ))

            if _is_hypothetical(raw_message):
                hypothetical_result, _ = self._translation_service.translate(raw_message, [], current_config, None)
                if hypothetical_result.status == TranslationStatus.UPDATED_DRAFT and hypothetical_result.draft is not None:
                    hyp_config = hypothetical_result.draft
                    hyp_multi = len(hyp_config.asset_rules) > 1
                    for rule in hyp_config.asset_rules:
                        results.append(self._backtest_rule(
                            rule, hyp_config.portfolio_rules, start, end, starting_cash, capital_label,
                            hyp_multi, label="The hypothetical version of",
                        ))
                elif hypothetical_result.status == TranslationStatus.NEEDS_CLARIFICATION:
                    results.append(CapabilityResult(
                        agent=self.name, description="Needs clarification on the hypothetical change",
                        facts=[hypothetical_result.clarification_message or "Could you clarify what you'd like to change?"],
                    ))

        strategy_symbols = {r.symbol for r in current_config.asset_rules} if current_config else set()
        benchmark_entities = [r for r in grounded.resolved_entities if r.entity.value not in strategy_symbols]
        for resolved in benchmark_entities:
            results.append(self._backtest_benchmark(resolved, start, end, starting_cash, capital_label))

        if not results:
            results.append(CapabilityResult(
                agent=self.name, description="Nothing to backtest",
                facts=["I don't have a confirmed strategy to backtest, and I'm not sure which symbol you'd like as a benchmark."],
            ))

        return results

    def _load_confirmed_config(self, strategy_id) -> StrategyConfig | None:
        strategy = strategy_service.get_strategy(self._db, strategy_id=strategy_id)
        if strategy is None or strategy.current_version is None:
            return None
        try:
            return StrategyConfig.model_validate(strategy.current_version.config_json)
        except Exception:
            return None

    def _resolve_starting_cash(self, strategy_id) -> tuple[float, str]:
        if strategy_id is not None:
            snapshots = trading_cycle_service.list_portfolio_snapshots(self._db, strategy_id=strategy_id, limit=1)
            if snapshots:
                return snapshots[0].total_value, "your current paper account balance"
        return _DEFAULT_STARTING_CASH, "a default assumed simulation balance (no recorded account balance yet)"

    def _backtest_rule(
        self, rule, portfolio_rules: PortfolioRules, start: datetime, end: datetime,
        starting_cash: float, capital_label: str, is_multi_rule: bool, label: str,
    ) -> CapabilityResult:
        risk_limits = build_risk_limits(portfolio_rules)
        result = run_backtest(self._market_data, rule, start, end, starting_cash, risk_limits)

        total_return = total_return_pct(result.equity_curve)
        max_dd = max_drawdown_pct(result.equity_curve)
        win_rate = win_rate_pct(result.trade_pnls)

        if total_return is None:
            facts = [f"Not enough price history for {rule.symbol} over that window to run a backtest."]
        else:
            win_rate_text = f", {win_rate:.0f}% win rate" if win_rate is not None else ""
            facts = [
                f"{label} {rule.symbol}: {total_return:+.2f}% return over the period, "
                f"{max_dd:.2f}% max drawdown, {len(result.trades)} trade(s){win_rate_text}."
            ]

        limitations = [
            f"This is a SIMULATION assuming {capital_label} (${starting_cash:,.2f} as the starting balance) -- "
            f"not a real investment amount. Fills happen instantly at each day's closing price, with no slippage modeled.",
        ]
        if is_multi_rule:
            limitations.append(
                "Each rule in this strategy was backtested independently with the full assumed balance -- "
                "this does not model how they would actually compete for the same capital together."
            )

        return CapabilityResult(
            agent=self.name, description=f"Backtested {rule.symbol}", facts=facts,
            affected_entities=[EntityReference(kind="symbol", value=rule.symbol, display_name=rule.symbol)],
            limitations=limitations,
        )

    def _backtest_benchmark(
        self, resolved: ResolvedEntity, start: datetime, end: datetime, starting_cash: float, capital_label: str,
    ) -> CapabilityResult:
        symbol = resolved.entity.value
        bars = self._market_data.get_historical_bars(symbol, Timeframe.DAY, start, end)

        if not bars:
            return CapabilityResult(
                agent=self.name, description=f"No data for {symbol}",
                facts=[f"I don't have enough price history for {symbol} over that window."],
                affected_entities=[resolved.entity],
            )

        equity_curve = simulate_buy_and_hold(bars, starting_cash)
        total_return = total_return_pct(equity_curve)
        max_dd = max_drawdown_pct(equity_curve)

        facts = [
            f"Simply holding {symbol} over the same period would have returned "
            f"{total_return:+.2f}%, with a {max_dd:.2f}% max drawdown."
            if total_return is not None else f"Not enough price history for {symbol} over that window."
        ]
        limitations = [
            f"This is a SIMULATION assuming {capital_label} (${starting_cash:,.2f}) buys and holds {symbol} "
            f"for the whole period, with no trading -- not a real investment amount."
        ]

        return CapabilityResult(
            agent=self.name, description=f"Benchmarked against holding {symbol}",
            facts=facts, affected_entities=[resolved.entity], limitations=limitations,
        )