# Chase or wait for the retest? (D-24 / M-2)

**Waiting is modestly better, not worse — but neither is significant, and the
signals the retest never fills are the best ones in the sample.**

```
python3 -m tools.entry_study --year 2026 --top 150 --wait 5
```

## The question

Monday 2026-09-21: the plan found a real signal in ETHA, rested a limit at the
broken level rather than chasing 2% higher, and never filled. ETHA closed
+4.8%. The thesis was right about direction and the account collected none of
it. One observation settles nothing, so: same signals, same universe, same
stop rule, no target, 20-day horizon from the fill.

- **chase** — buy the next open, whatever it is
- **retest** — rest a limit at the prior 20-day high (the level that broke);
  fill only if price trades back to it within 5 sessions, else no trade

## Result, 2026, point-in-time top-150 universe

| entry | taken | fill% | expectancy | ±SE | t | total R | win% |
|---|---|---|---|---|---|---|---|
| chase | 1881 | 100% | +0.054 | 0.048 | +1.1 | +102.4 | 31% |
| **retest** | 1398 | **74%** | **+0.092** | 0.054 | +1.7 | **+128.6** | 33% |

**The retest arm is better on both measures** — higher expectancy per trade
*and* higher total R despite taking 26% fewer trades. My prior going in was
that waiting would anti-select, the way the structural filter did. It does
not. A breakout that pulls back gives a materially better entry, and the same
stop rule then risks less per share for the same move.

Neither arm is statistically significant (t = 1.1 and 1.7). This ranks the two;
it does not establish that either has an edge.

## The part that matters more than the ranking

**483 signals (26%) never traded back to the level. Chasing those same
signals instead returns +1.054R expectancy, +508.9R total, 56% win rate** —
against a +0.054R average for chasing everything.

So the forgone set is not average. It is roughly twenty times better per
trade than the arm's own mean, and it is the single strongest sub-population
in the study.

**This does not mean "chase instead."** Chasing all 1,881 is the +102.4R
column, worse than waiting. The +508.9R is a hindsight number: you can only
collect it by knowing at signal time which breakouts will not pull back, and
a wait-then-chase rule cannot — after five sessions of waiting the entry is
gone. The two facts sit together honestly:

- among signals that *do* pull back, the retest entry is much better than
  chasing them (chasing that same 1,398 returns roughly **−406R**)
- among signals that *don't*, everything good happens and the retest arm is
  absent

Which is the same sentence from both ends: **pulling back to the broken level
is evidence the breakout failed.** The retest rule is, in effect, a filter
that keeps the weak breakouts and discards the strong ones, and it still wins
because its entry on the weak ones is so much better.

## What follows

1. **Keep the retest entry.** It is ahead on the evidence available, and
   Monday's non-fill was the modal case of the 26%, not bad luck.
2. **The prize is a signal-time proxy for "this one will not pull back."**
   That sub-population carries +1.054R. Candidates that are knowable on the
   signal bar and cost nothing to test: the size of the breakout (close vs
   prior high), the gap from the prior close, relative volume, distance from
   the 20-day high to the 50- or 200-day average. If any of them separates
   the 483 from the 1,398 ex ante, it is worth more than the entry question.
3. **Do not treat this as settled.** t = 1.7, one year, one universe, costs
   excluded (~0.013R/trade), and the whole comparison rests on a 5-session
   wait that was chosen and not tuned. `--wait` is a parameter; nobody has
   swept it.
4. **The live account has one data point** and it agrees with the hindsight
   half: ETHA did not come back, and the day's return went uncollected.

---

# The signal-time proxy: answered, and the answer is no

`python3 -m tools.proxy_study --year 2026 --top 150 --wait 5`

The +1.054R sitting in the no-pullback group is only collectable if something
visible on the signal bar separates it in advance. Six candidates, all
computed from `bars[:i+1]`, against the 2026 signals:

| feature | no-pullback rate, Q1 → Q5 | predicts the label? |
|---|---|---|
| **breakout %** (close above the prior 20-day high) | 12% → **47%** | **strongly** |
| **gap %** (next open vs signal close) | 11% → **48%** | **strongly** |
| relative volume | 24% → 34% | weakly |
| distance to 50-day MA | 27% → 28% | no |
| distance to 200-day MA | 27% → 28% | no |
| ATR % of price | 21% → 28% | no |

**Two of them predict the label very well.** A signal that clears its 20-day
high by more than 2.5%, or gaps up more than ~1%, is roughly four times as
likely never to come back as one that barely clears.

**And it buys nothing.** The top breakout quintile returns **+0.053R** when
chased — the baseline, to three decimals.

## Why it cancels

The feature that identifies "will not pull back" also identifies "and will
not pay as much." Within the no-pullback group alone, breakout size predicts
chase R **negatively**:

| within no-pullback only | breakout % | n | chase R |
|---|---|---|---|
| Q1 | 0.01 – 0.67 | 96 | **+1.473** |
| Q2 | 0.67 – 1.25 | 96 | +1.357 |
| Q3 | 1.25 – 2.35 | 96 | +0.901 |
| Q4 | 2.36 – 4.00 | 96 | +0.810 |
| Q5 | 4.09 – 23.14 | 99 | **+0.736** |

The arithmetic is exact:

```
chase R | never pulled back : +1.054  (n=483)
chase R | did pull back     : -0.291  (n=1398)

top breakout quintile        : 47% never pull back
predicted by naive mixture   : +0.348
ACTUALLY observed            : +0.053
```

A mixture argument says selecting the top quintile should nearly seven-times
the baseline. It does not, because the two effects run against each other and
very nearly cancel. **The label is predictable. The return is not.**

That is economically sensible rather than a data artifact: a large breakout
has already made much of the move. It is less likely to give the level back
*and* has less room left to run. You cannot buy the first property without
paying for the second.

## What this settles

- **Do not build a feature-based entry filter on these six.** It would look
  well-motivated, backtest to baseline, and add a parameter to tune.
- The retest entry stays, on the docs/16 result above.
- The +508.9R remains a hindsight number. It is not a missed opportunity, it
  is a description of a subgroup that cannot be identified in advance by
  anything tested here.
- **Untested and still open:** features not in this list — news, sector
  breadth, the market's own trend on the signal day, earnings proximity. The
  negative result covers price and volume geometry, which is the cheap half.
