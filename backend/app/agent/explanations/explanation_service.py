"""explanation_service: generates plain-English explanations for
DecisionLog rows, using the same LLMService as translation. Reads rows
where explanation_text IS NULL, writes generated text back. Not wired
into the worker loop — the worker's job is running the trading cycle,
not generating prose synchronously inside it. This is a separate,
on-demand (or externally scheduled) batch process.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.explanations.prompts import EXPLANATION_SYSTEM_PROMPT
from app.agent.llm_service import LLMService
from app.models.decision_log import DecisionLog


def explain_decision(log: DecisionLog, llm_service: LLMService) -> str:
    """Generate (but do not persist) an explanation for one DecisionLog."""
    facts = {
        "symbol": log.market_snapshot_json.get("symbol"),
        "action_taken": log.action_taken,
        "rules_triggered": log.rules_triggered_json,
        "risk_approved": log.risk_approved,
        "risk_reason": log.risk_reason,
        "market_close_price": log.market_snapshot_json.get("close"),
        "timestamp": log.timestamp.isoformat(),
    }

    messages = [
        {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Explain this trading decision: {json.dumps(facts)}"},
    ]

    return llm_service.generate_text(messages)


def explain_unexplained_decisions(db: Session, llm_service: LLMService, limit: int = 50) -> int:
    """Finds up to `limit` DecisionLog rows with no explanation yet,
    generates and persists explanations for each. Returns the count
    actually processed. Each row is committed individually, so a
    failure partway through doesn't lose already-generated explanations.
    """
    logs = db.execute(
        select(DecisionLog).where(DecisionLog.explanation_text.is_(None)).limit(limit)
    ).scalars().all()

    processed = 0
    for log in logs:
        log.explanation_text = explain_decision(log, llm_service)
        db.commit()
        processed += 1

    return processed