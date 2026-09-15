# Model strategy

**Question asked:** develop with Opus 5 (medium effort), then switch to
Sonnet 5 (high effort) for ongoing trading. Is there a better approach?

**Short answer:** the development half is right. The runtime half is *nearly*
right, with three changes: split the runtime by task rather than using one
model for everything, use `xhigh` rather than `high` effort for the trading
loop, and — most important — **validate Phase 2 on the model you intend to
deploy, not on Opus.**

## 1. Model choice does not control the risk of ruin here

This is the load-bearing point, and it is a consequence of the architecture.
Every rule that can lose the account lives in `engine/risk.py` as
deterministic code with tests: position sizing, the 2% budget, the class
caps, the option floor, the halt state machine. A weaker model cannot size a
position more aggressively, cannot skip a stop, cannot trade through a halt.
It can only propose; the engine disposes.

So the Opus→Sonnet question is **not** a safety question. It is a question
about the quality of ideas — regime reading, news triage, thesis
construction — which determines expectancy, which determines whether the
agent makes money at all. That is the right thing to be optimizing, and it
means you can make the cost trade-off on its merits.

## 2. Split the runtime by task, not one model for everything

The agent's day is not one workload. It is two, with very different shapes:

| Job | Frequency | Shape | Recommended |
|---|---|---|---|
| Pre-market research, regime read, thesis construction (`premarket-brief`, `trade-plan`) | 1-2x/day | Open-ended synthesis across noisy conflicting sources; errors compound into every trade that day | **Opus 5, effort `high`** |
| News triage, execution, position management, journaling (`news-intel`, `execution`, `trade-journal`, `session-close`) | many times/day | Rule-following against an explicit checklist with structured output | **Sonnet 5, effort `xhigh`** |
| Weekly review, rule promotion, post-halt post-mortem | weekly / on halt | Deciding what the agent *becomes*; a bad rule promoted here persists | **Opus 5, effort `xhigh`** |

The asymmetry is deliberate. A bad execution turn costs one trade. A bad
rule promoted into a `SKILL.md` costs every trade until someone notices.
Spend the capability where the mistake is durable.

If you want a single model for simplicity, **Sonnet 5 at `xhigh` for
everything, with Opus 5 reserved for the Friday review**, is a defensible and
much simpler configuration. That is close to your original plan and I would
not argue hard against it.

## 3. Use `xhigh`, not `high`

Both Opus 5 and Sonnet 5 support effort `low | medium | high | xhigh | max`.
`high` is the **default** — asking for "Sonnet 5 - High" is asking for stock
Sonnet 5. `xhigh` sits between `high` and `max` and is the recommended
setting for agentic and long-horizon work on this generation; it is Claude
Code's own default.

For the trading loop specifically, `xhigh` on Sonnet 5 is a better use of
budget than `high` on Opus 5 for the routine turns. Reserve `max` for the
weekly review, where correctness matters more than cost and it runs once.

For development — what we are doing now — `medium` is on the low side. This
session's most valuable output was catching that the first ablation was
vacuous and that a hard-coded 45%/2R edge had quietly assumed the conclusion.
That is the kind of error that gets missed at lower effort. Use `high` or
`xhigh` for skill development.

## 4. The change that matters most: validate on what you deploy

Your plan is: build on Opus 5 → validate in Phase 2 → deploy. If Phase 2
runs on Opus and production runs on Sonnet, **Phase 2 measured a different
agent.** The entire point of the paper weeks is to estimate expectancy from
30+ trades; swapping the model that generates the theses invalidates that
estimate, and expectancy is the one number that decides whether any of this
works (`docs/01-feasibility.md`).

So:

1. **Pick the runtime configuration before Phase 2 begins**, and run every
   paper week on exactly that configuration.
2. Treat any later model change as a **config change requiring re-validation**:
   re-run `python3 -m sim.run_suite --seeds 300` and `python3 -m unittest
   discover -s tests` (these pin the engine, which is model-independent, so
   they should be unchanged — if they are not, something else broke), then
   run one shadow week where the new model produces plans that are journaled
   but not traded, and compare its calls to the incumbent's.
3. Record the model, the effort level and the date in every brief and journal
   entry, so a later change in performance can be attributed rather than
   guessed at.

## 5. The economics, stated plainly

Current first-party API pricing: Opus 5 is **$5 / $25** per million input /
output tokens; Sonnet 5 is **$2 / $10**; Haiku 4.5 is **$1 / $5**.

At a $300 account, inference cost is not a rounding error against expected
profit — it is likely larger than it. A realistic year for the disciplined
strategies in simulation was **+$2 to +$9** (`docs/05-sim-report.md`). A
daily research turn with meaningful context does not cost $2 a year.

This does not make the project pointless, but it does change what it is for.
**Until equity is well into four figures, this agent is infrastructure you
are building and validating, not a profit centre.** Judge it on whether the
guardrails hold and whether measured expectancy is positive — those transfer
to a larger account. The P&L on $300 does not.

Practical consequence: if you are running this through a Claude Code
subscription rather than the API, the constraint is your rate-limit budget
rather than dollars, and the same conclusion holds — spend the expensive
turns on the weekly review, not on watching a position tick.

## 6. What I would not do

- **Don't use Haiku 4.5 for trade decisions.** Fine for mechanical feed
  classification if you later need volume; not for anything that sizes or
  selects a position. At this trade frequency the added complexity of a third
  model is not worth the saving.
- **Don't switch models mid-week.** Finish the paper week, then switch, so
  the journal attributes cleanly.
- **Don't reach for a more capable model to fix a losing streak.** If
  expectancy is negative over 40 trades the strategy is wrong, and a better
  model applied to a broken process just loses money more articulately. The
  `trade-journal` skill escalates to you instead.

## Recommendation

| Phase | Model | Effort |
|---|---|---|
| Skill development (now) | Opus 5 | `high`-`xhigh` |
| Phase 2 paper weeks — daily research | Opus 5 | `high` |
| Phase 2 paper weeks — execution/journal loop | Sonnet 5 | `xhigh` |
| Weekly review and rule promotion | Opus 5 | `xhigh`-`max` |
| Phase 3 live | **identical to whatever Phase 2 ran** | same |

If that is more moving parts than you want: **Sonnet 5 at `xhigh` for the
daily loop, Opus 5 at `xhigh` for the Friday review.** Two models, one rule,
and the guardrails do not care either way.
