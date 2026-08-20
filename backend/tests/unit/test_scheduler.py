"""Unit tests for scheduler.run_all_active_strategies -- specifically
the state-filtering logic (which strategies get evaluated each tick).
Full evaluation behavior is already covered by
test_evaluation_cycle_scenarios.py; this file tests only the new
inclusion of PAUSED alongside ACTIVE, and the correct exclusion of
DRAFT/CLOSED."""

import uuid

from app.models.strategy import StrategyState
from app.services import strategy_service
from app.workers import scheduler


def _create_strategy(db_session, state: StrategyState):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": []},
        source="manual", confirmed_now=True,
    )
    strategy.state = state
    db_session.commit()
    db_session.refresh(strategy)
    return strategy


def test_active_and_paused_strategies_are_both_evaluated(db_session, monkeypatch):
    active = _create_strategy(db_session, StrategyState.ACTIVE)
    paused = _create_strategy(db_session, StrategyState.PAUSED)
    draft = _create_strategy(db_session, StrategyState.DRAFT)
    closed = _create_strategy(db_session, StrategyState.CLOSED)

    evaluated_strategy_ids: list[uuid.UUID] = []

    def fake_run_evaluation_cycle(db, *, strategy, strategy_version, market_data, broker):
        evaluated_strategy_ids.append(strategy.id)

    monkeypatch.setattr(scheduler, "run_evaluation_cycle", fake_run_evaluation_cycle)

    scheduler.run_all_active_strategies(db_session, market_data=None, broker=None)

    assert set(evaluated_strategy_ids) == {active.id, paused.id}
    assert draft.id not in evaluated_strategy_ids
    assert closed.id not in evaluated_strategy_ids