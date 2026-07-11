"""Signal: the rule evaluator's output — what the configured entry
conditions concluded, given the latest available bar.
"""

import enum
from dataclasses import dataclass, field
from datetime import datetime


class SignalAction(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """evaluated=False means there wasn't enough indicator history to
    reach a conclusion at all (distinct from a real HOLD, where
    evaluated=True and the conditions were simply false). action is
    always HOLD when evaluated=False.
    """

    symbol: str
    action: SignalAction
    timestamp: datetime
    evaluated: bool
    triggered_rules: list[str] = field(default_factory=list)