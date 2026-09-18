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
