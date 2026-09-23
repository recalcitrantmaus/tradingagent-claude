# Wednesday 2026-09-23 — queue (T-n, continuing Tuesday's numbering)

Session: `claude-opus-5`, effort **high** against an `xhigh` floor (see T-15).
Account $299.99, flat at open, risk state NORMAL, cash drift 0.0000.

---

## Fixed today

### T-12 — the taper and the 4% book cap were both inert within a session. HIGH. FIXED.
`tools/paper_session` never updated the portfolio between proposals, so every
proposal was gated as position 1 against an empty book. Four proposals could
carry 5.6% of equity at risk against a 4% cap. Full write-up in
`docs/04-lessons.md`. Fixed + 9 tests in `tests/test_session_gating.py`.

### T-13 — every refusal logged the wrong constraint. HIGH. FIXED.
`Decision.reject` appends; the runner printed `reasons[0]`. RKLB's refusal on
the tapered budget was logged as `expected R 2.00`, a passing grade. Fixed to
`reasons[-1]`, pinned both ways.

### T-14 — carried positions rebuilt without their resting stops. HIGH. FIXED.
`open_risk` counted a stopped position at full notional, so one filled DT
share would have frozen all new entries the next session behind a message that
reads like a working guardrail. Added `AlpacaAdapter.resting_stops()`; verified
live (`{'DT': 55.8}`). Fail-closed behaviour kept and tested.

---

## Open

### T-15 — `preflight_phase2` reports the DECLARED effort, not the real one. MEDIUM.

```
preflight_phase2 :  [ok ] model routing   effort xhigh; model reads claude-sonnet-5 from an ENVIRONMENT default...
model_check      :  EFFORT MISMATCH: harness reports 'high', TRADING_AGENT_EFFORT declares 'xhigh'.
```

Preflight printed `effort xhigh` and a green `[ok]` while the harness was
actually running `high`. `model_check` reads the harness and got it right;
preflight reads `TRADING_AGENT_EFFORT` and echoed the declaration back.

This is **M-22/M-26 exactly** — a gate answering a per-session question from an
environment constant — surviving in the one tool whose whole job is to say
whether the session is fit to trade. Preflight already knows to distrust the
environment for the *model* (it says so in its own output, in that same line).
It does not apply the same distrust to *effort*.

Both open tasks were non-blocking on a downgrade, so nothing was blocked today.
The failure mode is a **blocking** task — weekly-review, rule-promotion,
post-halt-review — passing preflight while under its floor.

Fix: have preflight call the same code path `model_check` uses, and report the
harness value with the declaration as a mismatch note.

### T-16 — the Yahoo cross-check is intermittent, and it is the only independent leg. MEDIUM.

Measured today: HTTP 429 on 3 of 5 symbols on the first pass, then 429 on
everything for several minutes, succeeding on retry in between.
`query2.finance.yahoo.com` is **403 at the proxy** — not in the network policy
— so there is no alternate host. `preflight_phase2` logged it as
"cross-check unavailable (AdapterError) — not a blocker".

CLAUDE.md says never to trade on a single unverified price, and Yahoo is the
only thing making a price not-single. A rate-limited cross-check is a
cross-check that is absent exactly when a session is doing a lot of work,
which is when it is most needed.

Both names traded today WERE verified (DT 0.0 bps, RKLB 1.4 bps, 13:52Z) before
the rate limit set in. That was luck of ordering.

Options, none taken today: add `query2` to the network policy; back off and
retry inside `cross_check` rather than raising on the first 429; or add a
genuinely different second source. Note the consolidated SIP daily bar is a
usable *third* reading — different feed from the IEX snapshot `last_trade`
uses — and today it corroborated both names to within 2 and 7 bps. It is 15
minutes delayed, so it is a sanity check, not a substitute.

### T-11 — the screen has no minimum breakout depth. LOW. RECOMMENDED, NOT APPLIED.

RKLB qualified today at **0.16 ATR** above its 20-day close-high; DT at 0.71
ATR. A 0.16-ATR penetration is inside a single day's noise, and RKLB
round-tripped 72.74 -> 72.52 -> 72.53 while the plan was being written.

Recommending a minimum penetration depth in ATR units in `CRITERIA`
(`tools/screen.py`) rather than applying one, because a filter that lives only
in a session cannot be checked by anyone, and because the evidence CLAUDE.md
requires for a rule change — five consistent closed trades, or a backtest with
a better median and no worse ruin rate — **does not exist: this account has
zero closed trades.** It needs a backtest, not an opinion.

### Carried from Tuesday, untouched today

T-3 (universe price ceiling checked against a stale close), T-5 (duplicate
live-price implementations — `tools/smoke_submit.last_price` vs
`AlpacaAdapter.last_trade`), T-6 (`screen()` doing ~300 requests where
`/v2/stocks/snapshots` would do ~151). All LOW. T-4 (the `min_expected_r` gate
cannot fire on the mechanical path) is documentation, not a defect.

---

## Today's trading, for the record

| | |
|---|---|
| screened | 150-name committed universe, 149 scanned, 1 no history |
| signals | 2 — DT, RKLB |
| proposed | 2, ordered by conviction (ATR-depth through the level: DT 0.71, RKLB 0.16) |
| approved | **DT**, 1 share @ limit 58.47, stop 55.80, target 63.81, risking $2.67 = 0.89% of equity |
| refused | **RKLB** — `size rounds to zero; binding constraint: per-trade risk budget tapered to 1.00% as position 2` |
| filled | **none.** DT rests at the broker, order `99ebcbc4-36b2-4a63-b491-1265ea81b315`, status `new`, bracket with both legs `held` (TP 63.81, stop 55.80, both GTC) |
| cash drift | **0.0000** |

The ordering decision was written down before the engine was run, and it is
the reason RKLB was refused: ranked the other way round, both would have fit.
That permutation was available and was not taken. See
`state/plans/2026-09-23.md`.

DT's limit was not re-priced when the stock ticked from 58.47 to 58.62 during
the bug fix. The order rests or it does not.

## Still unverified after three days

**Zero fills, ever.** B-15 (fills.jsonl carrying the broker's
`filled_avg_price`), B-16/M-20 (a bracket leg promoted `held` -> `new` by a
parent fill, TIF verbatim) and M-16 (`trading_day preclose` live) remain
untested. Today got one step closer than the previous two days — a real
bracket is resting at the broker with both legs `held`, which is B-16's
precondition — and no closer to a fill.

---

# Pre-close addendum — 15:30 ET

## Verified today (both fixes re-evaluated under real conditions)

### B-15 fill recovery — HOLDS on a second run.
`tools.trading_day preclose` run again at 19:31Z. `state/fills.jsonl` is
**byte-identical** (md5 `697b2842456595384a656b043ee2b727` before and after),
still exactly one buy and one sell with `dry_run: false`, activity_ids unique.
Dedupe on `activity_id` works. `tools.review` shows 1 closed trade at
**-0.139R**. Cash drift **$+0.0000** across 5 reconciliations — no $58.47 drift
reappeared. `trading_day preclose` exit code **0**; cancelled **nothing**
("none resting"), correct on a flat book. M-16 has now run live.

### Stop fix — returns `{}` on a flat book, which proves almost nothing.
`positions_with_unconfirmed_stops()` -> `{}`, `positions_without_stops()` ->
`[]`, `resting_stops()` -> `{}`. **Said plainly: today produced no live
evidence either way.** The book was flat from 14:28Z onward, so the control was
never asked the question it exists to answer. A green result from a control
with no input is the vacuous-pass family this repo has now logged four times.

---

## T-17 — the `held` stop leg was probably live, and flattening cost 0.371R. HIGH. OPEN.

**The cost is larger than it looked at 15:00.** The routine recorded DT at
58.27 and put the cost of the flatten at ~0.064R. DT closed at **59.09** (SIP
consolidated; session 57.54 / 59.31 / 57.39 / 59.09):

```
realised (flattened at 58.10)    -0.139R
counterfactual (held to 59.09)   +0.232R
-----------------------------------------
cost of the flatten               0.371R
```

Nearly 3x the loss actually taken, and it converted a winning trade into a
losing one. The stop at 55.80 was **never within $1.59** of the session low.

**Alpaca's documentation appears to explain the `held` reading.** From
https://docs.alpaca.markets/us/docs/orders-at-alpaca (fetched today, HTTP 200
— the host is **NOT** blocked by this environment's egress policy, contrary to
the note in the routine; `alpaca.markets/docs/...` is 403 at the proxy, but
`docs.alpaca.markets` resolves and serves):

> "The first order is used to enter a new long or short position, and **once
> it is completely filled, two conditional exit orders are activated.**"

> "Note that when you retrieve the list of orders with the nested parameter
> true, **the take-profit order shows up as the parent order while the
> stop-loss order appears as a child order.**"

That is precisely the shape observed: at the parent's fill the take-profit was
(re)submitted at 14:04:57 and went `new`, while the stop leg kept its original
13:59:22 submission timestamp and reported `held`. Read together, `held` looks
like **the documented representation of a live OCO child**, not an inert order.

**NOT asserted as settled, and deliberately left open.** No page in Alpaca's
reachable documentation defines the `held` status string — searched
`orders-at-alpaca`, `working-with-orders`, and the `alpaca-py` `OrderStatus`
enum, which lists `HELD = "held"` with no semantics. Today's data cannot close
it: both legs are now `canceled`, so their live status can no longer be read,
and the stop was never near enough to prove itself by triggering.

**Nothing was changed.** The control is wrong in the *safe* direction, and
loosening a protection is exactly the change an unattended session must not
make on one observation. `model_check rule-promotion` exited **1** — refused
for want of an authorization, and none was written.

**How to settle it for ~$0:** the next time a bracket parent fills, query the
stop leg by its own order id and record `status`, `order_class`, and whether it
appears as an independent row in `GET /v2/orders`. Two or three observations
decide it deterministically, riding on trades taken for their own reasons.

**Why this is urgent despite being safe-direction:** if the stop *is* live,
this control will flatten **every** bracket position this account ever opens,
at a cost of roughly 0.37R each on today's evidence. That is not a guardrail;
it is a systematic bleed with a guardrail's error message — and a -0.139R
expectancy built from trades exited that way measures our plumbing, not our
edge.

## T-18 — "costs below gains" passes vacuously on a losing account. LOW. OPEN.

`trading_day week` prints:

```
  [ok] costs below gains          $0.00 vs $-0.37
```

$0.00 is not below -$0.37. The test is `costs <= max(net, 0)`, so with net
negative it reduces to `costs <= 0`, which zero-commission paper trading always
satisfies. The criterion is defensible as written — no costs means costs are
eating nothing — but the **displayed line asserts a false comparison** and
reads green on a losing week.

This is the T-8 family again (a criterion that passes vacuously and gets
repeated in a summary without its denominator), surviving in a criterion T-8
itself rewrote. Suggest it report a third state — *not measurable while net
<= 0* — rather than `[ok]`. Not changed here: exit criteria are rule-adjacent
and this session is unattended.

---

## Day's numbers

| | |
|---|---|
| equity | **$299.62** |
| day | **-0.12%** |
| week | **-0.12%**, gap to the +5% hurdle **-5.12%** |
| since inception | -0.13% |
| drawdown from peak | 0.13% |
| closed trades | 1 (0W / 1L), net -$0.37, expectancy **-0.139R** |
| costs | $0.00 |
| cash drift | **$+0.0000** across 5 reconciliations |
| risk state | NORMAL |
| carried overnight | none — flat |
| escalations | none |
| Phase 2 exit criteria | 3/5 (30+ trades 1/30; expectancy -0.139R) |

`trading_day close` exit 0; `trading_day week` exit 1 (criteria unmet, not an
error).

**On the expectancy figure:** -0.139R over one trade, and that one trade was
exited by a control rather than by the market. It is a measurement of our
software, not of the strategy. It should not be cited as evidence about 20-day
breakouts in either direction.
