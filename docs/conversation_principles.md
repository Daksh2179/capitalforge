# CapitalForge — Conversation Principles

This document is the constitution for the conversational layer, the
same role decisions.md/roadmap.md/architecture.md play for the
trading engine. Any Agent, prompt, or pipeline stage that contradicts
what's written here is wrong, not the document. Written after three
research passes (portfolio-construction-adjacent conversational
patterns, finance-advisor communication, and general dialogue/
explanation design) and dozens of simulated conversations, both
ordinary and deliberately awkward — see decisions.md for the full
research trail; only the resulting rules live here.

## Core philosophy

The conversational layer follows the exact discipline the trading
engine already follows: **use the LLM where language understanding is
genuinely required; use deterministic code everywhere objective state
already exists.** An LLM extracts what the user means. It never
self-reports whether something is ambiguous, whether it has enough
context, or how confident it should be — those are judgments this
architecture consistently found LLMs unreliable at making about
themselves, backed by real research (see decisions.md), not just
house style.

This is the same principle that makes `ConversationState` (and its
successor, Conversation Memory) trustworthy today: state is derived
deterministically from what actually happened, never from the model
saying "here's what I think you meant."

## The five conversational design principles

Every Agent and the Response Composer must honor all five, in order
of precedence when they conflict:

1. **Answer what was actually asked, first.** Volunteer at most one
   genuinely useful next fact per turn — across the whole turn's
   combined output, not once per contributing Agent.
2. **Offer depth, don't force it.** Mention a concept when relevant;
   don't unpack a lecture unless asked or unless the user's own
   phrasing signals unfamiliarity.
3. **Facts, then convention, then explicit limit — always in that
   order.** State the computed value as fact. State its conventional
   interpretation as an attributed convention ("readings below 30 are
   conventionally read as oversold"), never as the agent's own belief.
   State what's uncertain or unknown honestly, without apologizing for
   it.
4. **Adapt depth to inferred expertise, not a settings toggle** — and
   when inferring a novice user, be *more* explicit about what's fact
   vs. convention vs. uncertain, never less. Fluent, confident
   explanations risk creating false confidence in exactly the users
   least equipped to catch it (the "Illusion of Explanatory Depth" —
   see decisions.md).
5. **Clarify only when the missing piece materially changes the
   answer, and always name the specific missing dimension.** Never a
   fixed, one-size-fits-all clarification template regardless of what
   is actually ambiguous.

## The pipeline

User message
│
▼
Goal Extraction (LLM — lightweight only)
│
▼
Grounding Check (deterministic)
│
▼
Conversation Memory Update (pre-routing)
│
▼
Agent Router (deterministic, from confirmed_capabilities)
│
▼
Data Orchestrator (resolves each Agent's declared required_data)
│
▼
Specialist Agents (one or more, same turn)
│
▼
Conversation Memory Update (post-execution)
│
▼
Response Composer
│
▼
User


**Goal Extraction** understands what the user is trying to accomplish,
identifies obvious entities (raw text, unresolved), and proposes
candidate Agents. Nothing more. It does not decide ambiguity,
clarification, confidence, or final routing — all of that happens
after deterministic grounding. Intent values: `LEARN`, `RESEARCH`,
`DECIDE`, `BUILD`, `EDIT`, `EXPLAIN`, `REVIEW`, `EVALUATE`, `CONTINUE`.
Goal Extraction also emits `goal_relation` (`NEW | CONTINUATION |
SUBTASK | ABANDON_AND_REPLACE`) describing how this turn relates to
`active_goal`, since that judgment is genuinely linguistic ("actually,
forget dividends" vs. "also check Nvidia").

**Grounding Check** resolves raw entities against `AssetDirectory`,
resolves pronouns and implicit references against Conversation
Memory, resolves time references, and corrects Goal Extraction's
candidate Agent list against what's actually resolvable. This is
where real ambiguity (two comparably-strong ticker matches) and real
inferability (a pronoun cleanly resolved by `primary_focus`) get
decided — never self-reported by the LLM. Grounding may apply
deterministic linguistic rules to distinguish factual requests from
evaluative requests; V1 uses explicit evaluative language ("should
I," "which is stronger," "recommend," "worth it," "better than") as
the trigger. If Goal Extraction proposes `EVALUATE` but no such marker
is present, Grounding downgrades to `RESEARCH` — ties always go to
*not* volunteering an opinion.

## The Agent roster

Ten Agents, each owning one domain of reasoning:

- **Strategy Builder** — constructs new rules from user language.
- **Strategy Editor** — modifies existing rules.
- **Strategy Explainer** — justifies *why* a past edit was made; must
  say "you specified that directly" rather than inventing a technical
  justification when `ConversationEvent.reasoning` is `None`.
- **Market Research** — company-level information (price, 52-week
  range today; fundamentals/news are declared but currently
  unavailable, not silently omitted).
- **Technical Analyst** — indicator values and their conventional
  interpretation.
- **Fundamental Analyst** — company financials and valuation.
  Introduced now, honestly reporting unavailability, so integrating a
  real data source later requires no redesign.
- **Portfolio Analyst** — reads PortfolioSnapshot/Order/DecisionLog
  history to answer "why didn't you buy X" / "how's this doing."
- **Performance Analyst** — strategy performance over time.
- **Risk Advisor** — volatility, concentration, and risk-profile
  reasoning about a candidate or an existing position.
- **Investment Analyst** — the recommendation orchestrator (see
  below). The only Agent whose entire job is synthesizing other
  Agents' structured outputs.
- **Educator** — canned, hand-reviewed concept explanations (RSI, SMA,
  EMA, moving averages, technical analysis generally). Deliberately
  not LLM-generated. Corrects a real gap: this Agent was in the
  original nine-Agent roster but was silently dropped when
  Fundamental Analyst was added later, leaving the "ten Agent" count
  in this document wrong until now -- the roster is actually eleven.

## The universal Agent contract

Every Agent, without exception, implements:

can_handle(context: GroundedContext) -> bool
required_data(context: GroundedContext) -> list[DataRequirement]
clarification_needed(context, data) -> ClarificationRequest | None
execute(context, data) -> CapabilityResult


And every Agent's contract must answer three questions, not two:

1. **What data do I require?** Declared, never fetched ad hoc — no
   Agent reaches for global state it didn't declare through
   `required_data()`.
2. **What deterministic outputs do I produce?**
3. **What am I explicitly not allowed to infer?** Every Agent refuses
   future-value prediction. `InvestmentAnalystAgent` additionally
   refuses personal-suitability judgment (see Boundaries, below).

**`InvestmentAnalystAgent` performs no domain analysis.** It never
computes indicators, reads raw market data, evaluates portfolio
metrics, or interprets financial statements directly. It only
synthesizes structured outputs already produced by specialist Agents
into a coherent recommendation. This is not an implementation detail —
it is part of its contract, enforced the same way Risk Manager doesn't
calculate indicators and the Opportunity Engine doesn't perform risk
checks.

## Conversation Memory — governing principles

(Schema itself lives in code once built; these are the rules that
govern any future change to it.)

- **References, not data.** Memory stores what's being discussed, never
  the facts themselves. No cached prices, indicator values,
  PortfolioSnapshot, or DecisionLog rows. Every Agent re-fetches live
  data every turn via `required_data()`.
- **No Agent owns Memory.** Agents only produce `CapabilityResult`s.
  One deterministic Memory Update Policy decides what survives into
  Conversation Memory — exactly like Risk Manager being the single
  source of truth for capital/position rules.
- **Reconstructibility test for any new field:** if it could be
  deterministically reconstructed from persisted history without the
  LLM reasoning again, it doesn't belong in Memory.
- **Expiry is semantic, never a fixed TTL.** A thread or focus expires
  because the conversation's focus changed, the goal changed, the user
  abandoned it, or it was resolved — never because N turns passed.
- **`ConversationThread` is the general mechanism for surviving
  interruption** — clarification is one instance of it, not the whole
  concept. "Explain RSI... [detour]... continue the RSI explanation"
  reopens an existing thread; nothing new is invented.

## Recommendations

**The reconciliation, locked:** Recommendations are conversational
output. Strategies, rules, and execution are deterministic system
behavior. The user always owns what gets into the strategy. The agent
may help the user decide, but it never silently converts advice into
action. A follow-up like "okay, buy it then" is a brand-new `BUILD`
turn through Strategy Builder's normal clarification discipline — it
never inherits a threshold from a recommendation.

**Enforced at the type level, not by convention:** `CapabilityResult`'s
`draft_change` and `recommendation` fields are mutually exclusive on
every result, permanently. No Agent that renders an opinion can also
write to the draft in the same breath.

**Recommendations are explicitly solicited only** — intent must
classify as `EVALUATE` (per the deterministic Grounding rule above).
During a `BUILD` turn, `InvestmentAnalystAgent.can_handle()`
structurally returns false even if an unrelated stock is mentioned in
passing — no suppression logic needed, the capability gate already
handles it.

**One `Recommendation` type, internally routed.** The public shape is
one object; Grounding determines, based on whether the subject is a
security or a methodology, which specialists `InvestmentAnalystAgent`
orchestrates before synthesizing — an asset question pulls in Market
Research/Technical/Fundamental/Portfolio/Risk; a methodology question
("would DCA beat RSI here?") pulls in Technical/Risk only, since
there's no company to research.

```python
class Conclusion(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WAIT = "wait"
    WATCH = "watch"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Recommendation:
    kind: Literal["asset", "strategy"]
    subject: list[EntityReference]
    conclusion: Conclusion
    supporting_evidence: list[str]
    assumptions: list[str]
    confidence: Literal["high", "moderate", "low"]
    invalidating_conditions: list[str]
    contributing_agents: list[AgentName]
```

`WAIT` is the default safe outcome. Not trading is always a valid
decision throughout CapitalForge; nothing in this architecture should
pressure an Agent into manufacturing a BUY or SELL merely because an
evaluation was requested. `INCONCLUSIVE` is a legitimate, expected
answer when specialists' evidence genuinely conflicts — to be reported
honestly, never forced toward a lean.

**Locked exactly as written, in this document, the `Recommendation`
model's docstring, `InvestmentAnalystAgent`'s contract, and
decisions.md:**

> Confidence represents the completeness, consistency and quality of
> the available evidence. It must never be interpreted as the
> probability that a trade will succeed.

Even a single-subject recommendation is implicitly comparative against
the counterfactual of not acting — state that baseline explicitly
("compared to holding cash," "compared to your current allocation")
rather than let the opinion appear to exist in a vacuum.

## Traceability

Every conversational conclusion must be traceable. Every
recommendation, explanation, warning, clarification, or educational
response must be explainable by pointing back to one or more
specialist Agent outputs — never "because the LLM thought so." This is
the conversational-layer counterpart to DecisionLog recording every
decision and the Opportunity Engine explaining every deferral.
`Recommendation.contributing_agents` and `ConversationEvent.reasoning`
exist specifically to make this checkable, not just aspirational.

## Boundaries (never loosened by the above)

- **No unsolicited investment ideas**, ever — the `EVALUATE` gate is
  the only door into asset or strategy opinions.
- **No prediction of future values or outcomes** — every Agent's
  contract refuses this, not just `InvestmentAnalystAgent`.
- **No personal-suitability advice.** "Should I buy Tesla" (asset
  opinion, allowed on request) and "should I buy Tesla given I'm
  retiring soon" (suitability advice wearing an asset question's
  clothes) must resolve differently. The agent may analyze assets; it
  does not become a financial adviser reasoning about someone's
  personal financial situation. This is outside CapitalForge's purpose
  and must be declined honestly, not answered cautiously.
- **Never assert a fact the system has no data to back**, even when
  it happens to be true (e.g., a private company's status) — report
  what was actually found, not an inferred explanation for why nothing
  was found.

## ResponseComposer

The single place responsible for the conversational personality of
the system. Agents produce structured facts, interpretations,
clarifications, recommendations, and explanations -- they never write
prose meant to sound like a conversation. Composer owns: ordering,
transitions, wording, brevity, progressive disclosure, deduplication,
and keeping a multi-Agent turn feel like one coherent conversation
rather than stitched-together specialist outputs.

Multi-Agent conflict is never resolved by Composer -- if Technical
Analyst and Risk Advisor point in different directions, both are
presented as what they are (independent pieces of evidence), never
forced into agreement. This is deliberate preparation for
InvestmentAnalystAgent, which is the only place synthesis across
conflicting evidence is allowed to happen.

Adding a new Agent (FundamentalAnalystAgent, InvestmentAnalystAgent,
etc.) should require registering a capability, never rewriting
composition logic -- Composer never special-cases any Agent by name,
only by ResultKind/CapabilityResult structure.