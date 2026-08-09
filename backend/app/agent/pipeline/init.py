"""The conversation pipeline: Goal Extraction -> Grounding ->
Execution Plan -> execution -> Memory update. See
docs/conversation_principles.md for the full design. Not yet wired
into api/agent.py — standalone, fully tested infrastructure, migrated
into the live API once enough Agents exist that switching increases
capability rather than decreasing it (see docs/decisions.md).
"""