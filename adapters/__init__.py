"""Broker adapters.

Every adapter obeys three rules:
  1. Dry-run by default. Sending real orders requires an explicit flag AND a
     dated human authorization recorded in state/authorization.json.
  2. Orders are never constructed here. Adapters receive a Decision that the
     risk engine has already approved, and translate it to the wire format.
  3. A protective stop is submitted in the same call as the entry, or the
     entry is not submitted at all.
"""
from .base import BrokerAdapter, AdapterError, Authorization   # noqa: F401
