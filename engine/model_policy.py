"""Which Claude model is allowed to perform which task.

An autonomous agent cannot choose its own model mid-run — the model is set by
whatever launched the session (a Routine, a cron trigger, a CLI flag). So this
module does the next best thing: it states the policy as data, and lets any
task refuse to run on a model that is not cleared for it.

The asymmetry is deliberate. A bad execution turn costs one trade. A bad rule
promoted into a SKILL.md costs every trade until someone notices. Capability
is spent where mistakes are durable.
"""

from dataclasses import dataclass
from enum import Enum
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
    TaskPolicy("session-close", Tier.SONNET, "xhigh",
               "Reconciliation and reporting against a fixed checklist.",
               blocking=False),
    TaskPolicy("trade-journal", Tier.SONNET, "xhigh",
               "Recording a reflection is routine; PROMOTING one to a rule is "
               "not — that is rule-promotion, below.", blocking=False),

    # --- judgment: open-ended synthesis, errors propagate into every trade
    TaskPolicy("premarket-brief", Tier.SONNET, "xhigh",
               "Open-ended synthesis over noisy, conflicting sources. Sonnet "
               "at xhigh is the validated floor; Opus is preferred when the "
               "regime is unclear or posture would be RISK_OFF.",
               blocking=False),
    TaskPolicy("trade-plan", Tier.SONNET, "xhigh",
               "Thesis construction sets the day's expectancy. Same floor as "
               "the brief it consumes.", blocking=False),

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


def current_effort() -> Optional[str]:
    return os.environ.get("TRADING_AGENT_EFFORT")


def check(task: str, model: Optional[str] = None,
          effort: Optional[str] = None) -> tuple[bool, List[str]]:
    """Return (ok, messages). ok=False means do not perform this task."""
    p = POLICY.get(task)
    if p is None:
        return True, [f"no model policy for '{task}'; proceeding"]

    if model:
        source = "explicit"
    else:
        model, source = model_and_source()
    effort = effort or current_effort()
    msgs: List[str] = []

    # A blocking task decides what the agent BECOMES. Clearing one on an
    # environment default means clearing it on a value that cannot vary with
    # the thing being checked — and the failure is silent and one config edit
    # away: set TRADING_AGENT_MODEL to an opus id and EVERY session in the
    # environment would clear, whatever it actually runs. So an unverified
    # model is not good enough for a blocking task, even when it looks good
    # enough. Pass --model after reading the session record.
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
        return True, msgs
    if p.blocking:
        msgs.append("BLOCKING: do not perform this task. Re-run it in a "
                    "session configured with the required model.")
        return False, msgs
    msgs.append("non-blocking: proceed, and record the downgrade in the journal.")
    return True, msgs
