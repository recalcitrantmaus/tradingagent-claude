# Tuesday 2026-09-22 — queue (T-n)

Numbered T-1.. per the convention agreed after four parallel sessions collided
on one M-n list. Do not renumber Monday's M-n items.

Findings from an attended bug session with the market open, after M-22/M-26,
M-29 and M-30 were fixed and pushed. Six end-to-end scenarios run live.

---

## T-1 — No aggregate open-risk cap. HIGH.

Per-trade risk is capped at 2%. Concurrency is capped at 4. **Nothing caps
the sum**, so the book can carry 8% of equity at risk simultaneously.
Measured, not inferred — four proposals each engineered to the full per-trade
budget:

```
SYM0 APPROVED 1   open risk $ 6.00 ( 2.0%)
SYM1 APPROVED 1   open risk $12.00 ( 4.0%)
SYM2 APPROVED 1   open risk $18.00 ( 6.0%)
SYM3 APPROVED 1   open risk $24.00 ( 8.0%)
SYM4 REFUSED      already at max 4 positions

MAX SIMULTANEOUS OPEN RISK: 8.0%   daily halt 4%   weekly halt 8%
```

**That is 2x the daily halt and exactly 1x the weekly halt, reachable in one
correlated move.** And the breakers cannot help: `daily_loss_halt_pct` stops
NEW trades once -4% is realised; it cannot unwind stops already resting on the
book. By the time it fires, the remaining exposure is still live.

This is not theoretical. Today's five real signals, run through the engine
with the portfolio actually updating, took four positions totalling **4.53% of
equity at risk — already above the 4% daily breaker** — without a single gate
objecting.

`class_caps` caps aggregate NOTIONAL by asset class (equity 90%). Nothing
anywhere caps aggregate RISK.

Needs an attended decision: is 8% the intended ceiling? If it is, the daily
breaker at 4% is mis-set relative to it and should be understood as a
post-hoc marker rather than a limit. If it is not, the cap belongs in
`engine/config.py` with a test, and the sim should be re-run for ruin rate
before and after.

## T-2 — No sector or correlation constraint, and the screen selects FOR correlation. HIGH.

Today's six breakout signals, names from `/v2/assets`:

```
ASX    ASE Technology Holding Co., Ltd.        semiconductor assembly & test
STM    STMicroelectronics N.V.                 semiconductors
DRAM   Roundhill Memory ETF                    an ETF OF memory semiconductors
MCHP   Microchip Technology Incorporated       semiconductors
JEPQ   JPMorgan Nasdaq Equity Premium Income   Nasdaq-concentrated
RKLB   Rocket Lab Corporation                  space
```

**Four of six are semiconductors.** The engine's first four approvals were
ASX, STM, DRAM and RKLB — three semis and one space name. `class_caps`
distinguishes only equity / option / crypto, so an ETF of semiconductors is
"equity", the same as anything else.

This compounds T-1 rather than sitting beside it. A 20-day breakout screen
does not draw independent samples: it selects whatever sector is running, so
on any given day the candidates are correlated by construction. "Four
independent trades at 2%" is, in practice, one sector bet in four wrappers —
and the 8% ceiling in T-1 is therefore 8% on a single factor, not 8% spread.

The strategy's own history says the same thing: 2022 chase was -0.168R at
t=-4.9 (`docs/16-entry-study.md`), i.e. this strategy loses when its factor is
out of favour. A correlated book is exactly how that year hurts.

## T-3 — The universe price ceiling is enforced against a stale close. LOW.

MCHP made the universe on a prior-session close at or under $75, then traded
75.67 live and produced a signal. The engine refused it correctly — *"size
rounds to zero; binding constraint: single-position cap"* — so no risk
reached the account. But the screen spent the work and the signal list
carries a name that can never be sized. Filter the live price against
`max_price` in `screen()`, or note the ceiling is a build-time property.

## T-4 — `min_expected_r` cannot fire on the mechanical path. LOW.

`propose_mechanical` sets `stop = px - 1.5*ATR` and `target = px + 3*ATR`, so
expected R is **exactly 2.00 by construction** — every proposal today printed
`expected R 2.00` — and higher when the -8% stop floor binds. The
`min_expected_r = 1.5` gate can therefore never reject a mechanical proposal.

Not a bug. The gate is real and load-bearing for PLAN proposals, where it
refused VKTX at 0.22R and ONON at 0.78R this morning. But a gate that cannot
fail on a path should be known not to be protecting that path, or it reads as
coverage that is not there.

## T-5 — Duplicate live-price implementations. LOW.

`tools/smoke_submit.last_price()` and the new `AlpacaAdapter.last_trade()`
now do the same job with different fallbacks. One of them will drift.
Consolidate on the adapter.

## T-6 — `screen()` doubled its request count. LOW, performance only.

Splitting level from price (M-30) added one `last_trade()` call per symbol, so
a 150-name scan is now ~300 requests instead of ~150. Correct but wasteful;
`/v2/stocks/snapshots` takes 500 symbols per call and would make it ~150 + 1.

---

## What PASSED, recorded so a quiet result is not mistaken for no result

- **`trading_day open` is idempotent.** Run a second time at 16:18Z after the
  13:45Z firing: re-anchored cash, appended one bounded history row, drift
  0.0000, no corruption.
- **`smoke_submit` clean.** Whole-share bracket ACCEPTED with 2 legs
  (`limit 13.36`, `stop 10.46`), both fractional probes rejected 422 —
  "must be DAY orders" and "must be simple orders" — cleanup left nothing
  resting and no position. **D-17 reproduced a third time.**
- **The screen works on the split feed.** RKLB now measured against the
  consolidated 71.21 rather than the IEX 70.56.
- **The risk engine refused what it should.** MCHP on the position cap, the
  5th signal on max concurrency. The model proposed; the code disposed.
- **The empty plan held.** `paper_session` read `[]` and did not fall back to
  the scanner.

## Still unverified after two days

Zero fills, ever. B-15 (fills.jsonl carries the broker's price), B-16 / M-20
(a bracket leg promoted from `held` to `new` by a parent fill, with its TIF)
and M-16 (`trading_day preclose` live) all remain untested, and no amount of
refusing trades will test them.
