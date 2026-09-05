"""Regression tests for the LLM tool-calling ORCHESTRATION loop
(assistant_service._answer_with_tools) -- the part that decides which tool
results to feed back to the model and when to stop.

This environment has no ANTHROPIC_API_KEY / outbound network access, so a
real end-to-end Claude call can't be exercised here. Instead, these tests
monkeypatch assistant_service._client with a fake Anthropic client that
returns pre-scripted tool_use / text responses -- which is exactly the right
boundary to test at: it proves the LOOP correctly dispatches tool calls
through the real, unmocked assistant_tools.call_tool() (so real permission
enforcement still runs), assembles multi-turn messages correctly, handles
multiple tool calls in one turn, and terminates safely if a model never
converges. The tool functions themselves are covered by
test_assistant_tools.py; the mock-fallback path is covered by
test_assistant_context.py.

Uses a throwaway local SQLite file only. Never touches Supabase.
Run directly: `python backend/tests/test_assistant_tool_loop.py`
"""
import json
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _BACKEND_DIR)

_DB_PATH = os.path.join(tempfile.gettempdir(), "payroll_assistant_loop_test.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models as m  # noqa: E402
import app.assistant_service as assistant_service  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


# --- Fake Anthropic client -------------------------------------------------

class FakeBlock:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class FakeResp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("FakeMessages exhausted -- test scripted too few responses")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


# --- Fixtures ---------------------------------------------------------------

finance = m.Department(name="Finance", contact_email="finance@company.com")
ops = m.Department(name="Operations", contact_email="ops@company.com")
db.add_all([finance, ops])
db.flush()

cycle = m.Cycle(label="August 2026", cutoff_date="2026-09-05", is_current=True)
db.add(cycle)
db.flush()

submitter_finance = m.User(
    email="a.mensah@company.com", name="A. Mensah", initials="AM",
    role=m.Role.submitter, password_hash="x", department_id=finance.id,
)
specialist = m.User(
    email="k.owusu@company.com", name="K. Owusu", initials="KO",
    role=m.Role.specialist, password_hash="x", department_id=None,
)
db.add_all([submitter_finance, specialist])
db.flush()

sub_finance = m.Submission(
    cycle_id=cycle.id, department_id=finance.id, version=1, is_current=True,
    row_count=1, status=m.SubmissionStatus.needs_review, last_activity="Uploaded",
)
sub_ops = m.Submission(
    cycle_id=cycle.id, department_id=ops.id, version=1, is_current=True,
    row_count=1, status=m.SubmissionStatus.query_sent, last_activity="Query sent",
)
db.add_all([sub_finance, sub_ops])
db.commit()

ctx_finance = assistant_service.build_context(db, submitter_finance)
ctx_specialist = assistant_service.build_context(db, specialist)


# --- Tests -------------------------------------------------------------

# 1. Isolation holds THROUGH the whole tool loop: a fake model asks for
# "Operations" department detail while the real user is a Finance submitter.
# The dispatched tool result (fed back to the "model") must be scoped to
# Finance, never Operations -- proving the loop doesn't just trust the
# model's tool-call arguments.
fake = FakeClient([
    FakeResp("tool_use", [
        FakeBlock("tool_use", id="t1", name="get_department_details",
                  input={"department_name": "Operations"}),
    ]),
    FakeResp("end_turn", [FakeBlock("text", text="Finance's submission needs review.")]),
])
assistant_service._client = fake
reply = assistant_service._answer_with_tools(
    db, submitter_finance, "What is the issue with Operations?", ctx_finance
)
check("Tool loop returns the model's final text", reply == "Finance's submission needs review.")

second_call_messages = fake.messages.calls[1]["messages"]
tool_result_content = None
for msg in second_call_messages:
    if msg["role"] == "user" and isinstance(msg["content"], list):
        for block in msg["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_result_content = block["content"]
parsed = json.loads(tool_result_content) if tool_result_content else {}
check("Tool loop isolation: dispatched result is scoped to Finance (the real user), not the requested Operations",
      parsed.get("department") == "Finance")

# 2. Multiple tool calls in a single turn are all dispatched and fed back.
fake2 = FakeClient([
    FakeResp("tool_use", [
        FakeBlock("tool_use", id="t1", name="get_department_statuses", input={}),
        FakeBlock("tool_use", id="t2", name="get_export_readiness", input={}),
    ]),
    FakeResp("end_turn", [FakeBlock("text", text="Here is the overview.")]),
])
assistant_service._client = fake2
reply2 = assistant_service._answer_with_tools(db, specialist, "Give me an overview", ctx_specialist)
check("Multi-tool-call turn: final text returned", reply2 == "Here is the overview.")
second_msgs = fake2.messages.calls[1]["messages"]
tool_result_blocks = [
    b for msg in second_msgs if msg["role"] == "user" and isinstance(msg["content"], list)
    for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_result"
]
check("Multi-tool-call turn: both tool calls were dispatched and fed back", len(tool_result_blocks) == 2)

# 3. A model that never converges (always requests a tool) hits the
# iteration cap and the loop returns None -- the caller then falls back to
# the deterministic mock rather than hanging or erroring.
never_ending = FakeClient([
    FakeResp("tool_use", [FakeBlock("tool_use", id=f"t{i}", name="get_cycle_summary", input={})])
    for i in range(assistant_service.MAX_TOOL_ITERATIONS + 2)
])
assistant_service._client = never_ending
reply3 = assistant_service._answer_with_tools(db, specialist, "loop forever", ctx_specialist)
check("Iteration cap: a non-converging model returns None (safe fallback), not a hang or crash",
      reply3 is None)
check("Iteration cap: the fake client was called at most MAX_TOOL_ITERATIONS times",
      len(never_ending.messages.calls) <= assistant_service.MAX_TOOL_ITERATIONS)

# 4. Role framing / guardrails are actually present in the system prompt sent.
fake4 = FakeClient([FakeResp("end_turn", [FakeBlock("text", text="ok")])])
assistant_service._client = fake4
assistant_service._answer_with_tools(db, submitter_finance, "hello", ctx_finance)
sent_system = fake4.messages.calls[0]["system"]
check("System prompt includes the read-only/no-write guardrail",
      "read-only" in sent_system.lower())
check("System prompt includes the Submitter role framing",
      "Department Submitter" in sent_system)
check("System prompt forbids revealing secrets/credentials",
      "credentials" in sent_system.lower() and "password hashes" in sent_system.lower())

# 5. Full answer() falls back to mock when the tool loop yields no usable text.
no_text = FakeClient([FakeResp("end_turn", [])])  # no text block at all
assistant_service._client = no_text
result = assistant_service.answer(db, submitter_finance, "What is the issue?")
check("answer() falls back to the mock path when the live loop produces no text",
      "F2004" in result["reply"] or "no unresolved issues" in result["reply"].lower()
      or "don't see a current submission" in result["reply"].lower())

assistant_service._client = None  # restore -- don't leak a fake client past this test module

print()
db.close()
engine.dispose()
try:
    if os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)
except PermissionError:
    pass

if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All assistant tool-loop regression tests passed.")
