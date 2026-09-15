---
name: trade-journal
description: Record a structured post-trade reflection after every closed position and roll the lessons forward into the next session's plan. Use immediately after any exit, and when reviewing whether a pattern of trades is working. Trigger on "reflect", "what did we learn", "journal", "review that trade", or any position closing.
---

# Trade journal

Reflection is only useful if it changes the next decision. A journal entry
that ends "be more disciplined" is worthless. One that ends "stop taking
breakout entries in the first hour when VIX is above 22" is a rule.

## Write one entry per closed position, immediately

```markdown
## YYYY-MM-DD HH:MM — TICKER — result +$X.XX (+X.XR)
**Thesis at entry:** (copied verbatim from the plan — do not rewrite history)
**Invalidation stated at entry:** ...
**Counter-case stated at entry:** ...
**What actually happened:** ...
**Exit reason:** stop | target | trail | time | halt
**Process grade:** A-F — did I follow the plan? (independent of P&L)
**Outcome grade:** A-F — did the thesis pay?
**Which was luck:** ...
**Candidate rule:** a falsifiable if/then, or "none"
```

## Grade process and outcome separately

This is the whole discipline. Four cases:

| | Good outcome | Bad outcome |
|---|---|---|
| **Good process** | Repeat it | Expected cost of doing business — change nothing |
| **Bad process** | **The dangerous one.** Got paid for a mistake. Flag loudly. | Fix the process |

A winning trade taken off-plan is a worse event than a losing trade taken
on-plan, because it teaches the wrong lesson. Mark it.

## Promoting a lesson to a rule

A candidate rule does not change behavior on the strength of one trade. One
observation is an anecdote; markets generate coincidences constantly.

Promotion requires **either**:
- the pattern appears in ≥ 5 closed trades with a consistent sign, **or**
- it can be backtested: encode it in `engine/strategies.py`, run
  `python3 -m sim.run_suite --seeds 300`, and show it improves median
  outcome *without* worsening the ruin rate.

On promotion, write it into the relevant `SKILL.md` and append it to
`docs/04-lessons.md` with the date, the evidence, and the trades that
motivated it. **A rule with no evidence trail gets deleted at the next
review** — that is the mechanism that stops the skill files silting up with
superstition.

## Weekly review (every Friday close)

Run `python3 -m tools.review --week` and answer:

1. Realized weekly return vs. the 5% target — and the honest gap.
2. Win rate, average win in R, average loss in R, profit factor.
3. Total costs as a percentage of starting equity. **If costs exceed
   realized gains, the strategy is trading too often** — this is the single
   most likely failure mode at $300.
4. Largest drawdown and what caused it.
5. Every trade graded bad-process. What is the common factor?
6. Any rule promoted or deleted this week.
7. **Is the account's measured edge (R per trade) still positive?** If it is
   negative over the last 20 trades, cut size to half until 10 consecutive
   trades restore it. If it is negative over 40 trades, stop and escalate to
   the human: the strategy does not work and no amount of sizing fixes a
   negative expectancy.
