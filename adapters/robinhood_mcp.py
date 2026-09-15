"""Robinhood Agentic Trading — the MCP path.

Robinhood launched Agentic Trading on 2026-05-27. It is not a REST API to
write a client against: it is an MCP server the agent connects to directly,
at https://agent.robinhood.com/mcp/trading. Claude Code is a supported client.

  Overview  https://robinhood.com/us/en/agentic-trading/
  Support   https://robinhood.com/us/en/support/articles/agentic-trading-overview/
  Trading   https://robinhood.com/us/en/support/articles/trading-with-your-agent/
  Newsroom  https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/

What this means for this repo:

  * Orders are placed by the agent CALLING MCP TOOLS, not by Python in this
    package. So this module holds the preflight — the checks that must pass
    before the agent is allowed to reach for those tools — and the ticket
    formatting, rather than an HTTP client.
  * Robinhood's own controls (a dedicated agentic account with a pre-loaded
    balance, spending limits, instant agent disable, order previews) sit
    OUTSIDE this repo and are configured in the Robinhood app. They are a
    second, independent layer. Configure both; neither is a substitute.
  * Robinhood previews orders for confirmation by default, but will place
    them without confirmation if the agent has been told to act without
    asking. That setting is the difference between a supervised and an
    unsupervised agent, and it is the single most consequential switch in the
    whole system. It belongs to the account holder, not the agent.

VERIFY BEFORE PHASE 3: everything above is from Robinhood's published pages
and press coverage as of 2026-09-15, gathered by search because this sandbox
cannot reach robinhood.com. Confirm the current tool surface, the asset
classes enabled on your account, and the approval settings directly in the
Robinhood app before sending a single order.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import datetime as dt

from .base import Authorization, OrderTicket

MCP_URL = "https://agent.robinhood.com/mcp/trading"

# Example .mcp.json — see docs/07-deployment.md
MCP_CONFIG_EXAMPLE = {
    "mcpServers": {
        "robinhood-trading": {"type": "http", "url": MCP_URL}
    }
}


@dataclass
class PreflightResult:
    ok: bool
    checks: List[str]

    def report(self) -> str:
        head = "PREFLIGHT PASSED" if self.ok else "PREFLIGHT FAILED — do not trade"
        return head + "\n" + "\n".join(f"  {c}" for c in self.checks)


def preflight(*, risk_state: str, ledger_reconciled_on: Optional[str],
              positions_without_stops: List[str], equity: float,
              decision_approved: bool, ticket: Optional[OrderTicket],
              today: Optional[dt.date] = None,
              require_authorization: bool = True) -> PreflightResult:
    """Run before any Robinhood MCP order tool is called.

    Every check is something that has to be true regardless of which broker
    is on the other end. The MCP server is convenient; it is not a safety
    system, and Robinhood's own limits protect the account, not the strategy.
    """
    today = today or dt.date.today()
    checks: List[str] = []
    ok = True

    def check(passed: bool, msg: str) -> None:
        nonlocal ok
        checks.append(("PASS  " if passed else "FAIL  ") + msg)
        ok = ok and passed

    check(risk_state == "NORMAL",
          f"risk state is {risk_state} (must be NORMAL to open new risk)")
    check(ledger_reconciled_on == today.isoformat(),
          f"ledger reconciled today (last: {ledger_reconciled_on or 'NEVER'})")
    check(not positions_without_stops,
          f"every open position has a resting stop "
          f"(unprotected: {positions_without_stops or 'none'})")
    check(decision_approved,
          "the risk engine approved this order (never send an unapproved one)")
    check(ticket is not None, "an order ticket exists to send")

    if ticket is not None:
        check(ticket.stop_price < ticket.limit_price,
              f"stop {ticket.stop_price:.2f} is below entry {ticket.limit_price:.2f}")
        check(ticket.qty > 0, f"quantity {ticket.qty:g} is positive")
        notional = ticket.qty * ticket.limit_price
        check(notional <= equity,
              f"notional {notional:.2f} within equity {equity:.2f}")

        if require_authorization:
            auth = Authorization.load()
            if auth is None:
                check(False, "state/authorization.json missing — live orders "
                             "need a dated human authorization")
            else:
                valid, why = auth.valid_for(today, notional)
                check(valid, f"authorization: {why}")

    return PreflightResult(ok=ok, checks=checks)


def ticket_to_mcp_args(ticket: OrderTicket) -> Dict:
    """Shape a ticket into the arguments an order tool expects.

    Field names vary by tool and Robinhood may change them; read the tool's
    own schema from the MCP server and map onto it rather than trusting this
    dict. It exists so the agent has a checklist of what must be supplied,
    not so it can skip reading the schema.
    """
    args = {
        "symbol": ticket.symbol,
        "side": ticket.side,
        "quantity": ticket.qty,
        "order_type": "limit",
        "limit_price": round(ticket.limit_price, 2),
        "time_in_force": ticket.time_in_force,
        "stop_loss_price": round(ticket.stop_price, 2),
    }
    if ticket.take_profit:
        args["take_profit_price"] = round(ticket.take_profit, 2)
    return args


REQUIRED_ACCOUNT_SETUP = """\
Configure in the Robinhood app before Phase 3 (outside this repo):
  1. A DEDICATED agentic account. Never point the agent at your main account.
  2. Pre-load exactly the capital the agent is authorized to trade ($300).
     This is the hardest limit in the whole system — it is the only one the
     agent genuinely cannot reason its way around.
  3. Spending controls set at or below the agent's own risk policy.
  4. Order previews ON for the first live week, so every order is seen by a
     human before it is processed. Turn them off only after the agent has a
     paper-trading record you believe.
  5. Know where the instant-disable control is before you need it.
"""
