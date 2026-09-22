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
