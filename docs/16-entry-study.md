# Chase or wait for the retest? (D-24 / M-2)

> **SUPERSEDED IN PART, 2026-09-22.** Everything below was computed on 2026
> alone. The bar cache now runs 2021-2026 and the headline conclusion does not
> survive: **retest beat chase in exactly one of six years, and that year was
> 2026.** The decomposition at the end of this file is what replaced it and is
> the part worth reading. See "Six years" below before acting on anything in
> the middle sections.

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


---

# Six years (2021-2026) — what survived, what did not

```
python3 -m tools.pit_study --fetch          # 2020-07-01 on, 2472 symbols, 51MB
python3 -m tools.multiyear                  # entry study, every year
python3 -m tools.multiproxy                 # the six features, every year
```

The IEX feed on this plan begins 2020-07-27. Taking all of it gives six study
years once the 200-day lookback is paid. 0 batches dropped in the fetch.

## 1. The retest result was a 2026 artifact

| year | signals | chase | retest | never pulled back (chased) |
|---|---|---|---|---|
| 2021 | 1,454 | **+0.054** | −0.012 | +0.891 (t=7.2) |
| 2022 | 2,110 | **−0.168** (t=−4.9) | −0.189 | +0.571 (t=6.5) |
| 2023 | 2,872 | **+0.159** | +0.157 | +0.997 (t=12.5) |
| 2024 | 2,805 | **+0.194** | +0.158 | +1.040 (t=11.2) |
| 2025 | 2,796 | **+0.178** | +0.170 | +1.034 (t=10.4) |
| 2026 | 1,875 | +0.060 | **+0.093** | +1.068 (t=9.2) |

Retest won in 1/6 years. Sign test p=0.219; paired t=−1.2. The difference is
not significant in either direction — but the *direction this file reported*
is the wrong one out of sample.

Worth recording as a process failure, not just a data update: my prior before
the 2026 study was that chase would win. The one-year result reversed it, I
wrote the reversal up, and six years says the original prior was right. **A
single year did not merely fail to confirm — it actively pointed the wrong
way, and it was confident enough to make me correct a correct instinct.**

## 2. The t-statistic this file should never have quoted

Pooled over all 13,912 chase trades: +0.096R at **t=5.6**. That number is
wrong to use. Trades inside one year share the same market, so they are not
13,912 independent draws and the pooled SE is far too small.

**Each year as one observation: chase +0.079R, sd 0.135, t=+1.4.** Six years,
2,472 symbols, daily bars — and the edge is still inside the noise. Every
future claim here quotes the year-level figure.

## 3. The decomposition — the part that is actually robust

The retest arm's fills and the chase arm's non-missed trades are the *same
10,117 signals*, so the gap attributes exactly:

```
signals that later pulled back, CHASED :  10117 trades  -0.227R  (-2299.6R)
the same signals, entered on the RETEST:  10117 trades  +0.078R  ( +788.3R)
   -> waiting is worth +0.305R on the signals it fills
signals that never pulled back, forfeited: 3795 trades  +0.957R  (+3631.6R)
   -> that forfeit is the whole of retest's shortfall
```

Both halves hold in **all six years**, 2022 included, where the no-pullback
group returned +0.571R in the year every other arm lost money. Year-level
t=12.1 — the only result in this study that clears significance comfortably.

**So: waiting for the pullback is the better entry on the trades it gets, and
loses anyway because it forfeits the trades that never come back.** The entry
style was never the error. Having to choose between the two groups at signal
time is the error, and it is structural.

## 4. Can anything at signal time tell the groups apart? Still no.

The 2026 negative result generalises. Test: does the Q5−Q1 spread in chase
return keep its *sign* year after year — not whether the pooled average is
positive.

| feature | mean Q5−Q1 R | year-level t | sign held | label Q5−Q1 |
|---|---|---|---|---|
| atr_% | +0.185 | 1.8 | 4/6 | +0.03 |
| breakout_% | +0.165 | 1.8 | 5/6 | **+0.40** |
| rel_volume | +0.143 | 1.4 | 5/6 | +0.19 |
| gap_% | +0.051 | 1.0 | 4/6 | +0.34 |
| dist_200ma_% | +0.078 | 0.5 | 3/6 | +0.02 |
| dist_50ma_% | +0.012 | 0.1 | 2/6 | +0.06 |

**Nothing clears the year-level bar.** Best is t=1.8 at 4/6 and 5/6
consistency, which is not evidence under the standard in CLAUDE.md.

The capture test shows *why*, and it is the same cancellation as 2026. If a
feature worked purely by selecting no-pullback signals, its return spread
would be (label spread) × (+0.957 − −0.227) = (label spread) × 1.184:

| feature | label Q5−Q1 | predicted R spread | observed | captured |
|---|---|---|---|---|
| breakout_% | +0.398 | +0.471 | +0.165 | **35%** |
| gap_% | +0.339 | +0.402 | +0.051 | **13%** |
| rel_volume | +0.191 | +0.226 | +0.143 | 63% |
| atr_% | +0.029 | +0.035 | +0.185 | 532% |
| dist_200ma_% | +0.018 | +0.022 | +0.078 | 364% |

And the mechanism, within the no-pullback group alone:

```
breakout_%   Q1 +1.160   Q5 +0.797   spread -0.363   negative in 4/6 years
rel_volume   Q1 +0.958   Q5 +0.887   spread -0.071   negative in 1/6 years
atr_%        Q1 +0.734   Q5 +1.076   spread +0.342   negative in 3/6 years
```

breakout_% selects the right group and then the *worst members of it* — it
buys the breakouts that have already made the move. Six years confirms what
one year suggested.

The two features that "capture" over 100% (atr_%, dist_200ma_%) are not
working through this mechanism at all; their label spread is ~0. Whatever they
do is a separate and weaker effect.

### A hypothesis I had and was wrong about

I expected atr_%'s spread to be an artifact of the stop floor:
`stop = max(entry − 1.5·ATR, entry×0.92)` means that above atr_% ≈ 5.33 the
floor binds, the stop is tighter than 1.5 ATR, and R is measured against a
denominator the trade never chose. Checked it:

```
floor-bound across all trades: 6.6%
  all trades         n=13912   Q1 -0.040  Q5 +0.146  spread +0.186
  floor never bound  n=12989   Q1 -0.031  Q5 +0.187  spread +0.218
```

Removing every floor-bound trade makes the spread *larger*. Not an artifact.
It is still only t=1.8 at 4/6, so it changes no rule — but the reason to
reject it is weakness, not arithmetic.

## 5. The finding that belongs in the risk rules, not the docs

**2022 chase: −0.168R over 2,110 signals, t=−4.9, −355R total.** A long
breakout strategy loses steadily and *significantly* in a bear year. Studying
2026 alone hid a regime dependency larger than the edge itself — the spread
between the worst year and the best is 0.36R, while the six-year mean is
0.079R.

This is the strongest argument yet for a regime gate that is code rather than
posture prose, and it is queued as such. No rule changes on it today.

## Standing caveat

The universe is built from `/v2/assets` as it stands today, so names delisted
before today are absent. Symbol counts rise monotonically — 1,944 names with
bars in 2021 to 2,471 in 2026 — which is delistings and IPOs mixed and cannot
be separated from this data. Every year is biased upward and the early years
more. Treat an edge that *grows* into the past as suspect for that reason
alone; 2022 being the worst year is, if anything, understated.
