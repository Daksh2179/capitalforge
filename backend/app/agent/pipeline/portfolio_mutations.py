"""The single deterministic boundary where a declared PortfolioChange
actually becomes a real portfolio_service mutation. No Agent ever
calls portfolio_service directly -- this is the only code path that
does, using the exact same functions the manual Portfolio-page UI
calls, so chat and the manual UI stay two interfaces over one source
of truth, never two systems.

Rewrites each result's description/facts to the ACTUAL outcome
(added / already present / removed / wasn't present / failed) --
never the Agent's pre-mutation intent text, since only this function
knows what genuinely happened. Every declared change in a turn is
applied and reported independently -- a partial failure across
multiple symbols is never collapsed into one blanket success/failure
statement, and an already-present/absent symbol is reported honestly
as a no-op, never as if a fresh action occurred.

limitations (e.g. the held-position safety caveat PortfolioAnalystAgent
already attaches at declaration time) are preserved through the
rewrite -- this function only ever replaces description/facts, never
the safety framing an Agent already reasoned about.
"""

import uuid

from sqlalchemy.orm import Session

from app.agent.agent_contracts import CapabilityResult, PortfolioChangeType
from app.services import portfolio_service


def apply_portfolio_changes(
    db: Session, user_id: uuid.UUID | None, results: list[CapabilityResult]
) -> list[CapabilityResult]:
    if user_id is None:
        return results

    updated: list[CapabilityResult] = []
    for result in results:
        if result.portfolio_change is None:
            updated.append(result)
            continue

        change = result.portfolio_change
        try:
            if change.change_type == PortfolioChangeType.ADD:
                existing = portfolio_service.list_holdings(db, user_id=user_id)
                already_present = any(h.symbol == change.symbol for h in existing)
                portfolio_service.add_holding(db, user_id=user_id, symbol=change.symbol)
                fact = (
                    f"{change.symbol} was already on your portfolio list."
                    if already_present else
                    f"Added {change.symbol} to your portfolio list."
                )
            else:
                removed = portfolio_service.remove_holding(db, user_id=user_id, symbol=change.symbol)
                fact = (
                    f"Removed {change.symbol} from your portfolio list."
                    if removed else
                    f"{change.symbol} wasn't on your portfolio list -- nothing to remove."
                )
        except Exception:
            fact = f"Something went wrong updating {change.symbol} in your portfolio list -- it may not have been changed."

        updated.append(CapabilityResult(
            agent=result.agent, description=fact, facts=[fact],
            affected_entities=result.affected_entities, limitations=result.limitations,
        ))
    return updated