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

### 2026-09-15 — A broken data path reports itself as a quiet market
**Evidence:** `AlpacaAdapter.bars()` sent `limit` and `timeframe` but no
`start`. Alpaca defaults `start` to the beginning of the current day, so every
call returned exactly **one** bar regardless of the limit asked for.
`propose_mechanical` requires 21 bars to compute an ATR and a 20-day high, so
it skipped every symbol and printed "no proposals today. An empty plan is a
valid outcome." That sentence is true in general and was false here — the
pipeline had not looked at a single day of history. A first autonomous session
would have run a full day, traded nothing, and reported a clean result.

Widening the window exposed a second trap: `limit` truncates from the *start*
of the range, not the end. A 60-bar request over a 120-day window returned
2026-05-18 to 2026-08-12 — real data, correct length, and a month stale. Every
stop and every size is computed from that series, so this would have priced
stops off prices that no longer existed, and nothing downstream would have
flagged it.

**Change:** `bars()` now derives a window from the requested length, pages to
the end of it, and returns the tail. Two tests pin both failure modes:
`test_bars_requests_a_window_and_returns_the_tail` and
`test_bars_follows_pagination`. Verified against the live paper endpoint — 60
bars per symbol through 2026-09-15, with SPY's last close at 757.42 against
Yahoo's 757.44, inside the 50bps cross-check tolerance.

**Lesson for future rules:** "no setup today" and "no data today" must not
produce the same output. An empty result is only trustworthy if something
upstream has asserted the input was non-empty — a length check that skips
silently converts a data outage into a market opinion. The existing rule
"reachable is not usable" now has a sibling: **a response is not a series.**
Prefer a loud failure over a plausible one.
**Status:** active.

### 2026-09-15 — The circuit breakers reset overnight in the configuration we were about to run
**Evidence:** `.gitignore` excluded `state/ledger.json`, `state/fills.jsonl`
and the briefs, plans, news and reports under `state/`. Every Routine firing
gets a fresh container and a fresh clone, and `tools.state.load()` recreates
`EMPTY` when the ledger is absent — `risk_state: NORMAL`, `peak_equity: 300`,
`halts: []`, `week_start_equity: 300`, no fills. Consequences, all silent:

- a `HALTED_DAY` or `HALTED_WEEK` set on one day **cleared itself** by the next
- the -20% drawdown lock measures against `peak_equity`, so a run to $400 and
  a fall to $320 would have read as 0% drawdown and never locked
- the -8% week stop measured from $300 rather than the week's real start
- `fills.jsonl` began empty daily, so measured expectancy was permanently
  "0 closed trades" — the Phase 2 exit criterion, unmeasurable by construction

None of this was reachable while a human drove one long session, which is why
it survived the build phase. It became live the moment the plan changed to
unattended daily firings.

**Change:** `state/` is tracked. `.gitignore` now carries only secrets, with a
comment saying why the state lines must not come back. `state.load()`
announces a rebirth on stderr and tags the ledger `reborn: True` rather than
returning benign defaults in silence. Three tests pin it, including one that
reads `.gitignore` and fails if the state patterns reappear.

**Lesson for future rules:** durable state is part of the safety system, not
housekeeping around it. A circuit breaker that lives in an ignored file is not
a circuit breaker. And test the configuration you are about to *run*, not the
one you have been running — this whole class of failure appeared only in the
unattended shape.
**Status:** active.

### 2026-09-16 — The scheduled session had no repository, and could not get one
**Evidence:** the first autonomous firing failed immediately. The Routine's
stored config reads `"sources":[], "outcomes":[]` — `create_trigger` carries no
git source, because a fresh-session-on-fire inherits the *environment*, not the
repository. The container came up empty and nothing ran.

It could not recover on its own, for two independent reasons, both verified
rather than assumed: the repo is private, and a source-less test session
attempting `git clone` was refused by the permission classifier — there is no
human present to approve it. That refusal is correct. An unattended session
talking itself into cloning a private repo is not a capability worth having.

A second defect was hiding behind the first: every prompt hardcoded
`/home/user/tradingagent-claude`, which is this interactive session's path. A
session created with `source_url` lands at `/root/<branch-name>`. The prompts
would have failed even with the repo present.

**Change:** `preflight_phase2` gained a `repository` check, first in the list —
work tree, branch, origin remote, and a real `git fetch` against the private
repo, because a readable working copy proves nothing about whether the session
can persist anything. `docs/10-runtime-requirements.md` records the full
surface and the two configurations that actually work.

**Lesson for future rules:** the first firing is the test, and nothing before
it counts. Everything upstream had been verified — keys, network, risk gates,
data, state durability — and the thing that broke was the one part that only
exists at fire time. **Verify the artifact you are scheduling, not the
environment you are scheduling it from.** The session I checked it in was never
the session that would run it.

The session failed safe, and that is worth recording too: it found no repo and
stopped, rather than reaching for the broker API directly. The broker showed
$300.00, no positions, no orders. That behaviour is now an explicit rule rather
than a lucky default.
**Status:** active.

### 2026-09-16 — The day-1 rehearsal found three controls that were not controls
**Evidence:** the dry-run rehearsal (`state/rehearsals/2026-09-16.md`) produced
an empty plan and zero tickets, and then found three defects that an empty day
happened to hide. All three verified independently before being fixed.

1. **An empty plan handed control to the mechanical scanner.**
   `tools/paper_session.py:145` read
   `propose_from_plan(today) or propose_mechanical(...)`. An empty plan is
   `[]`, which is falsy, so `or` discarded it and ran the 20-day-breakout
   scanner instead. **A deliberate refusal to trade was indistinguishable, to
   that code, from having no opinion.** On any day the agent writes `[]`
   because of an FOMC, a halt, or an unreadable regime, the runner would have
   substituted breakout proposals and could have submitted them. It was
   harmless on 2026-09-16 only because the scanner also found nothing.
2. **`NO_TRADE` posture had no enforcement anywhere.** `posture`, `NO_TRADE`
   and `RISK_OFF` appeared exactly once across all `.py` files — inside a
   comment string. The brief's posture, which `premarket-brief` calls binding,
   was enforced only by the model's own compliance. That is the wrong side of
   the one rule that outranks everything.
3. **Dry-run fills polluted the measured track record.** `paper_session`
   appends a fill for every approved proposal including under `--dry-run`,
   tagged `dry_run`, and `review.closed_trades()` had no filter. Previewed
   tickets would accrue toward the 30 closed trades and the expectancy that
   unlock the option sleeve — options unlockable on trades that never
   happened — and worse, a phantom dry-run *entry* sits at the head of the
   FIFO queue where it pairs against the next **real** sell and corrupts that
   real trade's entry price and R.

**Change:** `engine/posture.py` makes posture deterministic, parsed from the
brief's `## Posture` section rather than by scanning the document (a brief
discusses posture in prose, and a keyword search reads those as the decision).
Everything fails closed: no brief, unreadable brief, or unparseable posture all
resolve to `NO_TRADE`, and ambiguity inside the section resolves to the most
conservative token present. `paper_session` now gates on it before proposals
are even gathered, and `RISK_OFF` tightens the config to 1% per trade and one
position. `propose_from_plan` returns `None` for an absent plan and a list for
a present one, so an empty plan is binding and the scanner is not consulted.
`closed_trades` drops dry-run fills before pairing. 13 new tests, 67 total.

**Lesson for future rules:** "the gate passed" and "nothing reached the gate"
look identical in a log and mean opposite things. Two of these three defects
were invisible on a day with no trades, and the rehearsal only caught them
because it went looking for what it had *failed* to test rather than reporting
a clean run. A day-1 gate that submits nothing exercises nothing — say so, and
then go test the untested path deliberately.

The second lesson is about where a rule lives. Posture was written down, agreed,
and documented as binding, and none of that made it a control. **A rule that
lives only in prose is a preference.** If it protects capital it belongs in
`engine/`, with a test, or it is not real.
**Status:** active.

### 2026-09-17 — Two primary sources were returning nothing, and preflight called it green
**Evidence:** `www.sec.gov` and `www.bls.gov` answered HTTP 403 to every
request this agent made. `netcheck.probe` caught the `HTTPError` and returned
`True, "HTTP 403 (host answered — network is open)"`, so both sat green in
every preflight while serving the brief nothing. The module's own header says
403 should be reported DEGRADED; the code did the opposite. Two sessions built
a thesis without SEC or BLS and neither said so, because nothing told them.

The cause was ours, not the allowlist. Measured across UAs:

| User-Agent sent | dol.gov | bls.gov | sec.gov |
|---|---|---|---|
| (none) | 200 | 403 | 403 |
| `tradingagent-claude` | 403 | 403 | 403 |
| `tradingagent-claude/1.0 (+<repo url>)` | 200 | 403 | 403 |
| `tradingagent-claude (<an email>)` | **200** | **200** | **200** |

Only a contact-shaped UA carrying an email satisfies all three, which is what
SEC's access policy asks for by name. A browser UA was tried and is *worse*
(403 from dol.gov), so impersonation is neither necessary nor effective.

**Change:** a 403 is now DEGRADED, not ok — 401 and 429 still pass, because
lacking a key is not a closed network. `netcheck.user_agent()` reads
`TRADING_AGENT_CONTACT` and **never defaults to a personal address**: that
string travels in an outbound header to third parties on every request, so
whose address it is must be a deliberate choice, not a default someone
inherits. Unset, SEC/BLS/DOL refuse us and netcheck says so.

Fixing the honesty immediately exposed a second defect: netcheck counted
`primary` failures as blocking, so preflight went red and would have stopped
Friday trading altogether. A degraded primary source is a reason to trust the
day's thesis less, not a reason to stop — `required` (broker, market data) and
`primary` (SEC, BLS, Treasury) now exit differently, and preflight reports
`READY, WITH DEGRADATION`, naming each source the brief must record as
unavailable.

**Lesson for future rules:** a check that cannot fail is not a check. "Host
answered" was easier to implement than "host served data", and the easier
question is the one that got asked for weeks. The existing rule — *reachable
is not usable* — was already written down and still did not stop this, because
it lived in a docstring rather than in the branch. **And when you make a check
honest, expect it to fail immediately and expect that to be inconvenient; the
inconvenience is the finding, but do not let a newly-honest check become a
blunter instrument than the thing it replaced.**
**Status:** active.

### 2026-09-17 — The posture parser read the reasoning as the decision
**Evidence:** `parse()` scanned the whole `## Posture` section and took the
most conservative token present. A brief that states `RISK_OFF` and then
argues for it — "this is not a NO_TRADE regime, and plainly not RISK_ON" —
resolved to `NO_TRADE`, blocking a day the brief had cleared. The 2026-09-17
brief is exactly that shape and only escaped because its reasoning happened
not to name another posture.

**Change:** the first line in the section that names **any** posture is the
decision; lines below it are reasoning and are ignored. Lines with no token
are skipped, so a preamble is harmless. Two or more tokens on the decision
line, no token anywhere, or no section at all still fail closed to
`NO_TRADE` — every failure mode lands in the same safe place.

**Lesson for future rules:** conservative defaults are not free. Failing
closed is right when the input is genuinely ambiguous, and wrong when it is
merely being read badly — that is not caution, it is a parsing bug wearing
caution's clothes. Distinguish "I cannot tell what this says" from "I am
reading the wrong part of it."
**Status:** active.

### 2026-09-17 — "No setup today" was a six-ticker list, not a market condition
**Evidence:** two sessions reported finding nothing and set posture partly on
it. The runner's own candidate list was `DEFAULT_SYMBOLS = ["F", "SOFI",
"PLTR", "NIO", "RIOT", "HOOD"]` — six tickers, hardcoded — and the 85-name
screen quoted in the briefs existed only inside a session, reproducible from
nothing. The open question was whether an affordable universe is structurally
too thin for a 20-day breakout to fire. It is not, and the measurement was not
close:

| | |
|---|---|
| US equities, active and tradable | 11,833 |
| Passing $3-$75 and the liquidity floor | **522** |
| Universe taken (top 150 by dollar volume) | 150 |
| Sessions in the last 60 with ≥1 breakout | **59** |
| Total signals over 60 sessions | 551 (9.3 per firing day) |
| Breakouts on 2026-09-17, the day a brief said none | **6** |

The strategy fires almost every day. Two empty sessions were a sampling
artifact of a six-name list.

Building the universe surfaced a second defect of the same family as the
`bars()` and 403 bugs — data present, meaning something other than it appears.
A $25M dollar-volume floor passed **14 names out of 11,833**, because Alpaca's
free feed reports IEX prints only: Ford showed 1.7M shares against Yahoo's
45.8M consolidated, about 4%. The floor was silently demanding ~$600M of real
volume. It is now named in IEX units, calibrated against a measured ratio, and
documented as coarse.

**Change:** `tools/screen.py` builds the universe from explicit, named criteria
and commits it to `data/universe.json`, screens it, and measures the base rate.
`paper_session` reads that universe; the six tickers remain only as a fallback
that warns loudly that it is not a universe. Ten tests, including one that
fails if the committed universe shrinks back toward a handful of names.

**Lesson for future rules:** an empty result is a claim about the world, and it
inherits every assumption in the thing that produced it. "Nothing is breaking
out" was really "nothing among these six is breaking out", and the difference
never reached the brief because the candidate list was a constant in a module
nobody re-read. **Before trusting a negative, state the denominator out loud.**
A screen that can veto a trade belongs in the repository with a test, so the
denominator is a committed fact rather than a sentence in a report.
**Status:** active.

### 2026-09-17 — The submit path works; fractional sizing cannot carry a stop
**Evidence:** after two sessions the order path had still never executed, so
`AlpacaAdapter.submit` was untested against a real broker — a mechanical risk
independent of any strategy, and one the first real trade would have
discovered unattended. `tools/smoke_submit.py` placed one bracket order priced
15% below the market so it could not fill, then cancelled it.

| Probe | Result |
|---|---|
| Whole-share bracket | **ACCEPTED**, `order_class=bracket`, **2 legs**: stop 10.95 and target 13.98 |
| Fractional 0.5, bracket | **REJECTED** — `42210000: fractional orders must be simple orders` |

> **Caveat added 2026-09-21.** This rejection is no longer reproducible as stated: once brackets became GTC (2026-09-18) the same probe returns `fractional orders must be DAY orders`, rejecting on time_in_force before the order_class is ever checked. See the 2026-09-21 entry.

Nothing filled, nothing was left resting, no position was taken, and
`state/fills.jsonl` still does not exist. The account reads $300.00 flat.

Two things settled. The stop really does attach atomically — the design was
right and is now demonstrated, not assumed. And **the ~$75 affordability
ceiling cannot be lifted by enabling fractional shares**, which had looked like
the obvious way to widen a $300 account's universe: Alpaca will not attach
protective legs to a fractional order, so a fractional entry is an entry
without a stop. That is the one thing this system will not do, and the
constraint is now a measured fact rather than an assumption.

**Change:** `tools/smoke_submit.py` is committed and re-runnable. It refuses
unless the market is open and the account is flat, prices the order where it
cannot fill, cancels in a `finally`, and writes nothing to the ledger or the
fill log — a rehearsal must not be able to contaminate the record it exists to
protect. Re-run it before Phase 3 against Robinhood.

**Lesson for future rules:** an untested write path is not a neutral gap, it is
a scheduled surprise, and the cheapest moment to find out is the one where
nothing is at stake. Test it deliberately rather than waiting for a real trade
to do it for you. **And when a constraint looks arbitrary, check whether the
alternative costs something you had decided was non-negotiable** — "just enable
fractional shares" would have quietly traded the atomic stop for a wider
universe, and nobody would have noticed until a gap.
**Status:** active.

### 2026-09-17 — The keyless fallback could cancel a trading day
**Evidence:** preflight's `live data` check called Yahoo alone. Yahoo returned
HTTP 429 and preflight exited non-zero, which means DO NOT TRADE. Observed
directly — three consecutive runs, two of them red, with every other check
green and Alpaca answering normally the whole time.

That inverts the documented precedence. `CLAUDE.md` puts Alpaca first and
describes Yahoo as "keyless, undocumented, fine as a cross-check, never the
sole basis for a trade" — and the gate was built on the cross-check.

**Change:** Alpaca decides; Yahoo is compared when it answers and reported
absent when it does not. A disagreement over 50bps is surfaced loudly, because
a silent disagreement between two sources is worth more than either number
alone. Two tests pin both halves.

Two smaller things fell out of the same pass. `adapters/marketdata.py` was
sending `Mozilla/5.0 (X11; Linux x86_64)` — impersonating a browser, which is
both dishonest and useless here, since dol.gov *refuses* browser UAs and Yahoo
serves the honest one identically. There is now one User-Agent for the whole
agent, and a test that fails if a second one appears. And `home.treasury.gov`
was reported blocked when it was merely slow: the probe path was a 404 and the
host takes 10-19s against a 12s timeout.

**Lesson for future rules:** rank your data sources, then check that the code
agrees with the ranking. Precedence written in a document and precedence
encoded in a gate had drifted apart, and the drift only showed up because a
third-party rate limiter happened to fire on a day someone was watching.
**A dependency you would never trade on is still a dependency that can stop
you trading.**
**Status:** active.

### 2026-09-17 — Five of six news sources were serving bot walls, reported healthy
**Evidence:** netcheck inspected the status code and not the body, so a
challenge page arriving as 401 read as "host answered — network is open".
Re-probed with body inspection:

| Host | Real status |
|---|---|
| www.reuters.com | HTTP 401 + JS bot challenge |
| www.marketwatch.com | HTTP 401 + JS bot challenge |
| apnews.com | HTTP 403 + JS bot challenge |
| www.theblock.co | HTTP 403 + JS bot challenge |
| www.cnbc.com | HTTP 403 |
| www.coindesk.com | **200 — the only one that serves us** |
| stooq.com | HTTP 200 + JS bot challenge (known since Phase 1) |

Every government primary, by contrast, serves us fine once the User-Agent
carries a contact. The split is not about permission, it is about what the
endpoint is *for*: machine-readable government data is built for programmatic
access, and consumer news HTML is built for browsers and defended against
everything else.

**Change:** the `news` tier is deleted rather than repaired — five hosts that
cannot serve us are not a source list, they are six lines of false comfort.
Market news now comes from **Alpaca's `/v1beta1/news`**, which was available
the whole time: authenticated, symbol-tagged, timestamped, on a host already
in the required tier, costing nothing to adopt. WebSearch covers the rest.

Fourteen replacements are proposed and explicitly **unverified** — all were
refused by the egress proxy before the host was ever asked, so their status is
unknown rather than good. They sit in a `proposed` tier that the default
netcheck run ignores, and are promoted only by answering. They favour JSON and
RSS endpoints over HTML for the reason above.

**Lesson for future rules:** when a whole category of source fails, ask what
the category has in common before replacing it like for like. Swapping six
challenged news sites for six more would have produced the same list with
newer names. **And a status code is a claim about a request, not about the
response body** — this is the fourth defect in a week where data was present
and meant something other than it appeared.
**Status:** active.

### 2026-09-17 — Promoting sources on a 200 would have repeated the whole week's mistake
**Evidence:** the allowlist opened and all fourteen proposed hosts returned
HTTP 200. Promoting there would have been the same error that made
`www.bls.gov` sit green for two sessions. Each was verified a second time
against the data it is supposed to carry, and one failed:

- `api.census.gov` answers **200 with an HTML "Missing Key" page**. It needs a
  free API key. Dropped rather than keyed, because FRED already serves the
  same retail-sales series (`RSAFS`) without one.
- The other thirteen parsed: 11 XBRL facts from `data.sec.gov`, 3,116 rows
  from FRED, CFTC and Treasury JSON, and 10-49 items from each of the seven
  RSS feeds.

The RSS bet paid off. Every feed serves us where the equivalent HTML page
serves a bot wall — BBC, NPR, Guardian, Fox Business, The Hill, Cointelegraph,
Decrypt. Feeds are built for machines; the pages are defended against them.

**FRED is the single biggest gain.** It carries the jobless-claims print that
`www.dol.gov` refuses us (196,000 for the week ending 2026-09-12) plus DGS10,
T10Y2Y, the high-yield spread, CPI, unemployment and VIX — keyless, no wall.
`adapters/fred.py` makes it usable rather than merely reachable, and every
reading carries its observation date and a staleness count, because a macro
number without its date reads as sourced while being stale, which is worse
than no number at all.

**Change:** thirteen promoted — five structured-data sources to `primary`, EIA
to `optional`, seven feeds to a rebuilt `news` tier. "Missing Key" and
"Invalid Key" joined the challenge markers, so a 200 carrying an error page is
caught the same way a 200 carrying a bot challenge is.

**Lesson for future rules:** there are three states, not two — *reachable*,
*usable*, and *used*. This week found failures at all three: hosts that
answered but served walls, data that parsed but meant something else (IEX
volume, one-bar series), and a screen that existed but nothing called. Clearing
one does not clear the next. **Verify against the thing you actually want out
of it, then check that something actually asks.**
**Status:** active.

### 2026-09-17 — The skills were still pointing at the dead sources
**Evidence:** after a week of source work, a grep across all six skills for
`fred`, `v1beta1/news`, `tools.screen`, `universe`, `rss` and `netcheck`
returned **nothing**. Meanwhile `news-intel` still named Reuters, AP,
Bloomberg, CNBC, MarketWatch and The Block as its lanes — every one of them
verified that morning as serving this agent a bot wall.

So the screen, the committed universe, `adapters.fred` and the Alpaca news API
all existed, were all verified working, and **nothing asked for any of them.**
The Friday trigger prompt named the screen only because it was written by
hand; the skills, which are the durable home, named none of it.

**Change:** `news-intel` now lists only sources verified serving us, with the
dead ones named as dead so nobody re-adds them, and a rule to prefer an
outlet's RSS feed over its HTML page. `premarket-brief` pulls rate, spread and
vol from `adapters.fred` with observation dates, and must run `tools.screen`
before concluding there is no setup. `trade-plan` takes candidates from the
committed universe and must state the denominator it screened.

One caveat went in with it: Alpaca's news feed is **Benzinga only**, 50 of 50
items. It is fast and symbol-tagged, but under the skill's own two-lane rule
it is a single outlet and cannot corroborate itself.

**Lesson for future rules:** building a capability and wiring it into the thing
that needs it are two separate jobs, and only the second one changes what a
session does. This is the third state — *used* — and it is the one with no
error message. A broken source throws; an unused tool is silent, and the work
looks finished from every angle except the one that matters. **After building
something, grep for its own name in the callers.**
**Status:** active.

### 2026-09-18 — The expected-R rule was never code, and the simulator could not have found that
**Evidence:** "Expected R >= 1.5" is written in `CLAUDE.md`, in
`docs/09-phase2-runbook.md` and in `.claude/skills/trade-plan/SKILL.md`. A grep
for it across the code —

```
grep -rn -iE "expected.?r|reward.?risk|r_multiple|min_r\b|1\.5R" engine/ tools/
```

— returned exactly one hit, a docstring line in `engine/feasibility.py`.
`RiskOfficer.evaluate` never read `p.target` at all. The field existed on
`OrderProposal`, every caller populated it, and no line of the gate consumed
it. The rule was unreachable by construction, not merely unenforced.

The obvious follow-up: 300-seed Monte Carlo has been run against these
guardrails repeatedly. Why did none of it surface a missing gate? Because
**every strategy in `engine/strategies.py` sets `target = px + 3.0 * atr`
against `stop = max(px - 1.5 * atr, px * 0.92)`.** That is 2.0R by
construction whenever the ATR leg binds, and wider when the 8% floor does. No
simulated proposal has ever been capable of failing a 1.5 gate, so a working
gate and an absent gate produce byte-identical simulation output. Re-running
`sim.run_suite --seeds 300` after adding the gate confirms it: every arm
unchanged (trend_pullback $302.17, momentum_breakout $308.89, option_swing
$300.00, graduated_swing $308.89, target_chaser_CONTROL $300.00, 0% ruin).

Friday, 2026-09-12, is where it would have mattered. Three breakouts — FPS,
MARA, RIOT — were **approved by the engine** and refused only by the plan,
on structural R of 0.3–0.5. The judgement was right and it was made in prose.
Had the session been on a worse model, or in more of a hurry, nothing in
`engine/` would have said no.

**Change:** `min_expected_r = 1.5` and `require_target = True` in
`engine/config.py`; the gate in `engine/risk.py`, positioned after the
asset-class checks and before sizing; seven tests in `TestExpectedRGate`.
One of them pins the float problem: the config's own option exit pair, a -40%
stop against a +60% take-profit, is `0.60/0.40 == 1.4999999999999998` in binary
floating point and fails a naive `< 1.5`. The comparison carries a `1e-9`
epsilon so the constitution does not reject its own documented defaults by
2e-16. Another test pins the finding above — that the simulated strategies are
2.0R by construction — so that if someone later changes a strategy's target
multiple, the test says out loud that the simulator's coverage of this gate
just changed.

**Correction, same day.** "No simulated proposal has ever been capable of
failing a 1.5 gate", above, is too strong, and cleaning up the rejection
histogram later that day is what exposed it. The strategies' *construction* is
2.0R and that part stands. But `engine/sim.py` signals on the close and **fills
at the next open**, leaving the stop and the target where the close put them.
A gap up compresses R without anything in the strategy changing:

```
signal at close 10.00: stop 9.25, target 11.50  -> R 2.00
fills at open 10.20 (+2%)                       -> R 1.37   REJECTED
fills at open 10.40 (+4%)                       -> R 0.96   REJECTED
```

The 300-seed suite carries a handful of these per arm — "expected R 1.36-1.49
< required 1.50". So the gate is **not** inert in simulation: it refuses to
chase a setup that degraded overnight between the signal and the fill, which
is a second capital-protecting behaviour the original note missed entirely. It
is rare enough that aggregate equity is unchanged either way, which is why the
byte-identical output was read as "the gate can never bind" when it actually
meant "the gate binds too rarely to move the median". Both facts now have
their own test.

**Lesson for future rules:** a simulation only tests the gates its generators
can fail. Every strategy here was written by the same hand that wrote the
guardrails, so they all obey them — which means the suite measures whether
compliant behaviour survives, never whether non-compliant behaviour is caught.
The `target_chaser_CONTROL` arm exists precisely to be a strategy that breaks
a rule, and it breaks the *sizing* rules, not this one. **For every rule in
the constitution, name the simulated arm that violates it. If there isn't one,
the suite is not evidence about that rule.**
**Status:** active.

### 2026-09-18 — The fill log recorded intent, not fills
**Evidence:** looking for a way to test the live submit path, I read what
`paper_session --submit` does *after* `adapter.submit` returns:

```python
result = adapter.submit(ticket)
state.append_fill({..., "qty": d.qty, "price": p.price, ...})
```

It writes a fill for every accepted order, unconditionally, at the **proposed**
price and the **approved** quantity, with no check that anything filled. These
are bracket *limit* orders. A limit at the last trade can rest all day and
expire unfilled, and that order would still have been written to
`state/fills.jsonl` as an entry.

That log is not cosmetic. It is the input to `closed_trades()`, which is the
input to `set_track_record()`, which is the input to the option-unlock gate:
30 closed trades at >= +0.10R. So an order that never traded would have
counted toward unlocking the instrument that simulation found negative at
every capital level, and the phantom entry would have sat at the head of that
symbol's FIFO queue waiting to pair against the next real sell and corrupt its
entry price and R.

The irony is that `closed_trades` already carries a careful docstring about
exactly this damage — written to explain why *dry-run* rows are filtered. The
same damage through the live path went unnoticed, because the live path had
never once run. Two sessions of empty plans meant the bug could not surface.

**Change:** `AlpacaAdapter.order()` and `await_fill()` poll a submitted order
to a terminal state; `paper_session` now records only what the broker reports
filled, at the broker's `filled_avg_price` and `filled_qty`, and prints the
realised slippage against the proposal. A partial fill records the part that
filled and carries the remainder as resting. An unfilled or rejected order
writes nothing and is carried into `ledger["working_orders"]` for
session-close to reconcile. The decision is a pure function, `fill_record()`,
so it is testable without a broker: ten new tests in
`tests/test_posture_and_fills.py` cover working, accepted, partially-filled,
rejected, zero-price and dry-run outcomes. 110 tests pass.

**Lesson for future rules:** "the submit path is untested" was the wrong frame,
and it hid this. The *adapter* submit path was proven on 2026-09-17 by
`smoke_submit` — bracket accepted, two legs attached. What had never run was
everything downstream of it, and that is where the defect was. A write path
has two halves, sending and recording, and the second one is the half that
lies quietly. **When something is "untested", name the specific line that has
never executed, not the feature.**
**Status:** active.

### 2026-09-18 — Crypto cannot carry an atomic stop, so crypto is already prohibited
**Question asked:** a bitcoin miner (MARA, RIOT) appeared in the screen, and
crypto trades 24/7 while the agent only runs during the regular session. Should
it be trading crypto off-hours?

**Evidence:** measured against the Alpaca paper broker, 2026-09-18, four
probes at unfillable prices, all cancelled:

| Order shape | Broker response |
|---|---|
| `order_class=bracket` (stop + target) | **422** `crypto orders not allowed for advanced order_class: otoco` |
| `order_class=oto` (stop only) | **422** `crypto orders not allowed for advanced order_class: oto` |
| simple limit, `time_in_force=day` | **422** `invalid crypto time_in_force` |
| simple limit, `time_in_force=gtc` | **ACCEPTED**, `legs=0` |

So the only crypto order this broker will accept is one with no protective leg
attached. CLAUDE.md already says: *every entry supplies a stop before it is
placed. No stop, no trade.* Crypto is therefore not a new decision to make —
it is prohibited by a rule that has been in force since day one. The hours
question never arises.

This is the fractional-shares finding again, one instrument over. There the
tempting move was "enable fractional to widen a $300 universe"; here it is
"trade crypto so the account can work nights". Both are paid for with the
atomic stop, and the atomic stop is the thing that is not for sale.

Note the second-order point, because it inverts the intuition. 24/7 markets
make a missing stop *worse*, not better: a position with no resting stop, in a
market that trades while no session is running, can only be managed by a
process that is awake, and this agent is awake on a Routine schedule. The
absence of a stop and the presence of 24/7 trading are not two independent
facts, they compound.

**On the miner itself:** MARA and RIOT are equities, not crypto. Nothing in
Friday's screen was a crypto trade. But they import crypto's overnight
variance into an instrument that can only be exited 6.5 hours a day — the
worst combination of the two, and a reason to treat a miner's overnight gap
risk as larger than its ATR suggests, not smaller. `class_caps["crypto"] = 0.20`
and `max_position_pct_crypto` stay in the config as dead settings, and should
be read as dead until a broker attaches a stop to a crypto order.

**Change:** none to the rules — the existing rule already covers it. This
entry exists so the question is not re-opened without new broker behaviour.
Re-measure before Phase 3: Robinhood's MCP may differ, and if it attaches a
stop atomically to crypto, the hours question becomes live and is worth asking
properly.
**Status:** active.

### 2026-09-18 — The stop was being cancelled at 16:00, with the position still open
**Evidence:** the same probe session, asking what happens to a bracket's
protective legs overnight. Submitting an equity bracket and reading the legs
back:

```
equity bracket, TIF=day   parent TIF=day   leg stop TIF=day   leg limit TIF=day
equity bracket, TIF=gtc   parent TIF=gtc   leg stop TIF=gtc   leg limit TIF=gtc
```

**The legs inherit the parent's time_in_force.** `OrderTicket.time_in_force`
defaulted to `"day"` and no caller overrode it. So the sequence for any
position carried overnight was: entry fills at 10:15, stop registers correctly,
16:00 arrives, the day order expires, **the stop is cancelled and the position
is not**. The account would have sat through the gap naked, and
`positions_without_stops()` would have reported it the next morning — after
the gap, which is the only time it matters.

`submit()` carries a docstring saying a filled entry whose stop failed to
register "is exactly the unmanaged position this system exists to prevent".
The stop did not fail to register. It registered, and then expired quietly six
hours later, which the docstring did not contemplate.

This was not hypothetical-only-in-principle: it was live in the path enabled
earlier the same day, and the strategy makes carrying the normal case, not the
exception. Target is `entry + 3*ATR` — a multi-day objective — and PDT allows
3 day trades per 5 days, so flattening daily is not available even if it were
desirable.

**Change:** `OrderTicket.time_in_force` defaults to `"gtc"`, so a stop outlives
the session that placed it. The corollary is that an *unfilled* entry also
persists and would fire the next morning on a gap against yesterday's thesis,
so `trading_day close` now calls `cancel_unfilled_entries()` — which cancels
resting bracket *parents* only, identified by the fact that they still carry
their `legs`, and never touches a live protective leg. `cancel_all()` must not
be used for this: once a parent fills, its stop and target become ordinary
open orders, and cancelling all of them strips the protection off an open
position. The close then re-reads `positions_without_stops()` *after*
cancelling and reports any change tonight rather than tomorrow. Three tests
pin all of it, including that a failed cancel is reported rather than
swallowed.

**Lesson for future rules:** a control can be correctly installed and still
stop existing later, and nothing will raise an error at the moment it
disappears. Ask of every protective mechanism not only "is it attached?" but
"what is its lifetime, and who ends it?" **Re-measure this on Robinhood before
Phase 3** — leg TIF inheritance is broker behaviour, not a standard, and this
one was discovered by asking the broker rather than by reading anything.
**Status:** active.

### 2026-09-18 — The universe is not too thin. The plan is the constraint.
**Question asked:** three sessions produced zero trades, and the standing
hypothesis was structural — that a 20-day breakout inside a universe an account
can afford (whole shares, 2% risk, a 25% single-position cap on $300) is simply
too rare to trade. That is a system question, and answering it by lowering a
threshold on a future quiet day would have been the wrong way to find out.

**Evidence:** `tools/screen.py --base-rate 60` over the committed 150-symbol
universe, then `--replay 60`, which pushes every historical signal through
`RiskOfficer.evaluate` itself rather than restating the sizing arithmetic:

| | |
|---|---|
| Signals in 60 sessions | **533** |
| Sessions with at least one | **59 of 60 (98%)** |
| Approved by the engine at $300 | **507 (95.1%)** |
| Rejected | 26 — 24 on the single-position cap, 2 on the 2% risk budget |
| Tradeable days | **59 of 60**, median **7** tradeable signals each |
| Median position | 2 shares @ $34.64 = $61.95 (20.6% of equity) |
| Median risk taken | $2.34 — 0.78% of equity, **39% of the 2% budget** |

The hypothesis is wrong, and not narrowly wrong. The account could have taken a
sized, stopped, engine-approved trade on 98% of the last 60 sessions, with a
median of seven to choose from. The affordability ceiling is real but it is not
the binding constraint: it turns away 26 of 533 signals, and the constraint
doing the turning is the 25% single-position cap (`0.25 × $300 = $75`), not
volatility and not the risk budget.

So the zero-trade weeks were not the universe. Wednesday was a scheduling
defect and Thursday was a deliberate RISK_OFF, but **Friday is the real
datum**: the screen found three, the engine approved all three, and the plan
refused all three on structural reward-to-risk of 0.3-0.5R.

**The tension that leaves, stated plainly.** Two different definitions of
"target" are in play and they do not agree:

- The **mechanical** target, `close + 3*ATR`, is what `propose_mechanical`
  builds and what this replay measured. Against a stop of at most `1.5*ATR` it
  is 2.0R by construction — so it can never fail the expected-R gate added
  today, and on this evidence it would trade nearly every day.
- The **structural** target, the next real level, is what the model reads off
  the chart. On Friday it produced 0.3-0.5R on all three candidates, which the
  new gate would now reject in code rather than in prose.

Both cannot govern. The mechanical target trades a lot and is a rule with no
market read in it; the structural target has a market read and has produced
zero trades in three sessions. This is a decision about what the strategy *is*,
and it is not a threshold to be nudged on a quiet morning. It belongs to a
weekly-review session at Opus/xhigh with the evidence in front of it.

One more number worth carrying into that decision: the median approved trade
risks **39% of the permitted 2% budget**, because whole-share rounding at a
median 2 shares is coarse. The account systematically under-deploys its own
risk allowance, and there is no fix for that which does not cost the atomic
stop (see 2026-09-17 on fractional shares). It is a fact about trading $300,
not a defect.

**Change:** `tools/screen.py --replay N [--equity E]`, so this is re-runnable
evidence rather than a one-off answer, and so it tracks the engine
automatically when the engine changes. No rule was changed on the strength of
it — that is deliberate, and it is the next session's decision, not this one's.

**Lesson for future rules:** "the strategy finds nothing" and "the account
cannot take what it finds" and "the plan refuses what it could take" are three
different diagnoses with three different fixes, and from inside a quiet week
they produce an identical symptom: an empty plan. Two of the three were wrong
here, and the one that was right was the one nobody had proposed. **Before
adjusting a threshold because nothing is trading, measure which of the three
is actually happening.**
**Status:** active.

### 2026-09-18 — Two controls that only a live order could falsify
**Evidence:** the changes made earlier today were tested against stubs. Run
against the paper broker with the market open and the account flat, two of
them failed — and neither could have been caught any other way, because both
bugs were in assumptions about the broker's response shape.

**1. `cancel_unfilled_entries()` cancelled nothing.** It identifies an unfilled
bracket parent by the fact that it still carries its `legs`. Against the real
API:

```
GET /v2/orders?status=open                 parent comes back with legs ABSENT
GET /v2/orders?status=open&nested=true     parent comes back with legs: [2]
```

The flat listing omits nested legs entirely, so the guard skipped every parent
and the close would silently have carried resting entries into the next
morning — the exact thing it was written to prevent, reporting success.
`nested=true` fixes it. `open_orders()` keeps its flat default because
`positions_without_stops` depends on a *filled* parent's live legs appearing at
the top level.

**2. `positions_without_stops()` counted a take-profit as a stop.** The old
test marked a symbol protected if any open order on it had `order_class` in
`(bracket, oto, oco)`. Filling a bracket entry live showed why that is wrong:

```
entry a725aecc  filled 1 @ 13.10
live protective orders: [('limit', 'new')]     <- the TAKE-PROFIT, class=bracket
positions_without_stops(): []                  <- "protected"
```

The stop leg existed (it shows in a `status=all&nested=true` listing at
`stop=11.79`), but it was `held`, and **Alpaca's `status=open` filter excludes
`held`**. So the control returned the right answer from the wrong evidence. Had
the stop genuinely been cancelled while the take-profit survived — which is
precisely the state the `day`-TIF bug created — this control would still have
reported the position protected. It is the check that decides whether the close
escalates, and it would have stayed quiet.

Now it requires a real order, of a stop type, in a status that can still
execute, read from a nested listing so `held` legs are visible. Five tests
cover take-profit-only, live stop, held leg, cancelled stop, and a stop on a
different symbol.

The live probe cost one cent (a 1-share F round trip at 13.10) and left the
account flat at $299.99.

**Lesson for future rules:** a stub encodes what you believe the dependency
returns, so a test built on one can only confirm your own assumption. Both
bugs here were assumption bugs, both were in code written to protect a
position, and both tested green. **For anything that guards real money against
an external system, at least one test has to talk to that system.** And the
narrower lesson, which is now the fourth instance this week: when a control
answers "protected", ask what evidence it accepted — `order_class == bracket`
was true of the take-profit, and that was enough to pass.
**Status:** active.

### 2026-09-18 — The rejection histogram counted approvals as rejections
**Evidence:** `engine/sim.py` tallied **every** reason on a rejected decision:

```python
if not d.approved:
    for r in d.reasons:
        res.rejections[key] = res.rejections.get(key, 0) + 1
```

`Decision.reasons` is a running log, not a verdict. `reject()` appends the
verdict last; everything before it is a note recorded on the way through. So
adding `d.reasons.append(f"expected R {expected_r:.2f}")` to the *approval*
path earlier the same day immediately put lines like `expected R 2.02: 24`
into the rejection histogram — a proposal that **passed** the R gate and was
then rejected at sizing, counted once under the gate it cleared.

That table is what someone reads to answer "why is nothing trading". It is the
first place anyone would look, and it had started answering with reasons that
rejected nothing. Same failure as the rest of the week: a number that means
something other than what it appears to mean, in a place where it will be
trusted.

**Change:** tally `d.reasons[-1]` only. This also stops the older approval
notes — "at day-trade budget: this must be held overnight" — from polluting it.
Verified: the histogram now reads clean, and all five arms return identical
equity, so nothing about the simulation changed except what it reports about
itself.

**Lesson for future rules:** appending to a shared log is not a local change.
`reasons` is read by the simulator, by `paper_session`'s printed output and by
the session report, and each reads it with its own assumption about what the
list means. **Before adding to a structure something else aggregates, check
what the aggregator thinks each element is.**
**Status:** active.

### 2026-09-18 — The model gate reads an environment constant to answer a per-session question
**Evidence:** the week-one close reported `python3 -m tools.model_check
weekly-review` **exits 1** and concluded it was not cleared to review. The
16:35 wrap session ran the same command and got the same refusal:

```
!! 'weekly-review' requires opus-tier or better; running claude-sonnet-5 (sonnet).
!! BLOCKING: do not perform this task.
```

That session is Opus. Verified against the session record rather than the
environment:

| source | value |
|---|---|
| `configured_model` | `claude-opus-5` |
| `session_context.model` | `claude-opus-5` |
| `external_metadata.last_served_model` | `claude-opus-5` |
| `effort_level` | `xhigh` |

`engine/model_policy.current_model()` reads `TRADING_AGENT_MODEL`, which is set
to `claude-sonnet-5` — **at the environment level**, because trading days were
configured for Sonnet. Every session launched in that environment reports
Sonnet, whatever it is actually running. The gate is answering a per-session
question with an environment-wide constant, and it is right only when the two
happen to coincide.

CLAUDE.md already warns that environment variables are snapshotted at session
start. That note was written about *adding* a variable mid-session. The sharper
version is this: a snapshot of an environment default was never a measurement
of the session in the first place.

**Which direction the error runs, and why that is luck.** Today it failed
*closed* — it refused a session that was properly cleared, which costs a review
and risks nothing. But the mechanism is symmetric and the safe direction is not
a property of the design. Setting `TRADING_AGENT_MODEL=claude-opus-5` at the
environment level, for perfectly good reasons, would make **every** session in
it report Opus, and a rule promoted by an under-powered session would sail
through the one gate written to prevent exactly that. CLAUDE.md calls the
routing table binding and says a bad rule "costs every trade until someone
notices". That gate is currently one environment edit away from never noticing.

This is the same shape as `positions_without_stops` accepting a take-profit as
a stop, found the same afternoon, and as netcheck reading 403 as healthy. The
control runs, returns a confident verdict, and the verdict rests on evidence
that does not establish the claim.

**Change (landed 2026-09-20):** the fix is not a better guess — Claude Code
exports no model variable, so there is no better source available to a Python
process. It is honesty about provenance. `model_and_source()` returns the
value *and where it came from*, and `check()` now **refuses any blocking task
whose model came from the environment**, in either direction:

```
$ python3 -m tools.model_check weekly-review
  !! 'weekly-review' is blocking and the running model is UNVERIFIED: the
     value 'claude-sonnet-5' came from TRADING_AGENT_MODEL, an
     ENVIRONMENT-level default ... Refusing rather than guessing.
$ python3 -m tools.model_check weekly-review --model claude-opus-5
  ok: 'weekly-review' cleared on claude-opus-5 at effort xhigh
```

Refusing even when the environment value *would* pass is the point: accepting
it in the passing direction is what makes the failing direction reachable by a
single config edit. Non-blocking tasks proceed and name the provenance in
their output. Ten tests in `tests/test_model_policy.py`, including one pinning
that the rule-changing tasks are the blocking ones — making `rule-promotion`
non-blocking is the single change that would quietly undo this whole gate.

**Lesson for future rules:** ask what *scope* a control's evidence has, not
just whether the evidence is present. An environment variable cannot describe a
session, a take-profit cannot describe a stop, and a 200 cannot describe a
body. Each was a real value, correctly read, answering a question it was not
about. **When a control reads a variable, check that the variable can vary with
the thing being checked.**
**Status:** active.

### 2026-09-18 — A short entry would bypass the entire risk gate
**Evidence:** asked whether the agent should run a puts or downside strategy
to answer Q3's negative expectancy, I checked what `RiskOfficer.evaluate`
does with a sell. It is the first four lines:

```python
c, d = self.cfg, Decision(approved=True)
if p.side != "buy":
    d.reasons.append("exits are always permitted")
    return d
```

**Any** proposal that is not a buy returns APPROVED immediately — before the
account-state check, before the stop requirement, before sizing, before every
cap. Nothing anywhere in `engine/` or `tools/` distinguishes *sell to close*
from *sell to open*. A grep for `short`, `sell_to_open` or a side-aware entry
path returns nothing but unrelated matches.

Today that assumption holds, because the system is long-only and every sell
really is an exit. It stops holding the moment anyone adds a downside
strategy — a short entry, or a long put, presents as a sell and is waved
through with no stop, no size, no state check. In practice the `Decision`
carries `qty = 0.0`, so the broker would reject the resulting ticket; but the
gate said **yes**, and a control that approves an unstopped opening trade and
relies on a downstream system to catch it is not a control.

This is the same shape as the rest of the week: the code is correct only under
a premise that is not written down and not enforced. "Exits are always
permitted" is true. "Every sell is an exit" is the premise, and it is a
property of the current strategy rather than of the system.

**Change:** none yet — recorded before any downside work begins, not after.
The fix is that `OrderProposal` must carry intent (open vs close) rather than
inferring it from side, and only a *closing* sell short-circuits the gate. An
opening sell must pass a stop requirement — an upside stop — and its own
sizing path, because a short's risk is not bounded by its notional the way a
long's is, and none of the current caps model that.

**Lesson for future rules:** when a branch exists because of something that
happens to be true about today's strategy, write the premise into the branch,
not into the reader's head. **`if side != "buy"` encodes "every sell is an
exit" without ever saying so** — and the cost of the unstated premise is paid
by whoever first adds the feature that breaks it.
**Status:** active.

### 2026-09-18 — Most of the edge was the universe, and I had the sign wrong
**Evidence:** `docs/14-target-study.md` measured the no-target arm at +0.132R
expectancy, t = +2.7 — the one statistically significant result in the study.
I flagged the survivorship caveat in the same document and predicted its
direction: removing it should make that arm look **better**, because the
universe was capped at $75 and stocks that ran past it were the winners a
breakout strategy lives on.

Rebuilt point-in-time from all 13,169 tradable names, with eligibility
recomputed at each signal date, the arm falls to **+0.054R, t = +1.1** — not
significant. Across all 1,563 eligible names rather than the 150 most liquid,
it is **−0.014R**. I had the sign backwards.

The reason is that I was thinking about one bias and the universe carried two.
The old set was not only *surviving*, it was `size: 150` — the most liquid
eligible names, ranked. Separating them:

| | old (150, priced today) | PIT, top 150/day | PIT, all 1,563 |
|---|---|---|---|
| no-target arm | +0.132 (t +2.7) | +0.054 (t +1.1) | −0.014 (t −0.6) |

So liquidity selection is real and large — the strategy is negative across
every arm in the broad tail — and survivorship was worth roughly 60% of what
remained. The truncated-right-tail effect I worried about is real too, and it
is simply much smaller than the healthy-company effect I did not think about:
a universe screened on today's prices is a universe of companies that did not
collapse, delist, or go illiquid, and that flatters a backtest far more than
excluding a few big winners penalises it.

The ranking of the arms survived the correction. The edge did not.

**Change:** `tools/pit_study.py`, which rebuilds eligibility per date and
carries a `--top N` control so the liquidity cap can be isolated from the
survivorship correction. `docs/14-target-study.md` is flagged as superseded in
part rather than edited, so the original claim and its correction sit together.

**Lesson for future rules:** naming a bias is not the same as knowing its sign,
and a caveat stated confidently in the wrong direction is worse than one
stated as unknown — it launders a guess into a finding. **When a study is
conditioned on a selection, do not reason about which way it cuts. Re-run it
without the selection, and if that is impossible, say the result is
conditional rather than predicting the correction.** The number to distrust
most is the only one that came back significant.
**Status:** active.

### 2026-09-20 — The ledger's cash was write-once, so drift could not be seen
**Evidence:** on 2026-09-18 a one-share probe moved the broker from $300.00 to
$299.99. Every control reported clean: `trading_day open` printed `$299.99`
and `0 closed trades` in the same breath, the close reported "Escalate to the
human today? — nothing", and `tools.review` said "no closed trades".

The 15:30 session found why `reconcile()` could not see it — it compares
position symbols and `trading_blocked`, then adopts `acct["equity"]` wholesale
without ever asking whether that number is what the ledger expects. Reading
further turned up something worse: **`ledger["cash"]` was never written after
initialisation.** Nothing in `trading_day.py` or `paper_session.py` assigned
it; it sat at `300.0` from `state.EMPTY` forever, and `reconcile()` only read
it in the offline branch — which would therefore have reported $300.00
indefinitely, no matter what had happened.

So it was not a tracked value that drifted. It was a field that looked like a
tracked value and never was.

**Change:** check **cash**, not equity. Equity moves every second for
legitimate reasons, so comparing it needs a tolerance wide enough to catch
nothing; cash only moves when something *happened*, which makes it the
invariant worth holding:

```
expected_cash = ledger["broker_cash"]                      # last observation
              + sum(cash_effect(f) for f in fills since that observation)
```

Response is tiered, detection is not. Anything over half a cent is reported;
only drift over `max($1, 0.5% of equity)` returns `ok=False` and stops the
day. An unexplained cent and an unexplained dollar have identical causes — an
unrecorded fill, a fee, a position opened and closed between two firings, a
bug in the submit path — so both get said out loud, and the size decides only
whether trading continues.

Carried day to day by `anchor_cash()`, called at **both** open and close: it
writes `broker_cash`, `broker_equity`, `broker_cash_at`, appends to a bounded
`reconcile_drift` history, and keeps the legacy `cash` field honest. The
offline branch now reports the last *observed* broker figure with its
timestamp instead of a stored guess, so a stale number looks stale.

Verified live against the paper broker, non-destructively, on a copy of the
ledger: Friday's exact cent is caught and noted with the day continuing; a
$40 disagreement returns `ok=False` with "DO NOT TRADE". Thirteen tests,
including the one-cent case, a fill that explains the drift, a fill recorded
before the anchor, dry-run rows excluded, and the threshold scaling with
equity.

**Lesson for future rules:** a field that is initialised and never assigned
reads exactly like a field that is maintained — same name, same type, a
plausible value. `ledger["cash"] == 300.0` was *correct* on day one, which is
what made it invisible on day four. **For any value a control compares
against, find the line that writes it. If there is only one and it runs at
birth, the control is comparing against a constant.**
**Status:** active.

### 2026-09-20 — The circuit-breaker baselines reset on every management firing
**Evidence:** pre-flighting Monday, I read `cmd_open` and found this, directly
under a comment describing what it was supposed to do:

```python
# A new week resets the weekly anchor; a new day resets the daily one.
if today.weekday() == 0 or not ledger.get("week_start_equity"):
    ledger["week_start_equity"] = snap["equity"]
ro.start_day(today, snap["equity"])
ledger["day_start_equity"] = snap["equity"]          # every invocation
```

The comment states the intent. The code re-anchors on every **call**, and
`trading_day open` is called at every management firing — midday and
pre-close as well as the open, because that is how it reconciles.

So on a losing day: −3% by noon, noon re-anchors, a further −3% reads as −3%.
**The −4% daily halt measured from a baseline that walked downhill with the
losses and could never fire.** The weekly anchor was worse in two ways:
`weekday() == 0` made Monday re-anchor on every run, and a week whose Monday
never ran kept the *previous* week's anchor, so the −8% breaker measured the
wrong week entirely.

This was live, and I had just written `trading_day open` into both the midday
and pre-close prompts for Monday — the first day the account may actually
hold a position. Three firings, three resets.

**Change:** anchors are keyed to the calendar, not to the call —
`day_start_key` against today's date, `week_start_key` against the ISO week,
which also fixes the holiday-Monday hole. `ro.day_start_equity` is re-pointed
at the stored anchor after `start_day()`, or the fix would have been cosmetic:
the breaker reads the officer, not the ledger. Five tests.

**A second finding, in the test.** The first version of the test helper moved
equity and cash together, and `cmd_open` returned early on the new cash-drift
check before ever reaching the anchor logic — so the test asserted the right
value for entirely the wrong reason, and passed. A losing day with an open
position moves *equity* through unrealized P&L and leaves cash alone; the
helper now models that, and asserts `cmd_open` returned 0 so it cannot pass by
exiting early again.

**Lesson for future rules:** a comment that states the intent is evidence the
intent was understood, not evidence it was implemented — and it actively
suppresses review, because the reader checks the comment against the
requirement instead of the code against the comment. **Read the line, not the
line above it.** And when a function is called from more than one place, ask
what it assumes about being called once.
**Status:** active.

### 2026-09-20 — A per-reading threshold cannot see a day that leaks
**Evidence:** the cash-drift check landed earlier the same day reports the
displacement since the last anchor, then re-anchors. That is correct per
reading, and `trading_day open` runs at every management firing — open,
midday, pre-close. So three separate 60-cent surprises are three correct,
individually sub-threshold notes, while $1.80 of a $300 account has moved
with no recorded cause and nothing says so.

Each reading was reported, so nothing was hidden. But the *day* was never
stated, and the halt acted on increments rather than on the total, which is
the number that matters.

**Change:** `drift_today()` sums the readings already recorded today from
`reconcile_drift` (today's only — Friday's $9 is not Monday's problem). The
day's total is reported when there is more than one reading, and **the halt
now fires on the cumulative figure as well as the individual one**. The close
report states the figure unconditionally, including when it is zero:

```
## Cash reconciliation
- unexplained cash drift today: **$+0.0000** across 2 reconciliation(s)  — clean
```

Reporting it only when non-zero teaches the reader that silence means "not
checked", which is how a $300.00 that should have read $299.99 went unremarked
for a day.

**The test got the arithmetic wrong before the code did.** The first version
used three 40-cent drifts and asserted a halt; it failed, because the
threshold is `max($1.00, 0.5% of equity)` = **$1.50** at this account size, not
the $1.00 floor. The percentage term passes the floor above $200 of equity, so
the floor is never binding for this account. Pinned in a test now, because it
is counter-intuitive at $300 and I got it wrong while writing the thing.

**Lesson for future rules:** a threshold applied per reading is not a
threshold on the quantity, it is a threshold on the sampling rate. Check more
often and the same total passes more easily — which is the opposite of what
more checking should buy. **When a control samples repeatedly, ask what it
does to a quantity that leaks slowly.**
**Status:** active.

### 2026-09-21 — A passing probe stopped testing what it said it tested
**Evidence:** Monday's smoke test, the first since the GTC change. The
whole-share bracket was ACCEPTED with two legs and, read back from the broker,
`TIF=gtc` on the parent and on **both** legs — bug B-16's fix confirmed live,
which is what the firing was for.

The fractional probe is where it got interesting. It was REJECTED, as always,
with code `42210000`, as always — and the smoke test printed its usual
conclusion, "Fractional cannot carry a bracket, the ~$75 ceiling stands".

But the message had changed:

```
2026-09-17   42210000: fractional orders must be simple orders
2026-09-21   42210000: fractional orders must be DAY orders
```

The first is about `order_class`. **The second is about `time_in_force`** —
and it is our own doing: brackets became GTC on 2026-09-18, so the broker now
rejects the fractional probe on TIF and never reaches the order-class check.

Nothing failed. The probe still returned REJECTED, the same error code, and a
conclusion that reads identically. **But D-17 — whole-share sizing stands,
because a fractional order cannot carry an atomic stop — now rests on evidence
this run did not produce.** For all Monday's smoke test shows, a fractional
*day* bracket might be accepted, which would re-open the $75 ceiling and the
universe argument built on it.

**Change:** the probe is split in two, because one probe cannot test two
constraints when either alone is sufficient to reject. `fractional + gtc`
tests the TIF constraint; `fractional + day` tests the order_class constraint,
and that second one is what D-17 actually rests on. If a fractional day
bracket is ever ACCEPTED the test now says so loudly instead of printing the
old conclusion. The 2026-09-17 entry is caveated rather than rewritten. **D-17
is unverified until the next smoke run**, and I did not re-probe today: this
firing's instructions said place no other order, and working around my own
stated constraint because I wanted the answer is the exact habit the risk
engine exists to prevent.

**Lesson for future rules:** a test that asserts only `REJECTED` cannot notice
that it is being rejected for a new reason, and the reason is the thing the
decision rests on. This one drifted because *we* changed the request, so the
broker's first objection changed — no external event, no failing test, no
alarm. **Assert on the reason, not the outcome. And when you change a request,
re-check every test that depends on how that request is refused.**
**Status:** active.

### 2026-09-22 — Three gates that trusted a declaration, and one that ran too late
**Evidence and changes**, from Monday's live session (`state/reviews/2026-09-21-queue-m.md`):

**M-17, the effort gate.** `model_policy` read `TRADING_AGENT_EFFORT`, an
operator declaration set once per environment. The harness exports
**`CLAUDE_EFFORT`** and nothing read it. On 2026-09-21 they disagreed in the
close session — declared `xhigh`, running `high` — so the gate cleared an
effort the session was not running at, permissively, using a value that was
sitting in the environment the whole time. Now `effort_and_source()` takes the
harness value as truth, the declaration as a labelled fallback, reports a
mismatch loudly, and refuses a blocking task on a declared-only value.

This is the strictly better half of the model finding. There the fix could
only be honesty about provenance, because Claude Code exports no model
variable. Here a measured value existed and was being ignored.

**M-22, who may use `--model`.** The override was added on 2026-09-20 so a
session that had verified its own model could clear a blocking gate. Nothing
said *who* may do that. The close session worked it out unprompted and
declined the flag: *an override is honest only from a present human, never in
an unattended session.* That is right, and `CLAUDE_CODE_SESSION_ATTENDED` made
it enforceable rather than merely documented — a blocking task now refuses an
explicit `--model` from an unattended session, failing closed on a missing
flag. Non-blocking tasks are untouched; execution must never wait for a human.

**M-16, when entries are cancelled.** `cancel_unfilled_entries()` lived only
in `close`, which runs after 16:00 — after the closing cross, the largest
print of the day and the event most likely to fill a resting limit. Correctly
scoped, wrongly timed. The overnight case is worse: a GTC buy limit **gaps
through its own protection**, since an open below the limit fills at the open
price, which can be under the stop. New `trading_day preclose` closes the
entry book inside the management window and re-reads
`positions_without_stops()` afterwards, failing the session if cancelling left
anything naked — while the market is still open and something can be done.
`close` keeps the cancellation as a backstop.

**Lesson for future rules:** all three are the same shape. A control read a
value that described the environment rather than the session, or ran at a
moment chosen for convenience rather than for the risk. **Ask of every gate:
what exactly is this measuring, and is it the thing I am about to bet on?**
And note which of the three was fixable only by admitting uncertainty, and
which two had a real measurement available all along — the difference is worth
checking before settling for a caveat.
**Status:** active.

---

## 2026-09-22 — six years of data overturn a one-year conclusion (M-23, M-24)

`python3 -m tools.pit_study --fetch` now covers 2020-07-01 onward (2,472
symbols, 51MB, 0 batches dropped) because the feed's real start was 2020-07-27
and nobody had asked. Six study years replaced one. Full numbers in
`docs/16-entry-study.md`; the lessons are here.

**The reversal.** The 2026-only entry study concluded that resting a limit at
the broken level (retest) beat chasing the next open, +0.092R vs +0.054R, and
`docs/16` recommended it. Across six years **retest won in exactly one — 2026,
the year that was studied.** Sign test p=0.219, paired t=−1.2.

The process failure is worse than the data error. My prior before that study
was that chase would win. One year reversed it, I wrote up the reversal
honestly as a corrected prediction, and six years says the original prior was
right. **A single year did not merely fail to confirm a hypothesis — it
pointed the wrong way with enough confidence to overturn a correct instinct,
and the write-up made that reversal look like rigour.** The habit of recording
"I predicted X and was wrong" is worth keeping, but it is not a substitute for
asking whether the sample could have told the difference. Here it could not:
t=+1.7 is what a coin produces about one time in eleven.

**The statistic that was nearly quoted.** Pooled over all 13,912 chase trades
the expectancy is +0.096R at **t=5.6**, which reads as decisive and is not.
Trades inside one year share the same market and are not independent draws.
**Year as the unit of observation: +0.079R, t=+1.4.** Six years of daily bars
on 2,472 names and the edge is still inside the noise. `tools/multiyear.py`
now prints both, with the pooled figure labelled as the one not to use. The
general form: *a t-statistic is a claim about independence before it is a
claim about significance, and pooling is where that claim gets made silently.*

**M-23 — the regime dependency is larger than the edge.** 2022 chase returned
**−0.168R over 2,110 signals, t=−4.9, −355R total.** A long breakout strategy
loses steadily and significantly in a bear year. The spread between the worst
year and the best is 0.36R against a six-year mean of 0.079R, so *which year
you are in matters four times more than the strategy does.* One year of study
hid this completely. This is the strongest evidence yet for a regime gate in
`engine/` rather than posture prose in a skill, and it is queued — **no rule
changes today**, because the evidence standard in CLAUDE.md asks for a
backtest showing a better median outcome without a worse ruin rate, and that
backtest has not been run.

**M-24 — what did survive, and it is structural.** The two entry arms fill the
same 10,117 signals, so the difference decomposes exactly:

```
pulled back, chased          10117 trades  -0.227R
the same signals, on retest  10117 trades  +0.078R   waiting is worth +0.305R
never pulled back, forfeited  3795 trades  +0.957R   the entire shortfall
```

Both halves hold in all six years — including 2022, where the no-pullback
group made +0.571R while everything else lost money. Year-level t=12.1, the
only result here that clears significance comfortably. **Waiting for the
pullback is the better entry on the trades it gets, and loses anyway because
it forfeits the trades that never come back.** So D-24's question was
mis-framed: the ETHA entry style was not the error. Being forced to choose
between the two groups at signal time is, and that is a property of the
design, not of the day.

**And still nothing separates them at signal time.** The 2026 negative result
generalises rather than dissolving. No feature's Q5−Q1 return spread clears
the year-level bar; best is t=1.8 at 4/6 (atr_%) and 5/6 (breakout_%)
consistency. The mechanism is the same cancellation found in one year:
breakout_% moves the *label* by +0.40 (11%→51% never pull back) and captures
only **35%** of the return that implies, because within the no-pullback group
it predicts return *negatively* (−0.363, negative in 4/6 years). It selects
the right group and then the worst members of it — a big breakout is less
likely to give the level back *and* has less room left to run, and you cannot
buy the first property without paying for the second.

**A hypothesis I had and checked rather than asserting.** atr_% had the
largest spread and almost no label effect, so I suspected the stop floor:
`max(entry − 1.5·ATR, entry×0.92)` binds above atr_% ≈ 5.33, making R a ratio
to a denominator the trade never chose. Only 6.6% of trades are floor-bound,
and dropping them makes the spread *larger* (+0.186 → +0.218). Wrong
hypothesis. It changes no rule regardless — t=1.8 at 4/6 is weakness, not
arithmetic — but the reason matters for the next person who looks at it.

**Standing caveat, recorded before any early year gets believed.** The
universe comes from `/v2/assets` as it stands today, so names delisted before
today are absent. Symbol counts rise monotonically, 1,944 with bars in 2021 to
2,471 in 2026 — delistings and IPOs mixed, inseparable in this data. Every
year is biased upward and the early years most. An edge that *grows* into the
past is suspect for that reason alone, and 2022 being the worst year is if
anything understated.

**Status:** active. No `engine/` change; two queue items opened.

## 2026-09-22 — D-17 reproduced; a test that was measuring the machine (M-4, M-26, M-27, M-28)

**D-17 is settled, and the split probe is why.** On 2026-09-17 a fractional
bracket was rejected with `fractional orders must be simple orders` — an
`order_class` refusal, which is the whole evidentiary basis for whole-share
sizing and the ~$75 single-position ceiling. When brackets became GTC on
2026-09-18 the identical probe came back `fractional orders must be DAY
orders`: the broker now refuses on `time_in_force` and **never reaches the
class check**. The tool went on printing D-17's conclusion for four days from
evidence that had stopped supporting it. Split into two probes overnight, both
answered this morning, HTTP 422 both times:

```
fractional + gtc  -> {"code":42210000,"message":"fractional orders must be DAY orders"}
fractional + day  -> {"code":42210000,"message":"fractional orders must be simple orders"}
```

The ceiling stands on reproduced evidence. **The general form is worth more
than the result:** a probe's conclusion can be invalidated by a change
somewhere else entirely, and it fails by continuing to print the right answer
for the wrong reason. Our own GTC fix broke this test's meaning without
breaking the test. Anything that asserts a broker constraint should probe one
constraint at a time, or it cannot tell which one it measured.

**The same failure, one layer up, on the same morning.** `preflight_phase2`
exited 1 on a suite that was green overnight with no code change between. The
gate tests patch the environment with `clear=False`, so a variable a test does
not pin falls through to the real one — and M-17's fix had just made
`CLAUDE_EFFORT` the value that decides. `xhigh` overnight, `high` at 09:35,
same assertion, different answer. **A test about the environment was being
decided by the environment.** Fixed by pinning, verified under three ambient
environments; no production code touched.

**And the same failure again, in the control adopted the night before.**
`is_attended()` returns `True` in this unattended scheduled firing, because
`CLAUDE_CODE_SESSION_ATTENDED` is set at the *environment* level — one
constant answering a per-session question, exactly like `TRADING_AGENT_MODEL`
before it. M-22 was adopted to stop a session self-certifying, and as
implemented it does not bind. Recorded as M-26, not fixed here: an unattended
session tightening the control that decides whether it is trusted is the wrong
hand on that lever.

Three instances in one morning of a single pattern: **a check whose input
cannot vary with the thing it claims to measure.** Every one of them failed
permissive, and every one of them printed `ok` while doing it.

**Status:** no `engine/` change, no rule changed. D-17 confirmed. M-26, M-27
and M-28 opened in `state/reviews/2026-09-22-queue-m.md`; M-28 fixed there.

---

## 2026-09-22 — M-22, second attempt: the gate that never bound (M-26)

Authorized by recalcitrantmaus, attended, Opus 5 @ xhigh verified from the session record.
Recorded in `state/authorizations.jsonl`.

**What was wrong.** `is_attended()` read `CLAUDE_CODE_SESSION_ATTENDED` and
returned True on `"1"`. That variable is set environment-wide, so it read `1`
in every session — attended or not — and the gate never refused anything, once,
ever. Demonstrated end to end on 2026-09-22: an unattended scheduled relay
session ran `model_check --model claude-opus-5 rule-promotion` and got exit 0.

It is the third instance of the pattern named in the entry above, and the
worst, because it shipped *in the same commit* as the fix for the other two —
one function below a comment warning that a blocking task must not clear on "a
value that cannot vary with the thing being checked."

**The proposed fix was also wrong, and the session that proposed it is the
counterexample.** The plan was to require
`TRADING_AGENT_ATTENDED_SESSION == CLAUDE_CODE_SESSION_ID`, so that an
environment-wide value could satisfy at most one session. But a scheduled
relay fired into session `38d73c9c` at 14:20Z with no human present, and recalcitrantmaus
typed into that same session at 15:45Z. Same session id, same environment,
same variables; attendance changed.

**Attendance is a property of the TURN, not of the session or the
environment.** Environment variables are snapshotted at session start, so no
variable — of any scope, however cleverly bound — can track it. Two wrong
fixes in two days, both of them environment reads, before the category error
was visible: *I kept looking for a better variable when the problem was that
attendance is not a variable.*

**What replaced it.** The gate no longer tries to detect a human. It requires
the override to be SAID and it records it:

```
python3 -m tools.model_check rule-promotion --model claude-opus-5 \
    --authorization "<what is being changed and why, in the human's words>"
```

Appended to `state/authorizations.jsonl` — committed, not ignored — with task,
model, session id and timestamp.

**Be exact about what this buys, because overstating it is how the first
version happened. It is attributable, not enforceable.** Nothing in-process
can establish that a human is present: any check the process can read, the
process can satisfy. A session could fabricate the string. What it cannot do
is fabricate it without leaving a dated, session-stamped claim in the
repository.

Two things *are* enforced, and they cover the realistic failure — which was
never an adversarial agent:

- **A trivial authorization is refused.** "ok", "yes", "approved", anything
  under 12 characters. Self-certification wearing a string is still
  self-certification.
- **A verbatim-reused authorization is refused**, case- and
  whitespace-insensitive. This is the one that matters: a canned string pasted
  into a Routine prompt would otherwise clear the gate on every firing,
  unattended, forever. A nonce that must be new each time cannot be put on a
  schedule. The nonce is spent only when the whole check passes, so a run
  refused on tier or effort does not burn it.

**Verified:** 171 tests (9 new, replacing 4 that encoded the broken
behaviour), green under `CLAUDE_EFFORT` in {low, high, xhigh} x
`CLAUDE_CODE_SESSION_ATTENDED` in {0, 1} and with both unset — because this
morning's regression was a test suite that the environment decided. One test
exists purely to go red if `CLAUDE_CODE_SESSION_ATTENDED` is ever honoured
again. Monte Carlo suite unchanged at 300 seeds, 0.0% ruin across all arms,
which is the expected result: this gate is consulted only for blocking tasks
and never touches the trading path. `execution` still requires no
authorization, by an explicit test — execution must never wait on a human.

**Status:** active. M-22 and M-26 closed.

---

## 2026-09-22 — the feed was never a detail (M-30, M-29)

Authorized by recalcitrantmaus. Two bugs the open session found this morning, both of the
same family — data that means something other than what it appears to mean —
and the first one turned out to be much larger than reported.

### M-30: `feed=iex` was a guess that was never re-tested

`AlpacaAdapter.bars()` pinned `feed=iex` because the free plan was believed to
serve nothing else. **It serves `sip`.** Nobody had checked since; the belief
was load-bearing and untested, and one `curl` settled it.

IEX is a single venue carrying a **median 3.8% of consolidated volume** (the
calibration comment in `CRITERIA` said ~4% and was right). The thing to see is
that a 3.8% sample does not misprice a *mean* — prices agree to a cent, AAPL
342.30 IEX against 342.29 SIP. It misprices an **extremum**, and an extremum
is the only statistic this series is used for. Measured across 59 universe
names on completed sessions:

```
ATR(14) IEX/SIP : median 0.976, mean 0.936, worst 0.571
                  SMALLER IN 59 OF 59 NAMES
20-day high     : understated in 43/59, worst -0.913%
20-day low      : OVERstated  in 41/59, worst +0.487%
phantom breakout: 1 of 59 names on the day measured
```

Every one of those is one-directional, for a reason that is arithmetic rather
than statistical: **a subset of prints cannot contain a higher high or a lower
low than the whole.** So the error could never average out with more data, and
no amount of live trading would have surfaced it as noise.

Three consequences, and the one that was reported is the smallest:

1. **Phantom breakouts.** RKLB at 13:50Z: IEX said the 20-day high was 70.56
   and the price 70.76, so the screen fired. Consolidated said 71.21 — the
   price was 45c *below* resistance. (By 16:07Z RKLB had traded to 71.39 and
   was a genuine breakout on both feeds. The fix would have refused it in the
   morning and allowed it in the afternoon, correctly both times. It did not
   "save" a trade, and saying so would be the wrong lesson.)
2. **Every stop too tight**, in 59 of 59 names, by a median 2.4% of ATR and up
   to 43%. This was not in the original report and matters more.
3. **Support levels too high**, symmetrically, for the same reason.

On (2), be precise about what does and does not break. Dollar risk at the stop
is *unaffected*: size follows the stop, so a tighter stop buys more shares for
the same 2%. What changes is that the share count rises, so **gap exposure
scales up with the error**, and a stop set inside the noise band gets taken out
by noise. It is an expectancy leak and a gap-risk amplifier, not a breach of
the 2% rule.

**The fix is not a blanket feed swap**, because SIP on this plan is **15
minutes delayed** (measured: IEX last minute-bar 16:03Z, SIP 15:49Z) and
`/v2/stocks/snapshots` rejects `feed=sip` outright. `paper_session` was reading
`bars[-1].close` as the entry price, so switching the feed naively would have
priced entries, stops and targets off a quarter-hour-old number. So:

- **completed sessions → SIP.** They do not change, so the delay is irrelevant,
  and levels and ATR are finally consolidated.
- **the price now → `AlpacaAdapter.last_trade()`**, new, real-time, IEX.
  Returns `None` rather than a guess; a missing price stands the symbol down.
- `breakout_now(hist, price)` takes the level and the price from different
  places by construction, so the two can never be silently re-coupled.
  `breakout_at` remains for history, where a completed bar's own close is the
  right thing.

### M-29: a threshold that was a function of the clock

`build_universe` read `dailyBar`, which during the session is a **partial**
bar. Building at 09:50 ET measured twenty minutes of volume against a full-day
floor: a $1.5M threshold behaved like roughly $30M/day and dropped MARA,
CMCSA, MNST, ZTS, TFC and KR — all plainly liquid. Measured at 11:58 the same
day, today's dollar volume ran **0.25x to 1.46x** of the prior completed
session across ten names.

Worse than wrong, it was not **reproducible**. The scan walks ~11,800 assets
over several minutes, so the effective floor moved *during a single build* —
KR was excluded while the build ran and passed minutes later. The docstring at
the top of `screen.py` promises a universe that "must mean the same thing when
someone re-reads the decision next week", and with a partial bar it did not
mean the same thing an hour later.

Now `prevDailyBar`: a completed session, identical at 09:31 and 15:59. The
universe went 110 -> 150 names (the `size: 150` cap binding again rather than
the floor) and all six named names returned. Two consecutive builds now
produce **identical symbol lists, identical dollar volumes and an identical
session label.** The IEX calibration is untouched and still correct, because
snapshots cannot serve SIP anyway.

### Two smaller things found while fixing these

- The build report printed **"min $2M dollar volume" for a $1.5M floor** —
  `.0f` on 1.5. Anyone auditing the universe would have recorded the wrong
  threshold. Same disease as the rest of this entry: the report did not say
  what the code did.
- **A provenance field I introduced, wrong within the hour.**
  `liquidity_session` took whichever symbol the API returned first, and a name
  that had not traded in a week carried a week-old `prevDailyBar`. Two builds
  selecting *identical* universes labelled themselves 2026-09-14 and
  2026-09-21. It was caught only by the reproducibility check written for
  M-29, and it is now the mode across the names that actually made the cut,
  with any others listed. **A provenance field that is wrong is worse than no
  provenance field, because it is believed.** I wrote this one while fixing two
  bugs of exactly its kind.

**Verified:** 179 tests (8 new), including one that pins the RKLB phantom
against both tapes and one that pins the stale-name relabelling. Monte Carlo
unchanged at 300 seeds, 0.0% ruin across all arms.

**Status:** active. M-29 and M-30 closed.

---

## 2026-09-22 — T-1: the book had no risk cap, and diversification is not available (T-2)

Authorized by recalcitrantmaus. Two changes, one mechanism, because the evidence
collapsed them into one.

### What was wrong

Per-trade risk capped at 2%, concurrency capped at 4, **nothing capping the
sum.** Measured, not inferred — four proposals engineered to the full
per-trade budget:

```
SYM0 APPROVED  open risk 2.0%      MAX SIMULTANEOUS OPEN RISK: 8.0%
SYM1 APPROVED  open risk 4.0%      daily_loss_halt_pct  4%
SYM2 APPROVED  open risk 6.0%      weekly_loss_halt_pct 8%
SYM3 APPROVED  open risk 8.0%
SYM4 REFUSED   already at max 4 positions
```

Twice the daily halt, exactly the weekly one, in one correlated move. And the
breakers cannot close that gap: `daily_loss_halt_pct` stops NEW trades once
-4% is realised — it cannot unwind stops already resting on the book. Today's
five real signals took four positions at **4.53% aggregate, already past the
daily breaker**, with no gate objecting.

### T-2: why there is no sector rule

The instinct was to enforce sector diversification. The measurement says that
instrument does not work. 60-day daily-return correlation, SIP bars, on the
day's own six signals:

```
        ASX    STM   DRAM   MCHP   JEPQ   RKLB    SPY
ASX    1.00   0.67   0.76   0.58   0.78   0.59   0.61
STM    0.67   1.00   0.64   0.72   0.76   0.54   0.59
DRAM   0.76   0.64   1.00   0.60   0.78   0.51   0.45
MCHP   0.58   0.72   0.60   1.00   0.71   0.59   0.61
JEPQ   0.78   0.76   0.78   0.71   1.00   0.64   0.83
RKLB   0.59   0.54   0.51   0.59   0.64   1.00   0.61
```

Three things kill the sector approach:

1. **DRAM is an ETF.** Its SIC code says "investment trust". It correlates
   0.76 with ASX and 0.64 with STM. A sector label misses the most obviously
   concentrated name in the set.
2. **JEPQ is the most correlated name here** — 0.71 to 0.78 against every
   semiconductor, 0.83 against SPY — and no sector rule would ever flag a
   broad-market income ETF.
3. **The minimum pairwise correlation is 0.45.** Even a space company against
   a semiconductor. There is no uncorrelated pair to diversify *into*.

**A long-only breakout book is a single directional bet, always.** So "four
independent trades at 2%" is close to one 8% position, and the lever is the
total, not the selection. T-1 and T-2 are the same control.

### Choosing the number, and what the evidence actually showed

CLAUDE.md asks for a backtest with a better median and no worse ruin. The
first sweep (300 seeds, 6 caps, 3 strategies) **failed that test**: tightening
the cap produced a *worse* median (300.62 at 2% vs 308.40 at 8%) at an
identical 0.0% ruin. Reported rather than worked around.

Two things had to be checked before drawing any conclusion from that:

- **Is the sim as correlated as reality?** If it were more diversified it
  would understate the cap's value. It is not: sim pairwise correlation runs
  min 0.43 / median 0.61 / max 0.86 against the real 0.45 / 0.63 / 0.83. The
  inconvenient result stands on its own merits.
- **Is `ruin` measuring anything?** No. It is a 50% loss and it is 0.0% at
  every cap, so *"without a worse ruin rate"* is trivially satisfied by
  everything and carries no information in this regime. The LOCKED rate
  (-20% from peak, flatten, human only) is the operative catastrophe metric —
  but at 300 seeds it was 1 to 4 events and **non-monotonic**, i.e. noise. A
  4x reduction was there to be claimed and it would have been wrong.

Resolved at **3000 seeds**, momentum_breakout, 260 days:

```
 cap   median    p05    maxDD  worstDD   LOCKED  n_lock
  4%   302.27  264.35    8.9%    20.9%    0.50%      15
  8%   305.42  264.56    9.3%    21.5%    0.90%      27
```

**The cap costs -$3.15 of median equity — 1.05% over a year — and roughly
halves the locked-account rate, 0.90% to 0.50%.** z = -1.86 on the lock
counts, marginal alone, but corroborated by two independent monotonic
metrics: mean max drawdown 9.3% -> 8.9% and worst 21.5% -> 20.9%.

So it is not a free win. It is a priced trade-off, and the price is ~1% of
median annual return to halve the outcome that ends the account. For a system
whose first line calls itself capital-preserving, and whose own lessons record
that optimizing for return selects for strategies that ruin 94% of accounts,
that is the right side of the trade. **Set at 4% so the invariant is
checkable: if every stop filled at once, the loss is exactly the daily halt,
and the breaker becomes a ceiling rather than a marker read afterwards.**

### Implementation notes worth keeping

- Risk is measured **from the current price, not from entry**, so a trailed
  stop genuinely returns budget to the book. A position at breakeven consumes
  nothing and the book should be free to use the room.
- A position with **no stop counts its full notional.** Nothing should ever
  create one, but its loss is unbounded, and a risk total that quietly skips
  it is exactly the comforting-number failure this project keeps finding.

### One more thing the sweep exposed

`graduated_swing` and `momentum_breakout` returned *identical* numbers at
every cap, because the option leg is locked below $1,500 equity and
contributes nothing at $300. They are the same experiment reported twice in
the suite, not two independent confirmations. Worth knowing before either is
cited as corroboration.

**Verified:** 184 tests (5 new). Sim suite re-run at 300 seeds, 0.0% ruin.

**Status:** active. T-1 closed; T-2 answered and closed as not-implementable
by sector, with the aggregate cap standing in its place.

---

## 2026-09-22 — model floors raised for the open, pre-close and close

Authorized by recalcitrantmaus, recorded in `state/authorizations.jsonl`.

`premarket-brief`, `trade-plan`, `pre-close` and `session-close` move from
Sonnet @ xhigh to **Opus @ xhigh**. `execution`, `news-intel` and
`trade-journal` stay at Sonnet.

**The argument is about data, not difficulty.** The risk engine protects
against bad decisions; it cannot protect against bad data. A proposal built on
a wrong number passes every gate, because the size, the stop and the expected
R are all computed correctly *from that number*. RKLB would have cleared the
entire engine on a 20-day high 0.91% too low, and the same defect had ATR
wrong in 59 of 59 names. Only a model suspicious of its own feed caught it.

The open is also the only session that **forms beliefs about the world**; the
others execute against beliefs already formed. So the asymmetry follows the
task rather than the phase, and it will not expire when strategy testing does.
Pre-close prices overnight gap risk across a book correlating 0.45-0.83, where
a gap does not respect stops. The close is where findings are promoted or lost
— Monday's close found M-16 unprompted and declined a `--model` override it
was entitled to reach for.

**This floor is meant to be earned down, and that should be said out loud.**
Every artifact a model finds should become a deterministic check;
`cross_check()` exists for prices and belongs on levels and ATR next. Opus at
the open is right while the data layer is still surprising us — not forever.
Cost is a real input to that: this is not free, and the schedule should be
revisited once the data checks are code.

**Status:** active.

---

## 2026-09-22 — the size taper: "let one run" as size, not as targets

Authorized by recalcitrantmaus. The second half of T-2, and unlike everything else
today it is a clean win rather than a priced trade-off.

### Why size and not targets

The instinct was conservative targets on most positions with one allowed to
run. Targets are the wrong lever for that intent. **A target controls upside;
size and the stop control loss.** Trimming targets on the also-rans would give
up exactly their winners while keeping their full downside — the opposite of
the intended effect. Cutting SIZE gives the first and strongest position full
weight and makes every subsequent add cheaper to be wrong about, which is what
"conservative on most" actually means in a loss sense.

`correlated_risk_decay = 0.5`: the nth concurrent position gets
`2% x 0.5^(n-1)` — 2.00%, 1.00%, 0.50%, 0.25%.

**It takes no correlation input, and that is a measurement rather than a
convenience.** The minimum pairwise 60-day correlation across the day's own
signals was 0.45, including a space company against a semiconductor. There is
no uncorrelated pair to detect, so treating every addition as correlated is
both the honest default and the conservative one — and it keeps the risk
engine deterministic, with no live data or network call inside `evaluate`.

### The sweep

2000 seeds first, then confirmed at 3000 on two strategies:

```
momentum_breakout, 3000 seeds
 decay   median     p05   maxDD  worstDD   LOCKED  trades
  1.00   302.27  264.35    8.9%    20.9%    0.50%    44.0
  0.50   303.92  274.35    6.4%    17.8%    0.00%    40.9
        median +1.65   locks 15 -> 0   z = -3.88

trend_pullback, 3000 seeds
  1.00   301.91  281.25    4.8%    13.8%    0.00%    15.5
  0.50   302.19  284.15    3.9%    11.3%    0.00%    14.0
```

**Better median, better p05, lower drawdown and fewer locks, all at once.**
That is a Pareto improvement, unlike the portfolio cap earlier today which
bought safety by giving up 1% of median — and it is worth being clear that
the two are different kinds of result rather than presenting both as wins.

The mechanism is visible in one column: **worst drawdown 20.9% -> 17.8%.** The
lock threshold is -20%. The taper pulls the worst case under it, which is
exactly why 15 locked accounts become 0.

A suspicion worth having had: at $300 with whole-share sizing, a tapered 3rd
or 4th budget might round to zero and simply DELETE positions rather than
shrink them — a different rule than the one intended. Trade count says mostly
not, at this decay: 44.0 -> 40.9, about -7%.

### Measured on the day's own signals

```
before (neither rule)   4 pos  ASX STM DRAM RKLB   risk 4.53%   deployed 78%
cap only (4%)           4 pos  ASX STM DRAM JEPQ   risk 3.17%   deployed 75%
cap + taper             3 pos  ASX STM JEPQ        risk 1.96%   deployed 53%
```

4.53% — above the daily breaker — down to 1.96%.

### The side effect nobody asked for, recorded because it is real

Look at which names survive. RKLB (ATR 3.36, ~$5.04 of risk per share) drops
out; JEPQ (ATR 0.64, ~$0.96 per share) stays. At $300 with whole shares, a
tapered budget of $1.50 cannot buy one share of anything risking $5, but can
buy one risking $1. **The taper therefore biases the 2nd and 3rd slots toward
LOW-VOLATILITY names.** That is defensible — smaller slots holding quieter
instruments is coherent — but it is a selection effect introduced by a sizing
rule, it was not asked for, and it will disappear as equity grows and rounding
stops binding. Logged as T-7 so nobody rediscovers it as a mystery.

### How the two rules relate

They are not redundant. 2.00 + 1.00 + 0.50 + 0.25 = 3.75%, inside the 4% cap,
so **the taper usually binds first and the cap is a backstop.** The cap is the
guarantee — it holds if `max_concurrent_positions` is ever raised, or if a
future strategy sizes differently. The taper is the shaping. One test exists
purely to pin that arithmetic, and the cap's own test now disables the taper
so it still isolates what it claims to.

**Verified:** 189 tests (5 new). Four of them failed first and were wrong, not
the code — at $30k the position cap bound before the risk budget, and one
fixture had R=0.50 so it died on expected-R before sizing ran at all. The
tests were passing judgement on the wrong gate, which is the same failure this
file keeps recording. Sim suite green, 0.0% ruin.

**Status:** active. T-2 now fully answered: no sector rule (not implementable
on this universe), an aggregate cap, and a size taper.

---

## 2026-09-22/23 — T-9, T-8 and T-10: three checks that could not fail

Authorized by recalcitrantmaus. All three came out of the Tuesday close session, and they
are one family: a check whose input cannot vary with the thing it claims to
measure, so it reports success on nothing.

### T-9 — "today" was the container's date, not the exchange's

`drift_today()` keyed on `dt.date.today()` and matched UTC timestamps by
string prefix. Two faults:

- **UTC midnight is 20:00 ET** — four hours after the close, on the same
  session's evening. So the drift window opened the previous evening.
  Tuesday's four readings included one from Monday 22:32 ET.
- **`date.today()` is the HOST's date.** The same code on an ET machine would
  compare an ET date against UTC timestamp strings and bucket differently, or
  match nothing at all. A check decided by where it runs.

Harmless at +0.0000. Not harmless afterwards: the cumulative figure feeds
`drift_halts`, so an evening's drift would count against the wrong session —
and crypto, which the plan permits, fills around the clock.

Now one named function, `trading_date()`, on `ZoneInfo("America/New_York")`
rather than a fixed −05:00, so DST is carried rather than remembered. **Every**
"today" in the module moved to it — `cmd_open`, `cmd_close`, `cmd_preclose`,
the week key and the day-start key — because a drift window bucketed on ET
while the halt baselines bucketed on UTC would be worse than either alone.

Verified live: UTC date 2026-09-23, trading date 2026-09-22, and the Monday
evening reading moved back where it belongs — Tuesday 3 readings, Monday 5,
where the old keying reported four for Tuesday.

**Two things went wrong in the fix itself, and both are the same bug as the
one being fixed.** The tests mocked `dt.date`, but `trading_date()` reads the
clock through `datetime.now()`, so the mock stopped reaching it — the seam had
moved. And the replacement helper pinned the *conversion* as well as the
clock, which relabelled Friday's timestamp as Monday and pulled a stale
reading into today's total. Mis-bucketing, reintroduced inside the helper
written to prevent mis-bucketing. The helper now pins only "now".

The suite is green under UTC, America/New_York, Asia/Tokyo and
Australia/Sydney, and one test exists purely to assert that the answer does
not depend on when the suite runs.

### T-8 — a flat account read three-fifths of the way to Phase 2 exit

"zero guardrail breaches", "costs below gains" and "never LOCKED" all passed
**vacuously**: `all()` over an empty list is True, and costs carried an
explicit `if trades else True`. Each is a defensible vacuous truth alone.
Together they printed three `[ok]`s for an account that had never traded.

Same shape as Monday's "no protective leg was stripped — vacuously, with no
position", now in a published scorecard rather than a session note. **A check
that cannot fail is not evidence, and a scorecard that cannot tell "passed"
from "never ran" rewards doing nothing.**

Three states now: `[ok]`, `[XX]`, and `[--] not yet measurable`, with the exit
gate requiring every criterion to be measurable AND passed.

The first attempt keyed measurability on *sessions observed* and was too
weak — it still printed two `[ok]`s, because you cannot breach a rail you
never touched and LOCKED needs a −20% drawdown, which needs losses, which
needs trades. **A guardrail that was never exercised was not honoured; it was
untested.** So measurability keys on trades, and everything except the trade
count is unmeasurable until the account trades:

```
  [XX] 30+ closed trades          0/30
  [--] positive expectancy        no closed trade with a stop
  [--] zero guardrail breaches    0 escalations over 7 session(s)
  [--] costs below gains          no trade has cost anything yet
  [--] never LOCKED               7 session(s) observed

  0/5 met, 4 NOT YET MEASURABLE
```

Three-fifths became zero. Inactivity now scores nothing.

### T-10 — a per-turn value, checked once. PARKED, not wired in.

`CLAUDE_EFFORT` moved **high (13:39Z) → medium (20:07Z) inside one session**.
CLAUDE.md's blanket claim that environment variables are snapshotted at
session start is not true of it: it tracks the turn. For M-17 that is good
news, since the value chosen as the measurement really does measure.

The problem is the gate. `check()` runs once at task start and nothing
re-reads it, so a blocking task that clears at `xhigh` can perform its durable
write at `medium` with no signal. On 2026-09-22 `session-close` ran two
notches below its floor and only the journal recorded it.

**This is the third member of a family found inside two days.** Attendance is
a property of the turn (M-22/M-26). Effort is a property of the turn. Both
were being read as though they described a session. The general lesson is
sharper than any of the three fixes: *ask not only what a value measures, but
over what interval it is true.*

`recheck()` is written and tested and **nothing calls it** — parked at recalcitrantmaus's
request, to be incorporated deliberately at the end of a session rather than
dropped into a live trading day. It re-reads effort at the durable write, not
at task start, because that is where a downgrade costs something. It does not
re-verify the model: passing `--model` is a human's act, already recorded and
single-use, and the model does not move under a session the way effort does.
One test fails the moment anyone wires it in, as the reminder to delete the
banner and add the call sites.

**Verified:** 206 tests (17 new). Sim suite green, 0.0% ruin, medians
unchanged. Suite green under four timezones.

**Status:** T-9 and T-8 active. T-10 parked.

## 2026-09-23 — three controls that never reached the path that sends orders (T-12, T-13, T-14)

Found live, with the market open, by writing down what the engine *should* do
before running it. The plan for 2026-09-23 predicted RKLB would be refused on
the tapered risk budget. The engine approved it at 1.70% of equity. The
prediction was right and the runner was wrong, and that gap is the only reason
any of this was found.

**The habit is the finding.** Two sessions of "propose, run, report what
happened" would not have caught this, because the output looked correct: two
plausible orders, sensible sizes, no error. It is only wrong against a stated
expectation. `state/plans/2026-09-23.md` now carries a "what I expect the
engine to do, written before running it" section for that reason.

### T-12: the runner handed the engine the same empty book every time

`RiskOfficer.evaluate` reads both of the controls added on 2026-09-22 out of
the portfolio it is given:

```python
n_open = len(portfolio.positions)          # the taper
taper  = c.correlated_risk_decay ** n_open
risk_room = max(0.0, eq * c.max_portfolio_risk_pct
                - portfolio.open_risk(prices))   # T-1's aggregate cap
```

`tools/paper_session` looped over proposals calling
`ro.evaluate(p, pf, prices, today)` and **never mutated `pf`**. So inside one
session every proposal was gated as though it were the first: `n_open` stayed
at the count of pre-existing broker positions, `open_risk` stayed at their
risk, and both controls were inert.

Measured on the four-name case in `tests/test_session_gating.py`: four
proposals at $10 risking $0.60/share each take 7 shares apiece on the
single-position cap, for **$16.80 of book risk on a $300 account — 5.6%, past
the 4% cap and past the daily halt.** That is T-1's 8% book, restored in full,
one day after T-1 was closed.

This is T-1's own failure mode one layer up. The control was written into
`engine/`, unit-tested in `engine/`, and never wired into the only caller that
sends orders. **No engine-level test could have found it**, because from
inside the engine both controls work perfectly — they were simply never asked
a question that had a book in it. Note the wording in the T-1 entry: the five
signals were run "through the engine *with the portfolio actually updating*".
That measurement used a bespoke harness. Production did not do it.

Fixed: the approved order is reserved into `pf` (position and cash) before the
next proposal is gated. Reserved at **approval**, not at fill — a submitted
bracket has already committed the risk, and reserving early can only make the
engine refuse more, never less.

### T-13: every refusal has been naming the wrong constraint

Surfaced by the T-12 fix. `Decision.reject` **appends** the binding constraint
to `reasons`, and `evaluate` appends informational notes before reaching it.
The runner printed `d.reasons[0]`.

So RKLB's refusal — genuinely on the tapered risk budget — was logged as:

```
REJECT RKLB: expected R 2.00
```

"expected R 2.00" is a **passing grade**, not a reason to refuse anything. The
log named the reward-to-risk gate for a refusal that gate did not make. Every
refusal on this path is suspect for as long as this has been live, and the
approval branch was always correct (`d.reasons[-1]`), which is why nobody
looked.

This matters more than its one-character fix suggests. The daily routine's
instruction is that *a refusal nobody can check is not a decision*. A refusal
that names the wrong control is worse than an unlogged one: it reads as an
audit trail while pointing at the wrong place, and the rejection histogram
(M-4) counts it into the wrong bucket.

Fixed: print `reasons[-1]`. Pinned by a test that asserts the logged line
names the constraint that actually bound *and* that a genuine expected-R
refusal still says so.

### T-14: a carried position arrived without the stop that was resting for it

Found by reasoning forward rather than by a failure — the DT order placed this
morning is still resting, and the question was what tomorrow's session would
do with it once filled.

`paper_session` rebuilt broker positions as `Position(..., opened_at=today)`
with no `stop`. `Portfolio.open_risk` counts a stopless position at **full
notional**, deliberately and correctly, since an unstopped loss is unbounded.
The arithmetic on a single filled DT share:

```
open_risk   = 1 x 58.47        = $58.47   (19.5% of equity)
cap         = 0.04 x 299.99    = $12.00
risk_room   = max(0, 12 - 58.47) = $0.00  -> every entry refused
```

The account would have frozen the next session, and the refusal would have
read `portfolio open-risk cap ($58.47 already at risk)` — a guardrail's
message, for what is actually an outage. **A conservative failure is still a
failure, and it is the harder kind to see, because it looks like discipline.**
The true risk was $2.67: the stop was resting at the broker the whole time and
was never asked for.

Fixed: `AlpacaAdapter.resting_stops()` returns the live stop *price* per
symbol (widest stop wins on a tie), and the rebuild carries it onto the
`Position`. `positions_without_stops` answers a different question — *is* it
protected — and could not be reused. Verified against the live broker with
DT's held bracket leg: `resting_stops() -> {'DT': 55.8}`.

The fail-closed path is kept and tested: if the stop cannot be retrieved, the
position still counts at full notional. The fix must not soften the rule it
was hiding.

### What pinned it

`tests/test_session_gating.py`, 9 tests, driving the real `main()` loop
against a fake broker rather than inspecting its source — the lesson of the
2026-09-22 parked-check test, which grepped for a name instead of parsing for
a call. Mutation-checked: with all three fixes reverted, 5 of the 9 fail; with
them in place, 215/215 pass and `sim.run_suite --seeds 300` reports ruin 0.0%
on every strategy.

### The pattern, stated plainly, because it is now four for four

T-1, M-22/M-26, M-30, and now T-12/T-13/T-14 are the same defect wearing
different clothes: **a control that is correct in isolation and is never
handed the state that makes it bind.** The engine is not where these live.
They live at the seam between the engine and its caller, and every one of them
was invisible to a test that exercised only one side of that seam.

The standing check that follows from it: for each control in `engine/config.py`,
name the caller that supplies its input, and write one test that drives the
caller. A control with no such test should be assumed inert until shown
otherwise.

---

## 2026-09-23 — the first fill, and a stop that never went live

> **WRONG, CORRECTED 2026-09-24.** `held` is the normal working state for a
> stop leg, not a fault. The conclusion below was reached without the vendor's
> own explanation, which was one forum thread away. See the correction that
> follows this entry. The flatten it justified cost $0.37 on a misreading.


Phase 2's first fill, and it produced three findings in twenty-four minutes.
Authorized by recalcitrantmaus.

### What happened

DT filled 1 share @ 58.47 at 14:04:57Z. Its bracket legs then read:

```
sell limit 63.81   status=new    submitted 14:04:57   updated 14:04:57
sell stop  55.80   status=held   submitted 13:59:22   updated 13:59:22
```

The take-profit was created at the instant of the fill and went live. **The
stop was never touched** — its `updated_at` still equalled its `submitted_at`
from before the parent filled. `positions_without_stops()` returned `[]`
anyway, because `held` is in `ACTIVE_STATUSES`.

The position was flattened at 58.10, realising **−$0.37 = −0.139R**.

### What the documentation actually says

Alpaca's own page on bracket orders:

> "The second and third orders won't be active until the first order is
> completely filled."
> — https://docs.alpaca.markets/us/docs/orders-at-alpaca

So after a *complete* fill, both legs are supposed to be active. Ours was not.

And a second thing, which matters more: **`held` is not in Alpaca's documented
order-status list at all.** The documented values are `new`,
`partially_filled`, `filled`, `done_for_day`, `canceled`, `expired`,
`replaced`, `pending_cancel`, `pending_replace`, `accepted`, `pending_new`,
`accepted_for_bidding`, `stopped`, `rejected`, `suspended`, `calculated`. The
API returns a state its own reference does not define, and this project built a
protective control on top of it.

Community reports describe the same symptom, including exit legs stuck `held`
after a parent fills and at least one report of a stop not converting when
price crossed it. **I could not read those threads** —
`forum.alpaca.markets` is blocked by this environment's egress policy, only
`docs.alpaca.markets` was opened — so they are listed as leads, not evidence:

- https://forum.alpaca.markets/t/half-of-bracket-order-held/2727
- https://forum.alpaca.markets/t/bracket-order-exit-trades-not-executing/3697
- https://forum.alpaca.markets/t/issues-with-bracket-orders-being-held/5023
- https://forum.alpaca.markets/t/some-bracket-orders-don-t-have-stop-loss/5797

### What was changed, and what deliberately was not

**Not** changed: nobody established that a `held` stop fails to fire. Asserting
it does would have been as unfounded as the assumption it replaced.

What IS established is that this is not the documented behaviour, on a status
the vendor does not document, so it **cannot be relied upon**. That is enough
to act on without resolving the mechanism:

- `positions_with_unconfirmed_stops()` returns `{symbol: status}` for a
  position whose stop is not in a confirmed-working state. It names the
  ambiguity instead of resolving it by guess.
- `trading_day preclose` now **refuses** on an unconfirmed stop, exactly as it
  refuses on a missing one. Intraday it is a flag; overnight it is a refusal,
  because a gap does not wait for us to find out.
- `positions_without_stops()` is unchanged and keeps accepting `held`. The two
  answer different questions — "was a stop ever placed" and "did it go live" —
  and a bracket leg legitimately sits `held` before its parent fills, so
  folding them together would report every pending bracket as naked.

### The counterfactual, recorded because a small number is still a number

DT never traded below **57.39** on the consolidated tape (IEX said 57.52 — M-30
in miniature, a subset overstating a low). The stop at 55.80 was never within
$1.59. Holding would have been about −0.075R unrealised against the −0.139R
realised, so **flattening cost roughly 0.064R and bought certainty about
protection.** The right trade, and the honest footnote is that today produced
no evidence either way about whether that stop would have fired — price never
went near it.

**Verified:** 231 tests (16 new). Sim unchanged, 0.0% ruin. Live `preclose`
against the flat book exits 0 and now prints "every position has a live,
CONFIRMED stop".

**Status:** active. The mechanism question stays open and is worth resolving if
`forum.alpaca.markets` is ever reachable, or by watching the next filled
bracket's legs directly.

## 2026-09-23 (pre-close) — the first fill, and the control that took it away

Phase 2's first fill ever: DT, 1 share @ 58.47 at 14:04:57Z, **zero slippage**
against the proposed 58.47. It was flattened 24 minutes later at 58.10 because
the bracket's stop leg reported `status=held` and could not be confirmed live.

### What was verified, under real conditions rather than asserted

**B-15 holds.** `trading_day preclose` run a second time left `fills.jsonl`
byte-identical (md5 `697b2842456595384a656b043ee2b727` before and after), with
exactly one buy and one sell at `dry_run: false` and unique `activity_id`s.
Dedupe works, and cash drift stayed **$+0.0000** across five reconciliations —
the $58.47 drift did not reappear. `tools.review` reads 1 closed trade at
-0.139R. M-16 (`preclose` live) ran clean, exit 0, cancelled nothing on a flat
book.

**The stop control was not verified.** It returned `{}` — on a flat book,
having been asked nothing. Recorded as no evidence rather than as a pass; a
green result from a control with no input is the vacuous-pass family this repo
has now logged four times.

### The finding: `held` is probably what a live OCO child looks like

Alpaca's own documentation, https://docs.alpaca.markets/us/docs/orders-at-alpaca
(HTTP 200 today — **the host is reachable**, though `alpaca.markets/docs/...`
is 403 at this environment's proxy):

> "The first order is used to enter a new long or short position, and **once
> it is completely filled, two conditional exit orders are activated.**"

> "when you retrieve the list of orders with the nested parameter true, **the
> take-profit order shows up as the parent order while the stop-loss order
> appears as a child order.**"

Which is exactly the shape observed: at the parent's fill the take-profit was
resubmitted (`submitted_at` 14:04:57) and went `new`; the stop leg kept its
original `submitted_at` of 13:59:22 and reported `held`. A filled bracket
becomes an OCO, the take-profit is its parent, the stop-loss is its child —
and the child reports `held`.

**Left open, not concluded.** No reachable Alpaca page defines the `held`
string (`orders-at-alpaca`, `working-with-orders`, and the `alpaca-py`
`OrderStatus` enum, which lists `HELD = "held"` with no semantics). Both legs
are now `canceled`, so their live status can no longer be read, and the stop
was never within $1.59 of triggering. The next bracket fill settles it for
nothing: query the stop leg by its own id at the moment the parent fills.

### Why a safe-direction bug is still expensive

The flatten cost more than the pre-close estimate. DT closed at **59.09**:

```
realised (flattened at 58.10)    -0.139R
counterfactual (held to 59.09)   +0.232R
cost of the flatten               0.371R
```

Nearly three times the loss taken, and it turned a winner into a loser. If the
stop really is live, this control will do that to **every** bracket position
this account opens — a systematic bleed wearing a guardrail's error message.

**The general lesson, and it is the opposite of the last four entries.** Those
were controls that failed open — inert, passing vacuously, letting risk
through. This one fails *closed*, and closed failures are harder to see
precisely because they look like discipline: the account loses money and the
log says a protection worked. **A control that cannot distinguish "unprotected"
from "protected, represented differently" is not conservative. It is wrong, in
a direction that flatters it.**

Corollary for the expectancy number now on the books: -0.139R over one trade
exited by our own plumbing measures the plumbing. It is not evidence about
20-day breakouts, and it must not be cited as any.

### Not changed

Nothing was promoted or altered. `model_check rule-promotion` exited 1 for want
of an authorization; none was written. Loosening a protection on one
observation, unattended, is the change this project least wants made. Filed as
T-17 in `state/reviews/2026-09-23-queue-t.md` with the test that would
settle it.

---

## 2026-09-24 — correction: `held` was right all along

recalcitrantmaus opened `forum.alpaca.markets`. The answer was there, from Alpaca's own
staff, and it reverses yesterday's conclusion.

Dan Whitnable, Alpaca, in
https://forum.alpaca.markets/t/half-of-bracket-order-held/2727 :

> "Being 'held' simply means it hasn't been sent to the exchange yet."
>
> "Until the market price reaches that value, it is 'held'... In the
> background, the price is being monitored. If/when the price reaches the
> stop price then the stop-loss order will 'un-held'."
>
> "...the take-profit order is canceled and the stop loss order is now
> submitted and the state is changed from 'held' to 'new'."
>
> "It is a bit disconcerting that 'held' orders show up under the 'closed'
> section, but not to worry, they are truly being held (and not closed)."

**So the asymmetry was correct behaviour.** A limit sell at 63.81 can rest on
an exchange book, so it shows `new`. A stop at 55.80 cannot — a stop is not an
exchange order until it triggers — so the broker monitors it and routes it on
the trigger. Take-profit `new` alongside stop `held` is exactly what a working
bracket looks like after its parent fills.

Everything built on the other reading is removed: the `preclose` refusal,
`positions_with_unconfirmed_stops()`, `CONFIRMED_STOP_STATUSES`, and the tests
that encoded it. `held` stays in `ACTIVE_STATUSES` with the citation beside it
and a test asserting it is there, because removing it would report every
correctly-bracketed position as naked and session-close treats that as a
flatten-or-fix event.

### What this cost, and the part worth keeping

DT was flattened at 58.10 against a 58.47 entry — **−$0.37, −0.139R, paid for
a misreading.** The stop was working the whole time.

The reasoning that led there was not unreasonable: Alpaca's docs say exit legs
"won't be active until the first order is completely filled", `held` is absent
from its documented status list, and the leg's `updated_at` never moved. Three
true observations, and the inference from them was still wrong.

**The lesson is about which kind of evidence was missing.** I had the vendor's
reference documentation and reasoned from its silence. Silence in a reference
is not evidence of anything — `held` being undocumented meant the docs were
incomplete, not that the status was broken. The thing that settled it was an
operator saying what the system does, and it existed the whole time behind a
domain the environment blocked. When a control is about to act on an inference
from absence, that is the moment to say so and go looking, rather than to
harden the inference into code.

A narrower version of the same point: yesterday's entry recorded the forum
threads as "leads, not evidence" because they could not be read. That was the
right instinct and the wrong response — the honest move was to treat the whole
question as unresolved and NOT ship a refusal on it, rather than to ship the
refusal and footnote the uncertainty.

### Still open, and genuinely unresolved

The second thread — https://forum.alpaca.markets/t/issues-with-bracket-orders-being-held/5023
— has users reporting BOTH legs stuck `held` after a complete entry fill, where
the limit should read `new`. Alpaca staff asked for order numbers and no
resolution was recorded, across reports from March to September 2021. That is a
different shape from what we saw and remains unexplained. Not worth a control
until it is observed here.

**Verified:** 229 tests. Live `preclose` exits 0 against the flat book.

**Status:** active. Supersedes the 2026-09-23 entry above it.

## 2026-09-24 — testing the tools that decide what we believe (B-29, B-30)

The unit-test audit had stopped at the modules that move money and deferred
the research and reporting tools on the reasoning that "a bug there gives a
wrong conclusion, not a lost dollar". recalcitrantmaus pushed back: a wrong conclusion
misaligns the strategy and *then* costs dollars, at a lag and without a
traceable cause. That is right, and it is the worse failure of the two,
because a lost dollar announces itself.

Two live defects came out of writing those tests. Neither was found by a
session failing.

### B-29 — the routing gate cleared any task name it did not recognise

`model_check <task>` returned exit 0 for anything absent from `POLICY`,
printing "no model policy for 'x'; proceeding". The gate is invoked **by
name**, from Routine prompts and skill text, so `rule_promotion` instead of
`rule-promotion` cleared a blocking task silently — and a typo is
indistinguishable at the gate from a deliberate bypass. Shape B: the check
ran, reported, and could not fail.

`model_policy.check()` still returns True for an unknown task. That is correct
for a library call. The refusal belongs at the CLI, because that is where a
task name stops being a lookup and becomes an assertion.

### B-30 — preflight ran the test suite against the real ledger

`preflight_phase2` invoked `unittest discover -s tests` with no `-t .` — the
exact form that skips `tests/__init__.py`, so the sandbox never applies and the
suite writes to the real `state/` directory. That is how a phantom BUY reached
`state/fills.jsonl` earlier the same day.

The part worth keeping: **CLAUDE.md, the README and docs/05 were all corrected
that morning, and this call site was not.** The rule was true everywhere except
in the code that runs before every single session. Documenting a fix is not
shipping it, and a grep for the wrong form would have found this in seconds.

### The guard that could not see the code it guarded

The fix came with a repo-wide invariant test: nothing tracked may invoke
`discover -s tests` without `-t .`. Mutation-testing it scored **zero** —
removing `-t .` from preflight failed nothing. The test read `git grep` output
line by line, and preflight's call is wrapped across two lines with the word
`discover` on the first. So the guard against vacuous checks was itself a
vacuous check. It now scans whitespace-normalised file contents.

The general lesson, which has now cost three separate guards: **a check written
against a remembered bug must be run against the bug.** Not against a
description of it.

### A mutation harness that lied

Two of the mutations were pure re-orderings of adjacent `if` blocks, so the
mutated file had the **same byte size** as the original, and `shutil.copy`
restored it inside the same mtime second. CPython's bytecode cache keys on
mtime and size, so the "restored" tree kept running the mutated `.pyc`. One
mutation was scored caught on evidence from a stale cache, and `classify` went
on returning `inverse` for a 2x product until the full suite caught it.

Clear `__pycache__` around any file-swapping harness. A verification tool that
can be wrong in the flattering direction is worth less than no tool, because it
is trusted.

### What was added

`tests/test_research.py` (51) and `tests/test_reporting.py` (44). The research
file concentrates on two things: arithmetic that is easy to get *flatteringly*
wrong — gapped stop fills, which side of a tie wins, median vs mean liquidity —
and look-ahead, which is the failure a backtest cannot show you because it
makes the results better. Several tests rewrite the bars *after* a signal and
assert that nothing computed at signal time moved.

Twenty-one mutations, every one caught: 9 on the research suite (1–7 tests
each) and 12 on the reporting suite (1–2 each).

**Verified:** 426 tests, green. `sim.run_suite --seeds 300`: 0.0% ruin.

**Status:** active.

## 2026-09-25 — T-10 activated: the floor is now re-read at the write

Parked on 2026-09-22 at recalcitrantmaus's request, so it would be wired in deliberately
rather than dropped into a live trading day. Activated at her instruction with
the `rule-promotion` gate cleared on `claude-opus-5` at xhigh, model read from
the session record rather than the environment default.

### The finding, restated

CLAUDE.md said environment variables are snapshotted at session start.
**`CLAUDE_EFFORT` is the exception**: measured `high` at 13:39Z and `medium` at
20:07Z inside one session on 2026-09-22. It tracks the turn.

`check()` runs once, at task start, and nothing re-read it. So a blocking task
could clear at xhigh and perform its durable write several turns later at
medium with no signal at all — `session-close` did exactly that, two notches
below its floor, and only the journal caught it. **A point-in-time check on a
per-turn value certifies the turn it was taken in, not the write.**

CLAUDE.md's blanket claim has been corrected in place. A doc that is wrong
about the one variable that moves is worse than a doc that says nothing.

### One thing I measured before wiring anything in

`recheck()` fails closed when the harness effort value is unavailable — a
*declared* value cannot move, so it cannot detect the thing this exists to
detect. That means activating it into an environment without `CLAUDE_EFFORT`
would refuse **every** blocking write, which is an outage, not a control. So I
checked first: `CLAUDE_EFFORT=xhigh`, source `harness`. Activation was safe.

Measuring the blast radius before arming a refusal is the step the `held`
episode skipped two days ago, and it cost $0.37 then.

### Two call sites, and they are not equally strong

**`RiskOfficer.unlock()` — a real interlock.** The only durable write a
blocking task performs as a function call, and the most consequential write in
the system: it re-arms an account the breakers took offline. It now raises
`EffortFloorRefusal`, a type of its own so it cannot be swallowed by an
`except ValueError`. **A LOCKED account cannot be cleared below `max` effort**,
and the lock stays on until a session that holds the floor runs the unlock.

That is a new operational constraint on the recovery path and it is
deliberate — the policy already said `unlock-authorization` is Opus @ max,
blocking; this makes the procedural rule enforceable at the write. The escape
is real and named in the refusal message: run the unlock from a max-effort
session. Nothing is stranded permanently.

**`model_check <task> --at-write` — a procedure, not an interlock.** The other
durable writes (the `engine/config.py` edit, the SKILL.md write, the lessons
entry) are made by the agent with file tools, so there is no line of Python to
hook. Exit 1 means abandon that write. This is weaker by construction, and it
is recorded as the weaker thing it is rather than described as a gate. An
honest account of what a control can and cannot do is part of the control.

It deliberately does **not** re-verify the model. `--model` is a human's act,
already recorded and single-use, and the model does not silently drift under a
session the way effort does. A second place to assert a model is a second place
to fabricate one and detect nothing.

### The guard test was inverted, not deleted

The parked version asserted `recheck()` was called **nowhere** and failed the
moment anyone wired it in. Deleting it at activation would have been the
obvious move and the wrong one: it now asserts **both call sites are present**,
so quietly dropping one fails the suite instead of silently restoring the
finding with the code still there and still tested. That is the most flattering
way for a control to die, and it is now the loudest.

### Two of my own verification steps were wrong again

Seven mutations, all now caught — but not at first.

1. **A test that named a property it could not distinguish.** The blank-note
   ordering test ran at `max` effort, where both checks pass, so either
   ordering produced `ValueError`. It asserted the ordering and measured
   nothing. Fixed by asserting it at an effort *below* the floor, where the two
   checks disagree.
2. **A mutation written against the wrong line.** The mutation meant to break
   that ordering moved only the `recheck()` *call* above the blank-note check
   and left the `raise` where it was — a no-op. It scored zero, and I briefly
   read that as an escaped bug in the test rather than a flaw in the mutation.
   The real bug shape required moving the whole block.

Both are the same error in different clothing: **measuring something adjacent
to the thing you care about.** That is now four instances in three days — the
attendance gate, the invariant test that read grep lines, the ordering test,
and the mutation. The pattern is not carelessness about tests; it is that a
check is easy to write against a *description* of a bug and hard to write
against the bug. Run it against the bug.

**Verified:** 426 tests, green. `sim.run_suite --seeds 300`: 0.0% ruin.
`engine/` changed, so both were mandatory.

**Status:** active.
