"""Groq tool-calling provider for the Payroll Assistant.

Groq's chat-completions API is OpenAI-compatible, so this module speaks
that dialect: tools as {"type": "function", "function": {...}}, tool
results as role="tool" messages. The read-only tool SCHEMAS defined in
app/assistant_tools.py are written once in Anthropic's format and
translated here purely as a data-shape conversion (_to_function_tools) --
the underlying tool FUNCTIONS and their permission enforcement are called
through the exact same assistant_tools.call_tool() dispatcher Anthropic
uses, never duplicated or reimplemented.
"""
from __future__ import annotations

import json
import logging

from app.config import GROQ_API_KEY, GROQ_MODEL
from app import assistant_tools

log = logging.getLogger(__name__)

# Cap on tool-call round-trips per answer -- same bound as the Anthropic
# provider, for the same reason (bound the worst case of a model that never
# converges on a final answer).
MAX_TOOL_ITERATIONS = 6

_client = None
if GROQ_API_KEY:
    try:
        import groq
        _client = groq.Groq(api_key=GROQ_API_KEY)
    except Exception:
        _client = None


def _to_function_tools(tool_schemas: list[dict]) -> list[dict]:
    """Anthropic-style {name, description, input_schema} -> the OpenAI/Groq
    function-calling shape {"type": "function", "function": {name,
    description, parameters}}. Pure schema reformatting -- no tool logic
    lives here."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in tool_schemas
    ]


_TOOLS = _to_function_tools(assistant_tools.TOOL_SCHEMAS)


def available() -> bool:
    return _client is not None


def run(system: str, first_message: str, db, user, ctx: dict) -> str | None:
    """Returns the model's final text, or None on any failure (no client, no
    text produced, exceeded iteration cap, API error -- rate limit, timeout,
    provider outage) so the caller falls back to the deterministic mock.
    Never logs the API key or raw provider exception text -- just that a
    call failed."""
    if not _client:
        return None

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": first_message},
    ]

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = _client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=900, messages=messages,
                tools=_TOOLS, tool_choice="auto",
            )
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []
            if not tool_calls:
                return (msg.content or "").strip() or None

            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    if not isinstance(args, dict):
                        args = {}
                except (json.JSONDecodeError, TypeError):
                    # A malformed/non-JSON argument string from the model is
                    # not an error worth failing the whole request over --
                    # call_tool() below still enforces required arguments
                    # and reports back to the model as {"error": ...} so it
                    # can retry with corrected arguments.
                    args = {}
                result = assistant_tools.call_tool(tc.function.name, args, db, user, ctx)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str)[:6000],
                })
    except Exception:
        log.warning("Groq provider request failed; falling back to the deterministic answer.")
        return None

    return None
