# Lessons ledger

Every rule in `engine/config.py` and every behavioral rule in a `SKILL.md`
traces back to an entry here. An entry needs a date, evidence, and what
changed. No evidence, no rule — and rules whose evidence does not survive
review get deleted rather than grandfathered.

---

### 2026-09-15 — Options are arithmetically unaffordable below ~$1,500
**Evidence:** `sim/results/suite_default.json`; 9,498 sizing rejections
across 300 simulated years. A 2% budget on $300 is $6; one contract at a
$2.00 premium with a 40% stop risks $80.
**Change:** `RiskConfig.option_min_equity = 1500`; explicit rejection reason;
`test_options_blocked_below_equity_floor`.
**Status:** active.

### 2026-09-15 — Chasing the weekly target locks the account, reliably
**Evidence:** `--options-at-300` run, `target_chaser_CONTROL`: 100% of 300
runs ended in `LOCKED`, median $233.36, 3.2% win rate.
**Change:** `trade-plan` requires expected R ≥ 1.5 and forbids widening risk
to reach a return target; `docs/01-feasibility.md` makes the target a hurdle
rate, not a quota.
**Status:** active.

### 2026-09-15 — Optimizing for "weeks hitting +5%" selects for ruin
**Evidence:** ablation run — unrestrained `option_swing` hit +5% in 13.3% of
weeks (vs 0.6% for disciplined `momentum_breakout`) while ruining 94% of
accounts, median final equity $18.02.
**Change:** the agent's success metric is compounded growth subject to
survival. The weekly hit-rate is reported, never optimized.
**Status:** active. **This is the most important entry in the file.**

### 2026-09-15 — Position sizing does not change how often a week hits +5%
**Evidence:** `engine/feasibility.py` Monte Carlo — 40.7% of weeks clear +5%
at 2%, 5% and 20% risk per trade alike; at 20%, 8.7% of one-year paths go to
zero.
**Change:** `trade-plan` may not increase size to reach a return target. Size
follows the stop, never the ambition.
**Status:** active.

### 2026-09-15 — Never tighten a stop to afford a position
**Evidence:** design review of the sizing path — a narrower stop mechanically
buys a larger position under a fixed risk budget, so "make the stop tighter"
is indistinguishable from "take more risk", while also raising the odds of
being stopped out of a correct thesis.
**Change:** stated as a hard rule in `trade-plan`. If the structural stop is
too wide for the budget, the trade is skipped.
**Status:** active — **not yet backed by trade data.** Re-examine after 30
live paper trades.

### 2026-09-15 — Averaging down is prohibited at this account size
**Evidence:** none yet — this is a prior, not a finding.
**Change:** `trade-plan` permits scaling out only.
**Status:** provisional. Flagged honestly: kept because the downside
(unbounded loss on a $300 account) is not survivable, not because simulation
proved it.

### 2026-09-15 — More capital does not improve returns at this size
**Evidence:** `sim/results/capital_sweep.json`; 150 paths at each of 8 equity
levels from $300 to $10,000. `momentum_breakout` median return was +2.75% at
$300 and +1.67% at $10,000 — flat to declining in capital. Proposals lost to
whole-share rounding: 3.5% at $300, 0.0% from $500 up.
**Change:** initial deposit stays at $300. The "$1,500 milestone" framing from
the Phase 1 report is retired.
**Status:** active.

### 2026-09-15 — Long-premium option buying is negative expectancy here, at every account size
**Evidence:** capital sweep — option_swing median -1.97% at $1,500, -14.01% at
$2,500, -15.00% at $5,000, -14.68% at $10,000. Re-tested at $5,000 across five
stop/target variants (25%/40%/60%/no-stop, 60%/100% targets): every one lost,
from -5.28% to -15.00%. The cause is the implied-vol premium paid on entry
plus two-sided spread, not stop placement.
**Change:** `option_requires_proven_edge = True` — the option sleeve is locked
until the account shows >= 30 closed trades at >= +0.10R measured expectancy.
**Caveat:** only long OTM calls were tested. Debit spreads are a different
structure and remain untested; do not read this as "all options lose".
**Status:** active.

### 2026-09-15 — An affordability floor is not a quality gate (correction)
**Evidence:** the $1,500 `option_min_equity` rule, added the same day, was
derived from "can the account afford one contract" and silently assumed that
affording one made trading it sensible. The capital sweep showed it does not.
An affordability floor alone just delays the losing trade until the account
can lose more.
**Change:** the floor is kept (the arithmetic is still right) and paired with
the proven-edge gate above. With `graduated_swing` at $5,000, the gate cut
option trades from 25.1 to 3.5 a year, improved median return by 11.2
percentage points, and reduced mean drawdown from 19.7% to 11.5%.
**Lesson for future rules:** ask what question a limit actually answers. "Can
I?" and "should I?" need separate gates.
**Status:** active.

### 2026-09-15 — Model routing is a rule, not a preference
**Evidence:** none — this is a design decision, recorded for honesty. The
asymmetry it encodes is real: a bad execution turn costs one trade, a bad rule
promoted into a SKILL.md costs every trade until someone notices.
**Change:** `engine/model_policy.py` states the task -> model mapping as data
and `tools/model_check.py` enforces it. Routine-loop tasks warn and continue
on a downgrade; rule-promotion, weekly review, post-halt review and unlock
authorization BLOCK on anything below Opus tier.
**Status:** active, unmeasured. Revisit once there is a paper-trading record
on each configuration — if Sonnet's plans grade as well as Opus's over 30+
trades, the routine-loop floor could come down further.
