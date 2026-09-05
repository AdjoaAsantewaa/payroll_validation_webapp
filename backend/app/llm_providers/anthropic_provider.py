"""Anthropic (Claude) tool-calling provider for the Payroll Assistant.

Same tool-loop this app has always used -- moved here unchanged (out of
assistant_service.py) so that adding Groq as a second provider didn't
require rewriting this one. Reuses the exact same read-only tools in
app/assistant_tools.py; nothing about the tool functions or their
permission enforcement is duplicated or reinterpreted here.
"""
from __future__ import annotations

import json

from app.config import ANTHROPIC_API_KEY, AI_MODEL
from app import assistant_tools

# Cap on tool-call round-trips per answer -- generous enough for genuinely
# multi-fact questions while bounding the worst case if the model never
# converges on a final answer.
MAX_TOOL_ITERATIONS = 6

_client = None
if ANTHROPIC_API_KEY:
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception:
        _client = None


def available() -> bool:
    return _client is not None


def run(system: str, first_message: str, db, user, ctx: dict) -> str | None:
    """Returns the model's final text, or None on any failure (no client, no
    text produced, exceeded iteration cap, API error) so the caller falls
    back to the deterministic mock."""
    if not _client:
        return None

    messages: list[dict] = [{"role": "user", "content": first_message}]

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = _client.messages.create(
                model=AI_MODEL, max_tokens=900, system=system,
                tools=assistant_tools.TOOL_SCHEMAS, messages=messages,
            )
            if resp.stop_reason != "tool_use":
                text = "".join(
                    block.text for block in resp.content if getattr(block, "type", None) == "text"
                )
                return text.strip() or None

            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                result = assistant_tools.call_tool(block.name, block.input or {}, db, user, ctx)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str)[:6000],
                })
            if not tool_results:
                return None
            messages.append({"role": "user", "content": tool_results})
    except Exception:
        return None

    return None
