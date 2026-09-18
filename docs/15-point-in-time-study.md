# Point-in-time rebuild: the edge was mostly survivorship

**The 20-day breakout strategy has no statistically significant edge in 2026
once the universe is rebuilt without hindsight. Inverse ETFs do not fix it,
and they fail hardest in exactly the quarter where the long side fails.**

```
python3 -m tools.pit_study --fetch                       # ~500 requests, cached
python3 -m tools.pit_study --year 2026 --top 150         # like-for-like
python3 -m tools.pit_study --year 2026                   # all eligible names
python3 -m tools.pit_study --year 2026 --inverse
```

## What changed in the method

`docs/14-target-study.md` screened `data/universe.json` — 150 names selected by
price and liquidity **as of 2026-09-17** — and then backtested January. A stock
that was $40 in January and $200 today was excluded from its own January
signals, and for a breakout strategy those are the trades the edge lives on.

This run rebuilds eligibility **at each signal date** from the full tradable
list (13,169 names, 1,826 with enough 2026 history to matter):

```
eligible(sym, i)  <=>  3 <= close[i] <= 75
                  and  median 20-day dollar volume up to i >= $1.5M (IEX)
```

Everything else — entry at the next open, gap-aware stop fills, stop-first on
ambiguous bars, levels computed only from `bars[:i+1]` — is unchanged.

## The result, and the decomposition that explains it

Expectancy in R, 20-day horizon, with standard errors:

| arm | old universe (150, as of today) | point-in-time, **top 150/day** | point-in-time, **all 1,563** |
|---|---|---|---|
| mechanical | +0.032 (t +0.9) | −0.010 (t −0.3) | −0.033 (t −1.6) |
| struct_swing | +0.050 (t +1.1) | +0.009 (t +0.2) | −0.068 (t −2.0) |
| struct_coarse | +0.079 (t +1.0) | +0.041 (t +0.5) | −0.059 (t −0.9) |
| **none** | **+0.132 (t +2.7)** | **+0.054 (t +1.1)** | **−0.014 (t −0.6)** |
| signals | 1,983 | 1,881 | 13,506 |

Two separate effects were tangled together, and the middle column separates
them. The old universe was not merely "surviving" — it was also `size: 150`,
the *most liquid* eligible names. So:

- **Liquidity selection is real and large.** Across all 1,563 eligible names,
  every arm is negative. Restricting to the 150 most liquid *on each day*
  brings them back to roughly break-even. The strategy has no business in the
  broad tail of the eligible market.
- **Survivorship was worth roughly 60% of the measured edge.** Like-for-like —
  top 150 by liquidity in both — the best arm falls from +0.132R to +0.054R,
  and from t = +2.7 to t = +1.1.

**After correction, nothing in the study is statistically significant.** The
largest |t| across every arm and universe is 1.6. The *ranking* holds up
(no-target > coarse structure > swing structure > mechanical, in that order in
both corrected columns), so the conclusion in doc 14 — that targets cost money
and structural targets cost the most — survives. The claim that any of this
constitutes a measured edge does not.

## Inverse ETFs: no

Tested on 14 hand-verified 1x inverse funds (AAPD, AMDD, AMZD, AVS, BITI, DOG,
GGLS, MSFD, MUD, PLTD, PSQ, RWM, SH, SPDN), 106 breakout signals in 2026:

| arm | taken | expectancy | ±SE | t | total R | win% |
|---|---|---|---|---|---|---|
| mechanical | 106 | −0.592 | 0.109 | **−5.4** | −62.8 | 21% |
| struct_swing | 28 | −0.904 | 0.092 | **−9.9** | −25.3 | 11% |
| none | 106 | **−0.815** | 0.080 | **−10.2** | −86.4 | 15% |

This is the strongest statistical result in the entire study and it points the
wrong way. Buying a breakout in an inverse fund means buying it *after* the
market has already fallen — late, into a daily-reset instrument that decays.

And the part that actually answers the question that prompted it:

| arm | Q1 | Q2 | Q3 |
|---|---|---|---|
| mechanical | −0.810 (47) | −0.417 (22) | **−0.421 (37)** |
| none | −1.040 (47) | −0.750 (22) | **−0.569 (37)** |

**Inverse ETFs are negative in Q3 too** — the quarter where the long side
loses money. They are not a hedge for this strategy's weakness; they are a
second way to lose in the same conditions.

A caution on the sample: the name-substring classifier first used here matched
BIGBEAR.AI, MAPLEBEAR and three short-*duration bond* funds as "inverse". The
table above uses a hand-verified list instead. The contaminated run was also
strongly negative, so the conclusion does not rest on the cleaning — but an
automated classifier that returns Instacart when asked for inverse ETFs is
worth remembering.

## Q3 2026 is the open problem, on both sides

Long side, point-in-time top 150: Q1 +0.134, Q2 +0.219, **Q3 −0.278** (no-target
arm). Inverse side: negative in all three. Whatever changed in Q3 broke
breakout trading in this universe, and buying the other direction did not help.

The account has no regime detector, and this is the second study to say the
same thing.

## What follows

1. **Do not treat the no-target arm as a proven edge.** It is the best of the
   options tested and it is not distinguishable from zero. Adopting it is a
   decision to stop paying an identified cost (targets), not to collect a
   measured gain.
2. **Keep the liquidity cap.** `size: 150` in `tools/screen.py` is not a
   convenience, it is load-bearing: the same strategy on the broad eligible
   universe is negative across every arm.
3. **No inverse sleeve.** The evidence is strongly negative and worst where it
   would be needed.
4. **Regime, not instrument, is the next question.** Three arms, two
   directions, one year — and everything fails in the same quarter.
5. **Costs are still excluded.** ~0.013R per trade, against a best-case
   +0.054R. That is a quarter of the remaining number.
