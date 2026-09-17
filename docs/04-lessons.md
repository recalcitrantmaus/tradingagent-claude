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
