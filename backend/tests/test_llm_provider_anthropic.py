"""Regression tests for the Anthropic tool-calling provider
(app/llm_providers/anthropic_provider.py) -- the orchestration loop itself,
not the tool functions (covered by test_assistant_tools.py) or the mock
fallback (covered by test_assistant_context.py).

This environment has no ANTHROPIC_API_KEY / outbound network access, so a
real end-to-end Claude call can't be exercised here. Instead, these tests
monkeypatch anthropic_provider._client with a fake Anthropic client that
returns pre-scripted tool_use / text responses -- proving the loop correctly
dispatches tool calls through the real, unmocked assistant_tools.call_tool()
(so real permission enforcement still runs), assembles multi-turn messages
correctly, handles multiple tool calls in one turn, and terminates safely if
a model never converges.

Uses a throwaway local SQLite file only. Never touches Supabase.
Run directly: `python backend/tests/test_llm_provider_anthropic.py`
"""
import json
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _BACKEND_DIR)

_DB_PATH = os.path.join(tempfile.gettempdir(), "payroll_provider_anthropic_test.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
# Force both provider keys explicitly empty so config.py's load_dotenv()
# can't backfill a real key from backend/.env (used for local dev) --
# every test here supplies its own fake client, so a real one must never
# get constructed or used.
os.environ["GROQ_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = ""

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models as m  # noqa: E402
import app.assistant_service as assistant_service  # noqa: E402
from app.llm_providers import anthropic_provider  # noqa: E402

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
SYSTEM = "system prompt text"


# --- Tests -------------------------------------------------------------

# 1. Isolation holds THROUGH the whole tool loop: a fake model asks for
# "Operations" department detail while the real user is a Finance submitter.
fake = FakeClient([
    FakeResp("tool_use", [
        FakeBlock("tool_use", id="t1", name="get_department_details",
                  input={"department_name": "Operations"}),
    ]),
    FakeResp("end_turn", [FakeBlock("text", text="Finance's submission needs review.")]),
])
anthropic_provider._client = fake
reply = anthropic_provider.run(SYSTEM, "What is the issue with Operations?", db, submitter_finance, ctx_finance)
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
anthropic_provider._client = fake2
reply2 = anthropic_provider.run(SYSTEM, "Give me an overview", db, specialist, ctx_specialist)
check("Multi-tool-call turn: final text returned", reply2 == "Here is the overview.")
second_msgs = fake2.messages.calls[1]["messages"]
tool_result_blocks = [
    b for msg in second_msgs if msg["role"] == "user" and isinstance(msg["content"], list)
    for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_result"
]
check("Multi-tool-call turn: both tool calls were dispatched and fed back", len(tool_result_blocks) == 2)

# 3. A model that never converges hits the iteration cap and returns None.
never_ending = FakeClient([
    FakeResp("tool_use", [FakeBlock("tool_use", id=f"t{i}", name="get_cycle_summary", input={})])
    for i in range(anthropic_provider.MAX_TOOL_ITERATIONS + 2)
])
anthropic_provider._client = never_ending
reply3 = anthropic_provider.run(SYSTEM, "loop forever", db, specialist, ctx_specialist)
check("Iteration cap: a non-converging model returns None (safe fallback), not a hang or crash",
      reply3 is None)
check("Iteration cap: the fake client was called at most MAX_TOOL_ITERATIONS times",
      len(never_ending.messages.calls) <= anthropic_provider.MAX_TOOL_ITERATIONS)

anthropic_provider._client = None  # restore

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
print("All Anthropic provider regression tests passed.")
