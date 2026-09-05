"""Live LLM provider selection for the Payroll Assistant.

Exactly one provider is active per process, resolved once at import time
from config (see _resolve_provider_name below) -- not re-decided per
request. Both providers implement the identical interface:

    available() -> bool
    run(system: str, first_message: str, db, user, ctx: dict) -> str | None

assistant_service.py only ever calls this module's available()/run(); it
never imports anthropic_provider or groq_provider directly, and never
branches on which one is active -- that keeps assistant_service.py's
guardrails, context-building, and fallback logic identical regardless of
provider, per the "shared logic stays shared" design.

Selection order:
    1. LLM_PROVIDER explicitly set to "groq" or "anthropic" -- authoritative.
       If that provider's key is missing, the assistant falls back to the
       deterministic mock rather than silently using the other provider.
    2. Otherwise: GROQ_API_KEY present -> groq; else ANTHROPIC_API_KEY
       present -> anthropic; else no live provider (mock only).
"""
from __future__ import annotations

from app.config import LLM_PROVIDER, GROQ_API_KEY, ANTHROPIC_API_KEY
from app.llm_providers import anthropic_provider, groq_provider


def _resolve_provider_name() -> str | None:
    explicit = (LLM_PROVIDER or "").strip().lower()
    if explicit == "groq":
        return "groq"
    if explicit == "anthropic":
        return "anthropic"
    if explicit:
        return None  # an unrecognised explicit value -- don't guess
    if GROQ_API_KEY:
        return "groq"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return None


PROVIDER_NAME = _resolve_provider_name()


def available() -> bool:
    if PROVIDER_NAME == "groq":
        return groq_provider.available()
    if PROVIDER_NAME == "anthropic":
        return anthropic_provider.available()
    return False


def run(system: str, first_message: str, db, user, ctx: dict) -> str | None:
    if PROVIDER_NAME == "groq":
        return groq_provider.run(system, first_message, db, user, ctx)
    if PROVIDER_NAME == "anthropic":
        return anthropic_provider.run(system, first_message, db, user, ctx)
    return None
