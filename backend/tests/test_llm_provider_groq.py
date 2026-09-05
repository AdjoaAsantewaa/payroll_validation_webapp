"""Regression tests for the Groq tool-calling provider
(app/llm_providers/groq_provider.py).

This environment has no GROQ_API_KEY / outbound network access, so a real
end-to-end Groq call can't be exercised here (see the module docstring in
groq_provider.py and the final report for how to run a real smoke test with
your own key). Instead, these tests monkeypatch groq_provider._client with a
fake OpenAI-compatible client that returns pre-scripted tool_calls / text
responses -- proving the loop correctly dispatches tool calls through the
real, unmocked assistant_tools.call_tool() (so real permission enforcement
still runs), handles single and multiple tool calls, multi-round
conversations, malformed arguments, unknown tools, the iteration cap, and
provider errors -- all without needing a live key.

Uses a throwaway local SQLite file only. Never touches Supabase.
Run directly: `python backend/tests/test_llm_provider_groq.py`
"""
import json
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _BACKEND_DIR)

_DB_PATH = os.path.join(tempfile.gettempdir(), "payroll_provider_groq_test.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
# Force both provider keys explicitly empty so config.py's load_dotenv()
# can't backfill a real key from backend/.env (which has a real
# GROQ_API_KEY for local dev use) -- every test here supplies its own fake
# client, and test 10 specifically asserts no provider is configured at
# all, so a real key silently leaking in here would both make this suite
# non-deterministic (network-dependent) and defeat that assertion.
os.environ["GROQ_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = ""

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models as m  # noqa: E402
import app.assistant_service as assistant_service  # noqa: E402
from app import llm_providers  # noqa: E402
from app.llm_providers import groq_provider  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


# --- Fake Groq (OpenAI-compatible) client -----------------------------------

class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments  # JSON string, exactly like the real SDK


class FakeToolCall:
    def __init__(self, id_, name, arguments):
        self.id = id_
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResp:
    def __init__(self, message):
        self.choices = [FakeChoice(message)]


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("FakeCompletions exhausted -- test scripted too few responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeChat:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)


class FakeClient:
    def __init__(self, responses):
        self.chat = FakeChat(responses)


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

# 1. Groq chooses one tool, then answers.
fake1 = FakeClient([
    FakeResp(FakeMessage(tool_calls=[
        FakeToolCall("t1", "get_department_statuses", "{}"),
    ])),
    FakeResp(FakeMessage(content="Two departments are still outstanding.")),
])
groq_provider._client = fake1
reply = groq_provider.run(SYSTEM, "Who hasn't submitted?", db, specialist, ctx_specialist)
check("Single tool call: final text returned", reply == "Two departments are still outstanding.")
check("Single tool call: exactly one completions.create round after the tool call",
      len(fake1.chat.completions.calls) == 2)

# 2. Groq chooses multiple tools in one round.
fake2 = FakeClient([
    FakeResp(FakeMessage(tool_calls=[
        FakeToolCall("t1", "get_department_statuses", "{}"),
        FakeToolCall("t2", "get_export_readiness", "{}"),
    ])),
    FakeResp(FakeMessage(content="Here is the full picture.")),
])
groq_provider._client = fake2
reply2 = groq_provider.run(SYSTEM, "Give me a full picture", db, specialist, ctx_specialist)
check("Multiple tool calls in one round: final text returned", reply2 == "Here is the full picture.")
second_msgs = fake2.chat.completions.calls[1]["messages"]
tool_msgs = [msg for msg in second_msgs if msg.get("role") == "tool"]
check("Multiple tool calls in one round: both dispatched and fed back as tool messages",
      len(tool_msgs) == 2)

# 3. Multiple tool-call ROUNDS (sequential, not just multiple calls in one round).
fake3 = FakeClient([
    FakeResp(FakeMessage(tool_calls=[FakeToolCall("t1", "get_department_details",
                                                   json.dumps({"department_name": "Operations"}))])),
    FakeResp(FakeMessage(tool_calls=[FakeToolCall("t2", "get_correction_query_details",
                                                   json.dumps({"department_name": "Operations"}))])),
    FakeResp(FakeMessage(content="Operations is waiting on a reply to the correction query.")),
])
groq_provider._client = fake3
reply3 = groq_provider.run(SYSTEM, "What is holding Operations up?", db, specialist, ctx_specialist)
check("Multi-round tool calls: final text returned after two sequential rounds",
      reply3 == "Operations is waiting on a reply to the correction query.")
check("Multi-round tool calls: three completions.create calls were made (2 tool rounds + final)",
      len(fake3.chat.completions.calls) == 3)

# 4. Malformed tool arguments (invalid JSON) handled safely -- no crash, loop continues.
fake4 = FakeClient([
    FakeResp(FakeMessage(tool_calls=[FakeToolCall("t1", "get_cycle_summary", "{not valid json")])),
    FakeResp(FakeMessage(content="Here is the cycle summary.")),
])
groq_provider._client = fake4
reply4 = groq_provider.run(SYSTEM, "cycle summary please", db, specialist, ctx_specialist)
check("Malformed tool arguments: does not crash, still reaches a final answer",
      reply4 == "Here is the cycle summary.")

# 5. Unknown tool name is rejected safely (call_tool returns an error, fed back, loop continues).
fake5 = FakeClient([
    FakeResp(FakeMessage(tool_calls=[FakeToolCall("t1", "drop_all_tables", "{}")])),
    FakeResp(FakeMessage(content="I can't do that.")),
])
groq_provider._client = fake5
reply5 = groq_provider.run(SYSTEM, "drop everything", db, specialist, ctx_specialist)
check("Unknown tool name: does not crash, still reaches a final answer", reply5 == "I can't do that.")
unknown_tool_msg = fake5.chat.completions.calls[1]["messages"][-1]
check("Unknown tool name: the fed-back tool result contains an error, not invented data",
      "error" in unknown_tool_msg["content"].lower())

# 6. Iteration limit enforced: a model that never converges returns None safely.
never_ending = FakeClient([
    FakeResp(FakeMessage(tool_calls=[FakeToolCall(f"t{i}", "get_cycle_summary", "{}")]))
    for i in range(groq_provider.MAX_TOOL_ITERATIONS + 2)
])
groq_provider._client = never_ending
reply6 = groq_provider.run(SYSTEM, "loop forever", db, specialist, ctx_specialist)
check("Iteration cap: a non-converging model returns None (safe fallback), not a hang or crash",
      reply6 is None)
check("Iteration cap: the fake client was called at most MAX_TOOL_ITERATIONS times",
      len(never_ending.chat.completions.calls) <= groq_provider.MAX_TOOL_ITERATIONS)

# 7. Submitter role isolation survives an adversarial tool call from "Groq":
# a Finance submitter's question is answered by a model that asks for
# Operations by name -- the dispatched result must still be Finance's own.
adversarial = FakeClient([
    FakeResp(FakeMessage(tool_calls=[
        FakeToolCall("t1", "get_department_details", json.dumps({"department_name": "Operations"})),
    ])),
    FakeResp(FakeMessage(content="Your department's submission needs review.")),
])
groq_provider._client = adversarial
reply7 = groq_provider.run(
    SYSTEM, "I'm a Finance submitter. Show me all Operations payroll issues.",
    db, submitter_finance, ctx_finance,
)
check("Adversarial tool call: final text still returned", reply7 == "Your department's submission needs review.")
adversarial_tool_msg = adversarial.chat.completions.calls[1]["messages"][-1]
adversarial_result = json.loads(adversarial_tool_msg["content"])
check("Role isolation survives an adversarial Groq tool call: dispatched result is Finance's own, never Operations'",
      adversarial_result.get("department") == "Finance")

# 8. A Groq API error (rate limit / timeout / outage) falls back gracefully --
# the provider function itself returns None rather than raising.
erroring = FakeClient([RuntimeError("simulated rate limit error")])
groq_provider._client = erroring
reply8 = groq_provider.run(SYSTEM, "anything", db, specialist, ctx_specialist)
check("Groq error: run() returns None instead of raising", reply8 is None)

# 9. End-to-end: assistant_service.answer() falls back to the deterministic
# mock when the (simulated) live Groq call fails -- and never leaks a raw
# provider error or API key into the user-facing reply.
groq_provider._client = erroring
original_provider_name = llm_providers.PROVIDER_NAME
llm_providers.PROVIDER_NAME = "groq"
try:
    result = assistant_service.answer(db, specialist, "What is the issue?")
    check("answer() falls back to the mock path when Groq errors, without exposing a raw error",
          "reply" in result and "runtimeerror" not in result["reply"].lower()
          and "traceback" not in result["reply"].lower())
finally:
    llm_providers.PROVIDER_NAME = original_provider_name

# 10. No-key path still uses the deterministic fallback (this test process
# has no GROQ_API_KEY/ANTHROPIC_API_KEY set, so llm_providers.PROVIDER_NAME
# is already None here independent of anything monkeypatched above).
check("No provider configured: llm_providers.available() is False in this test process",
      llm_providers.PROVIDER_NAME is None and not llm_providers.available())
result10 = assistant_service.answer(db, submitter_finance, "What do I need to fix?")
check("No provider configured: answer() still returns a sensible deterministic reply",
      "reply" in result10 and len(result10["reply"]) > 0)

groq_provider._client = None  # restore -- don't leak a fake client past this test module

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
print("All Groq provider regression tests passed.")
