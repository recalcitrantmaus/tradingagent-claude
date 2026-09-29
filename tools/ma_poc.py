#!/usr/bin/env python3
"""Managed Agents proof of concept: model and effort stored WITH the agent.

    python3 -m tools.ma_poc                 # dry run: print the config, no network
    python3 -m tools.ma_poc --create        # create the agent, read it back, verify
    python3 -m tools.ma_poc --verify        # re-read the stored agent, verify
    python3 -m tools.ma_poc --session       # also run one capped, read-only session

Design: state/reviews/2026-09-29-design-managed-agent.md.

The question it answers: can the agent's model and effort be a stored,
versioned property of the agent that any process can reference, instead of a
picker in a browser? The agent object takes `model` as
{"id": ..., "effort": ...}, and the create/retrieve responses echo it back.
`verify()` is the check a future `model_check` would run: it reads the stored
agent, not the session's environment, so a session cannot certify itself.

Needs ANTHROPIC_API_KEY in the environment and `pip install anthropic`. Places
no orders, touches no broker, and runs no trading tool. The session is capped
with a platform-enforced budget.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL = "claude-opus-5-5"
EFFORT = "xhigh"
STORE = Path("state/agents/poc.json")
BUDGET_CENTS = "100"   # $1.00 hard cap on the probe session


def agent_config(model: str = MODEL, effort: str = EFFORT) -> dict:
    return {
        "name": "tradingagent-effort-poc",
        "description": "POC: model and effort pinned on the agent object. "
                       "Read-only; no trading tools.",
        "model": {"id": model, "effort": effort},
        "system": "You are a read-only probe. Never place orders. "
                  "Answer in one line.",
        "metadata": {"repo": "recalcitrantmaus/tradingagent-claude",
                     "purpose": "effort-pin-poc"},
    }


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def pinned(agent) -> tuple:
    """(model id, effort) as the agent object stores them. Effort may come
    back as a string or in object form, e.g. {"type": "xhigh"}."""
    m = _get(agent, "model")
    if isinstance(m, str):
        return m, None
    eff = _get(m, "effort")
    if eff is not None and not isinstance(eff, str):
        eff = _get(eff, "type")
    return _get(m, "id"), eff


def verify(agent, model: str = MODEL, effort: str = EFFORT) -> list:
    """Problems with the stored pin; empty means the pin is what we set."""
    got_model, got_effort = pinned(agent)
    out = []
    if got_model != model:
        out.append(f"model is {got_model!r}, expected {model!r}")
    if got_effort != effort:
        out.append(f"effort is {got_effort!r}, expected {effort!r}"
                   + (" (unset: the model default applies)"
                      if got_effort is None else ""))
    return out


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in this environment. It is "
                 "added in the environment's settings and a NEW session "
                 "picks it up.")
    try:
        import anthropic
    except ImportError:
        sys.exit("the anthropic SDK is not installed: pip install anthropic")
    return anthropic.Anthropic()


def _report(agent) -> int:
    problems = verify(agent)
    m, e = pinned(agent)
    print(f"agent {_get(agent, 'id')} v{_get(agent, 'version')}: "
          f"model={m} effort={e}")
    for p in problems:
        print(f"  PIN MISMATCH: {p}")
    print("PIN OK" if not problems else "PIN FAILED")
    return 0 if not problems else 1


def run_session(client, agent) -> None:
    env = client.beta.environments.create(
        name="tradingagent-effort-poc",
        config={"type": "cloud", "networking": {"type": "limited"}},
    )
    session = client.beta.sessions.create(
        agent={"type": "agent", "id": agent.id, "version": agent.version},
        environment_id=env.id,
        title="effort pin probe",
        budget={"type": "limit",
                "max_list_cost": {"amount": BUDGET_CENTS, "currency": "USD"}},
    )
    print(f"session {session.id}")
    with client.beta.sessions.events.stream(session_id=session.id) as stream:
        client.beta.sessions.events.send(
            session_id=session.id,
            events=[{"type": "user.message", "content": [
                {"type": "text", "text": "Reply with the single word: ready"}]}],
        )
        deadline = time.monotonic() + 180
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(f"  agent: {block.text.strip()}")
            elif event.type in ("session.status_idle",
                                "session.status_terminated"):
                break
            if time.monotonic() > deadline:
                print("  gave up waiting after 180s")
                break
    s = client.beta.sessions.retrieve(session_id=session.id)
    print(f"  status={s.status} usage={s.usage}")
    client.beta.sessions.archive(session_id=session.id)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--create", action="store_true")
    g.add_argument("--verify", action="store_true")
    ap.add_argument("--session", action="store_true")
    a = ap.parse_args(argv)

    if not (a.create or a.verify):
        print(json.dumps(agent_config(), indent=2))
        print("\ndry run: nothing sent. --create to create and verify.")
        return 0

    client = _client()
    if a.create:
        agent = client.beta.agents.create(**agent_config())
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps({"agent_id": agent.id,
                                     "version": agent.version}, indent=2))
        print(f"stored {STORE}")
    # Read back by id, never trust the create response alone: the retrieve is
    # what a later process holding only the id would see.
    agent_id = json.loads(STORE.read_text())["agent_id"]
    agent = client.beta.agents.retrieve(agent_id=agent_id)
    rc = _report(agent)
    if a.session and rc == 0:
        run_session(client, agent)
    return rc


if __name__ == "__main__":
    sys.exit(main())
