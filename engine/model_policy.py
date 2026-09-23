"""Which Claude model is allowed to perform which task.

An autonomous agent cannot choose its own model mid-run — the model is set by
whatever launched the session (a Routine, a cron trigger, a CLI flag). So this
module does the next best thing: it states the policy as data, and lets any
task refuse to run on a model that is not cleared for it.

The asymmetry is deliberate. A bad execution turn costs one trade. A bad rule
promoted into a SKILL.md costs every trade until someone notices. Capability
is spent where mistakes are durable.
"""

import datetime as dt
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
import os


class Tier(str, Enum):
    """Ordered by capability, not by price."""
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


ORDER = [Tier.HAIKU, Tier.SONNET, Tier.OPUS]

# Model id -> tier. Ids are matched by prefix so dated variants resolve.
MODEL_TIERS: Dict[str, Tier] = {
    "claude-haiku": Tier.HAIKU,
    "claude-sonnet": Tier.SONNET,
    "claude-opus": Tier.OPUS,
    "claude-fable": Tier.OPUS,
}

EFFORTS = ["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class TaskPolicy:
    task: str
    min_tier: Tier
    min_effort: str
    rationale: str
    blocking: bool          # False = warn and continue; True = refuse to run


POLICY: Dict[str, TaskPolicy] = {p.task: p for p in [
    # --- routine loop: Sonnet is sufficient, the risk engine is the safety net
    TaskPolicy("news-intel", Tier.SONNET, "high",
               "Triage against an explicit checklist; errors are recoverable "
               "and visible in the source log.", blocking=False),
    TaskPolicy("execution", Tier.SONNET, "xhigh",
               "Rule-following with structured output. Every order still "
               "passes the deterministic risk gate, so a weaker model cannot "
               "size up, skip a stop, or trade through a halt.", blocking=False),
    # Raised to Opus 2026-09-22. The close is where findings get promoted:
    # Monday's close found M-16 unprompted and declined a --model override it
    # was entitled to reach for. That is judgement, not reconciliation.
    TaskPolicy("session-close", Tier.OPUS, "xhigh",
               "Reconciliation against a fixed checklist, but also where the "
               "day's findings are written down and escalated — the errors "
               "here are the ones nobody catches later.", blocking=False),
    # Raised to Opus 2026-09-22, on T-1/T-2. Pre-close decides the overnight
    # carry, and a gap does not respect stops. With up to 4 positions whose
    # measured pairwise correlation runs 0.45-0.83, pricing the gap risk of a
    # correlated book is the highest-stakes judgement of the day. Revisit
    # once the portfolio open-risk cap has live evidence behind it.
    TaskPolicy("pre-close", Tier.OPUS, "xhigh",
               "Prices overnight gap risk across a correlated book and "
               "decides what is carried. A stop is a fill instruction, not a "
               "price guarantee, and it does not survive a gap.",
               blocking=False),
    TaskPolicy("trade-journal", Tier.SONNET, "xhigh",
               "Recording a reflection is routine; PROMOTING one to a rule is "
               "not — that is rule-promotion, below.", blocking=False),

    # --- judgment: open-ended synthesis, errors propagate into every trade
    # --- the OPEN session: raised to Opus on 2026-09-22 ----------------
    # The deterministic risk engine protects against bad DECISIONS. It cannot
    # protect against bad DATA — a proposal built on a wrong number passes
    # every gate, because the size, the stop and the R are all computed
    # correctly from it. RKLB on 2026-09-22 is the proof: it would have
    # cleared the whole engine on a 20-day high that was 0.91% too low, and
    # only a model cross-checking its own feed caught it. The same defect had
    # ATR wrong in 59 of 59 names (bug B-21).
    #
    # The open is also the only session that FORMS beliefs about the world;
    # the others execute against beliefs already formed. So the capability
    # asymmetry follows the task, not the phase, and it does not expire when
    # strategy testing ends.
    #
    # This floor should be EARNED DOWN. Every data artifact found here should
    # become a deterministic check — cross_check() already exists for prices
    # and belongs on levels and ATR next. When it is, revisit this.
    TaskPolicy("premarket-brief", Tier.OPUS, "xhigh",
               "Open-ended synthesis over noisy, conflicting sources, and the "
               "only place a bad INPUT can be caught — the risk engine "
               "validates decisions, not data.", blocking=False),
    TaskPolicy("trade-plan", Tier.OPUS, "xhigh",
               "Thesis construction sets the day's expectancy, on the same "
               "inputs the brief just had to verify.", blocking=False),

    # --- durable decisions: a mistake here outlives the trade that caused it
    TaskPolicy("weekly-review", Tier.OPUS, "xhigh",
               "Decides what the agent BECOMES. A bad rule promoted here "
               "silently costs every future trade.", blocking=True),
    TaskPolicy("rule-promotion", Tier.OPUS, "xhigh",
               "Writing to config.py or a SKILL.md is the most durable action "
               "the agent can take.", blocking=True),
    TaskPolicy("post-halt-review", Tier.OPUS, "xhigh",
               "Diagnosing why a circuit breaker fired, after real money was "
               "lost. Worth the most capable model available.", blocking=True),
    TaskPolicy("unlock-authorization", Tier.OPUS, "max",
               "Clearing a LOCKED account. Requires a human anyway; the model "
               "must be able to argue against resuming.", blocking=True),
]}


def tier_of(model_id: Optional[str]) -> Optional[Tier]:
    if not model_id:
        return None
    m = model_id.lower()
    for prefix, tier in MODEL_TIERS.items():
        if m.startswith(prefix):
            return tier
    return None


def model_and_source() -> tuple[Optional[str], str]:
    """The model this session appears to run, AND where that claim came from.

    This matters more than the value. `TRADING_AGENT_MODEL` is set at the
    ENVIRONMENT level, so every session launched in an environment reports the
    same model no matter what it is actually running. Measured 2026-09-18: a
    session verified as claude-opus-5 from its own session record read
    `claude-sonnet-5` here, because that is what the environment says.

    Claude Code exports no model variable, so there is no better source
    available to a Python process. The fix is therefore not a better guess, it
    is honesty about provenance: an environment default is a DEFAULT, not a
    measurement, and a caller that has verified its own model must say so.

    Returns (model, source) where source is "explicit" when the caller passed
    it, "environment" when it came from a variable, or "unknown".
    """
    m = os.environ.get("TRADING_AGENT_MODEL") or os.environ.get("ANTHROPIC_MODEL")
    return (m, "environment") if m else (None, "unknown")


def current_model() -> Optional[str]:
    """Back-compatible accessor. Prefer model_and_source() — the source is the
    part that decides whether a blocking task may trust this value."""
    return model_and_source()[0]


def effort_and_source() -> tuple[Optional[str], str]:
    """The effort level, and whether it was MEASURED or merely declared.

    Unlike the model — where Claude Code exports nothing and provenance is the
    best available fix — the harness DOES export `CLAUDE_EFFORT`. The policy
    read `TRADING_AGENT_EFFORT` instead, which is an operator declaration set
    once per environment. On 2026-09-21 those disagreed in the close session:
    declared `xhigh`, actually running `high`, so the gate cleared an effort
    the session was not running at. Failing in the permissive direction, on a
    value that was sitting in the environment the whole time.

    So: the harness value is the truth, the declaration is a fallback, and the
    caller is told which it got.
    """
    m = os.environ.get("CLAUDE_EFFORT")
    if m:
        return m, "harness"
    d = os.environ.get("TRADING_AGENT_EFFORT")
    return (d, "declared") if d else (None, "unknown")


def current_effort() -> Optional[str]:
    """Back-compatible accessor. Prefer effort_and_source()."""
    return effort_and_source()[0]


# --- M-22, second attempt. The first one did not work. -----------------
#
# `is_attended()` used to read CLAUDE_CODE_SESSION_ATTENDED and return True on
# "1". That variable is set environment-wide, so it read "1" in every session
# including unattended scheduled firings, and the gate never once bound. On
# 2026-09-22 an unattended relay session cleared `rule-promotion` with it.
#
# The replacement proposed at the time — require the variable to equal
# CLAUDE_CODE_SESSION_ID, so an environment-wide value satisfies at most one
# session — is ALSO wrong, and the session that proposed it is the
# counterexample. A scheduled relay fired into it at 14:20Z (unattended) and a
# human typed into the same session at 15:45Z (attended). Same session id,
# same environment, same variables. **Attendance is a property of the TURN,
# not of the session or the environment**, and environment variables are
# snapshotted at session start, so no variable of any scope can track it.
#
# So this stops pretending to detect a human and starts recording a claim.
# Be clear about what that buys, because overstating it is how the first
# version happened: this is ATTRIBUTABLE, not ENFORCEABLE. Nothing in-process
# can establish that a human is present — any check the process can read, the
# process can satisfy. What it can do is make the assertion explicit, specific
# and permanent, so a false one is a lie in an append-only log with a session
# id and a timestamp on it, rather than a silent boolean read.
#
# Two things here ARE enforced, and they cover the realistic failure:
#   1. A trivial authorization ("ok", "yes", "approved") is refused. The
#      override has to say something.
#   2. A verbatim-reused authorization is refused. That is the actual threat —
#      not an adversarial agent, but a canned string pasted into a Routine
#      prompt that then clears the gate every single day unattended. A nonce
#      that must be new each time cannot be baked into a schedule.

AUTH_LOG = Path(__file__).resolve().parents[1] / "state" / "authorizations.jsonl"

# Rejected outright: an authorization that carries no information is the same
# self-certification the gate exists to stop, wearing a string.
TRIVIAL_AUTHORIZATIONS = {
    "y", "n", "yes", "no", "ok", "okay", "1", "true", "go", "go ahead",
    "sure", "approved", "authorised", "authorized", "proceed", "do it",
    "confirmed", "confirm", "please", "fine", "accept", "accepted",
    "human", "attended", "authorization", "auth",
}
MIN_AUTHORIZATION_CHARS = 12


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split())


def _prior_authorizations(log_path=None) -> List[str]:
    path = Path(log_path) if log_path else AUTH_LOG
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line).get("authorization", ""))
        except json.JSONDecodeError:
            continue          # a corrupt row must not silently clear the gate
    return out


def authorization_ok(text: Optional[str], log_path=None) -> tuple[bool, str]:
    """Is this a usable human authorization? Returns (ok, reason)."""
    if text is None or not text.strip():
        return False, "no authorization was supplied"
    norm = _normalise(text)
    if norm in TRIVIAL_AUTHORIZATIONS or len(norm) < MIN_AUTHORIZATION_CHARS:
        return False, (f"the authorization {text.strip()!r} carries no "
                       "information. State what is being authorised and why, "
                       "in the authorising human's own words.")
    if norm in {_normalise(p) for p in _prior_authorizations(log_path)}:
        return False, ("this authorization has been used before, verbatim. A "
                       "reused string is a schedule, not a decision — it "
                       "would clear this gate on every firing. Write a new "
                       "one describing THIS change.")
    return True, "authorization accepted and recorded"


def record_authorization(task: str, model: Optional[str], text: str,
                         log_path=None) -> None:
    """Append-only. This log is the whole point: it is what makes a false
    claim attributable after the fact."""
    path = Path(log_path) if log_path else AUTH_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "task": task,
        "model": model,
        "session": (os.environ.get("CLAUDE_CODE_SESSION_ID")
                    or os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID") or ""),
        "authorization": text.strip(),
    }
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def check(task: str, model: Optional[str] = None,
          effort: Optional[str] = None, authorization: Optional[str] = None,
          auth_log=None) -> tuple[bool, List[str]]:
    """Return (ok, messages). ok=False means do not perform this task."""
    p = POLICY.get(task)
    if p is None:
        return True, [f"no model policy for '{task}'; proceeding"]

    if model:
        source = "explicit"
    else:
        model, source = model_and_source()
    # NOTE: effort is resolved further down, not here. Filling it in at this
    # point made every value look like it had been passed explicitly, which
    # defeated the provenance check that is the whole point of M-17.
    msgs: List[str] = []

    # A blocking task decides what the agent BECOMES. Clearing one on an
    # environment default means clearing it on a value that cannot vary with
    # the thing being checked — and the failure is silent and one config edit
    # away: set TRADING_AGENT_MODEL to an opus id and EVERY session in the
    # environment would clear, whatever it actually runs. So an unverified
    # model is not good enough for a blocking task, even when it looks good
    # enough. Pass --model after reading the session record.
    # An explicit --model is a human's override, asserted on a session record
    # a human has read. The first attempt tried to DETECT a human (see the
    # note above authorization_ok); it could not, because nothing in-process
    # can. So the override now has to be SAID, in terms that cannot be
    # pre-baked into a schedule, and it is recorded.
    if p.blocking and source == "explicit":
        auth_ok, why = authorization_ok(authorization, auth_log)
        if not auth_ok:
            return False, [
                f"'{task}' is blocking and --model was passed without a usable "
                f"authorization: {why}",
                'Pass --authorization "<what is being changed and why, in the '
                'authorising human\'s words>". It is appended to '
                "state/authorizations.jsonl with the session id and timestamp.",
                "This gate is ATTRIBUTABLE, not enforceable: a session could "
                "fabricate this string. It could not do so without leaving a "
                "dated, session-stamped claim in the repository. Refusing "
                "rather than self-certifying."]

    if p.blocking and source != "explicit":
        where = ("TRADING_AGENT_MODEL, an ENVIRONMENT-level default"
                 if source == "environment" else "nowhere")
        return False, [
            f"'{task}' is blocking and the running model is UNVERIFIED: the "
            f"value {model!r} came from {where}, which is the same for every "
            f"session in this environment and cannot be trusted to describe "
            f"this one.",
            "Read the real model from the session record (get_session with "
            "session_id omitted; session_context.model and "
            "external_metadata.last_served_model), then re-run with "
            f"--model <that model>. Refusing rather than guessing."]
    if source == "environment":
        msgs.append(f"model {model!r} read from TRADING_AGENT_MODEL (an "
                    "environment default, not a measurement of this session)")

    # --- effort, same treatment ---
    eff_src = "explicit" if effort else None
    if not effort:
        effort, eff_src = effort_and_source()
    declared = os.environ.get("TRADING_AGENT_EFFORT")
    if eff_src == "harness" and declared and declared != effort:
        msgs.append(f"EFFORT MISMATCH: harness reports {effort!r}, "
                    f"TRADING_AGENT_EFFORT declares {declared!r}. Using the "
                    "harness value; fix the declaration.")
    if p.blocking and eff_src == "declared":
        return False, [
            f"'{task}' is blocking and the effort level is UNVERIFIED: "
            f"{effort!r} came from TRADING_AGENT_EFFORT, a declaration, and "
            "the harness did not report CLAUDE_EFFORT.",
            "Refusing rather than trusting a declaration about this session."]

    tier = tier_of(model)
    if tier is None:
        msg = (f"cannot verify the running model (value {model!r} from "
               f"{source}); '{task}' requires at least "
               f"{p.min_tier.value} at {p.min_effort}")
        return (not p.blocking), [msg]

    ok = True
    if ORDER.index(tier) < ORDER.index(p.min_tier):
        ok = False
        msgs.append(f"'{task}' requires {p.min_tier.value}-tier or better; "
                    f"running {model} ({tier.value}). {p.rationale}")
    if effort and effort in EFFORTS and EFFORTS.index(effort) < EFFORTS.index(p.min_effort):
        ok = False
        msgs.append(f"'{task}' requires effort >= {p.min_effort}; running {effort}")

    if ok:
        msgs.append(f"'{task}' cleared on {model} at effort {effort or 'unknown'}")
        if p.blocking and source == "explicit" and authorization:
            record_authorization(task, model, authorization, auth_log)
            msgs.append("authorization recorded to state/authorizations.jsonl")
        return True, msgs
    if p.blocking:
        msgs.append("BLOCKING: do not perform this task. Re-run it in a "
                    "session configured with the required model.")
        return False, msgs
    msgs.append("non-blocking: proceed, and record the downgrade in the journal.")
    return True, msgs


# ======================================================================
# T-10 — PARKED, NOT WIRED IN. Activate at the end of a session, deliberately.
# ======================================================================
#
# Nothing calls `recheck()` yet. That is on purpose: recalcitrantmaus asked for the fix
# to be parked and incorporated at the end of a session rather than dropped
# into a live trading day, and a gate that starts refusing mid-session
# without anyone expecting it is its own incident.
#
# THE FINDING. CLAUDE.md says environment variables are snapshotted at session
# start. That is NOT true of `CLAUDE_EFFORT`. Measured within one session on
# 2026-09-22:
#
#     13:39Z  CLAUDE_EFFORT=high
#     20:07Z  CLAUDE_EFFORT=medium
#
# It tracks the TURN. For M-17 that is good news — the value chosen as the
# measurement really does measure. The problem is what it implies for the
# gate: `check()` runs ONCE, at the start of a task, and nothing re-reads it.
# A blocking task that clears at xhigh can perform its durable write at medium
# with no signal at all. On 2026-09-22 `session-close` ran two notches below
# its floor and only the journal recorded it.
#
# A point-in-time check on a per-turn value certifies the turn it was taken
# in, not the task. This is the third member of a family found in two days:
# attendance is a property of the turn (M-22/M-26), effort is a property of
# the turn, and both were being read as though they described a session.
#
# WHAT THIS DOES NOT DO. It does not re-verify the model. Passing `--model` is
# a human's act and the authorization is already recorded and single-use; the
# model does not silently change under a session the way effort does. Only the
# value that actually moves is re-read.
#
# TO ACTIVATE, at the end of a session, not during one:
#   1. Call `recheck(task, effort_floor_of(task))` immediately before each
#      DURABLE WRITE in a blocking task — the `engine/config.py` edit, the
#      SKILL.md write, the docs/04-lessons.md entry — not at task start.
#      That is where a downgrade would actually cost something.
#   2. On a False, abandon the write and say so. Do not finish "just this
#      one" — a rule promoted at medium is exactly the cost M-17 priced.
#   3. Delete this banner and add the call sites to the tests.


def recheck(task: str, started_at_effort: Optional[str] = None
            ) -> tuple[bool, List[str]]:
    """Re-read the effort floor at the moment of a durable write.

    Returns (ok, messages). ok=False means: do not perform this write.
    Non-blocking tasks always pass — execution must never stall on this.
    """
    p = POLICY.get(task)
    if p is None or not p.blocking:
        return True, []

    effort, src = effort_and_source()
    msgs: List[str] = []
    if src != "harness":
        # Without the harness value there is nothing to re-check against, and
        # a declaration cannot move, so it cannot detect the thing this exists
        # to detect. Fail closed on a blocking write.
        return False, [
            f"'{task}': cannot re-verify effort at the write — "
            f"CLAUDE_EFFORT is unavailable (source: {src}). "
            "Refusing the durable write rather than assuming it held."]

    if started_at_effort and effort != started_at_effort:
        msgs.append(f"EFFORT MOVED during '{task}': started {started_at_effort!r}, "
                    f"now {effort!r}. CLAUDE_EFFORT tracks the turn, not the "
                    f"session.")

    if effort in EFFORTS and EFFORTS.index(effort) < EFFORTS.index(p.min_effort):
        msgs.append(f"'{task}' requires effort >= {p.min_effort}; this turn is "
                    f"running {effort}. The gate cleared earlier at a higher "
                    f"effort — that clearance does not carry.")
        return False, msgs

    msgs.append(f"'{task}' still at {effort} (>= {p.min_effort}) at the write")
    return True, msgs
