"""Regression tests for the Payroll Assistant's contextual-intent handling.

Bug this covers: vague questions about a user's own current submission
("What is the issue?", "What do I fix in my current submission?") were
falling through to a generic, unrelated RAG policy passage instead of the
user's actual live exceptions. These tests assert that such questions are
now answered from the authenticated user's real current submission and
exceptions first -- RAG only supplements, never replaces, that -- and that
role isolation and the no-action guardrails still hold.

Uses a throwaway local SQLite file only. Never touches Supabase.
Run directly: `python backend/tests/test_assistant_context.py`
"""
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _BACKEND_DIR)

_DB_PATH = os.path.join(tempfile.gettempdir(), "payroll_assistant_context_test.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models as m  # noqa: E402
from app import assistant_service  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


def ask(user, message, submission_id=None, exception_id=None):
    return assistant_service.answer(
        db, user, message, submission_id=submission_id, exception_id=exception_id
    )["reply"]


# --- Seed minimal fixtures ---------------------------------------------

finance = m.Department(name="Finance", contact_email="finance@company.com")
ops = m.Department(name="Operations", contact_email="ops@company.com")
clean_dept = m.Department(name="Marketing", contact_email="marketing@company.com")
db.add_all([finance, ops, clean_dept])
db.flush()

cycle = m.Cycle(label="August 2026", cutoff_date="2026-09-05", is_current=True)
db.add(cycle)
db.flush()

submitter_finance = m.User(
    email="a.mensah@company.com", name="A. Mensah", initials="AM",
    role=m.Role.submitter, password_hash="x", department_id=finance.id,
)
submitter_clean = m.User(
    email="b.owusu@company.com", name="B. Owusu", initials="BO",
    role=m.Role.submitter, password_hash="x", department_id=clean_dept.id,
)
specialist = m.User(
    email="k.owusu@company.com", name="K. Owusu", initials="KO",
    role=m.Role.specialist, password_hash="x", department_id=None,
)
db.add_all([submitter_finance, submitter_clean, specialist])
db.flush()

# Finance: submission WITH issues -- the scenario from the bug report.
sub_finance = m.Submission(
    cycle_id=cycle.id, department_id=finance.id, version=1, is_current=True,
    row_count=2, status=m.SubmissionStatus.needs_review, last_activity="Uploaded",
)
db.add(sub_finance)
db.flush()

row1 = m.SubmissionRow(submission_id=sub_finance.id, row_index=1, staff_id="F2004",
                        full_name=None, overtime_hours=5, basic_pay=2400, allowances=140)
row2 = m.SubmissionRow(submission_id=sub_finance.id, row_index=2, staff_id="F3010",
                        full_name="Comfort Adjei", overtime_hours=42, basic_pay=1900, allowances=100)
db.add_all([row1, row2])
db.flush()

exc1 = m.Exception(
    submission_id=sub_finance.id, row_id=row1.id, row_label="Row 1", field="staff_id",
    severity=m.ExceptionSeverity.high, source=m.ExceptionSource.rule,
    issue_text="Staff ID F2004 is not on the employee record", submitted_value="F2004",
    status=m.ExceptionStatus.open,
)
exc2 = m.Exception(
    submission_id=sub_finance.id, row_id=row2.id, row_label="Row 2", field="overtime_hours",
    severity=m.ExceptionSeverity.med, source=m.ExceptionSource.ai,
    issue_text="Overtime looks unusual", submitted_value="42", usual_value="12",
    ai_explanation="Overtime of 42h is about 3.5 times this employee's own average.",
    recommended_action="Query the department before approval.",
    status=m.ExceptionStatus.open,
)
db.add_all([exc1, exc2])

# Operations: a DIFFERENT department's submission/issue, to prove role
# isolation still holds after this change.
sub_ops = m.Submission(
    cycle_id=cycle.id, department_id=ops.id, version=1, is_current=True,
    row_count=1, status=m.SubmissionStatus.needs_review, last_activity="Uploaded",
)
db.add(sub_ops)
db.flush()
row_ops = m.SubmissionRow(submission_id=sub_ops.id, row_index=1, staff_id="OPS999",
                           full_name="Someone Else", overtime_hours=8, basic_pay=1000, allowances=0)
db.add(row_ops)
db.flush()
exc_ops = m.Exception(
    submission_id=sub_ops.id, row_id=row_ops.id, row_label="Row 1", field="staff_id",
    severity=m.ExceptionSeverity.high, source=m.ExceptionSource.rule,
    issue_text="Staff ID OPS999 is not on the employee record", submitted_value="OPS999",
    status=m.ExceptionStatus.open,
)
db.add(exc_ops)

# Marketing: a CLEAN submission with zero exceptions, for the "no
# unresolved issues" test.
sub_clean = m.Submission(
    cycle_id=cycle.id, department_id=clean_dept.id, version=1, is_current=True,
    row_count=1, status=m.SubmissionStatus.needs_review, last_activity="Uploaded",
)
db.add(sub_clean)
db.flush()
row_clean = m.SubmissionRow(submission_id=sub_clean.id, row_index=1, staff_id="MK001",
                             full_name="Clean Person", overtime_hours=2, basic_pay=1500, allowances=50)
db.add(row_clean)
db.commit()


# --- Tests ----------------------------------------------------------------

# 1. "What is the issue?" -- the exact query from the bug report.
reply = ask(submitter_finance, "What is the issue?")
check("'What is the issue?' surfaces the actual Finance exception (F2004 / Unknown employee)",
      "F2004" in reply and "Unknown employee" in reply)
check("'What is the issue?' does not answer with unrelated allowance policy text",
      "allowance" not in reply.lower())

# 2. "What do I fix in my current submission?" -- the second bug-report query.
reply = ask(submitter_finance, "What do I fix in my current submission?")
check("'What do I fix in my current submission?' lists a real issue, not a policy tangent",
      "F2004" in reply or "Row 1" in reply)
check("'What do I fix...' no longer hallucinates the old 'you can submit with issues open' answer",
      "you can submit with issues" not in reply.lower())

# 3. "Explain my current issues."
reply = ask(submitter_finance, "Explain my current issues.")
check("'Explain my current issues.' includes both real Finance issues",
      "Unknown employee" in reply and "Unusual overtime" in reply)
check("'Explain my current issues.' includes a recommended action per issue",
      "Recommended action" in reply)

# 4. "Which rows need attention?"
reply = ask(submitter_finance, "Which rows need attention?")
check("'Which rows need attention?' names the actual flagged rows",
      "Row 1" in reply and "Row 2" in reply)

# 5. Clean submission -> "What do I need to fix?" must NOT return generic policy advice.
reply = ask(submitter_clean, "What do I need to fix?")
check("Clean submission: 'What do I need to fix?' says no unresolved issues, not generic policy",
      reply.strip() == "Your current submission has no unresolved issues.")

# 6. Role isolation: Finance submitter must never see Operations' exception.
reply = ask(submitter_finance, "What is the issue?")
check("Role isolation: Finance submitter's answer never contains Operations' OPS999 exception",
      "OPS999" not in reply)

# 7. Role isolation via a smuggled cross-department submission_id.
ctx = assistant_service.build_context(db, submitter_finance, submission_id=sub_ops.id)
check("Role isolation: a Finance submitter's context ignores a smuggled Operations submission_id",
      ctx.get("department") != "Operations")

# 8. No internal technical terminology leaks into any tested reply.
all_replies = [
    ask(submitter_finance, "What is the issue?"),
    ask(submitter_finance, "Explain my current issues."),
    ask(submitter_clean, "What do I need to fix?"),
]
import re  # noqa: E402
leak_terms = (r"\brag\b", r"\bbm25\b", "retrieval", "embedding", "confidence score",
              "ai fallback", "source: rule", "source: ai")
leaked = [t for t in leak_terms for r in all_replies if re.search(t, r.lower())]
check("No internal technical terminology leaks into any tested reply", not leaked)

# 9. Guardrail still holds: an issue-shaped message asking for action is refused, not answered.
reply = ask(submitter_finance, "Can you approve my submission for me right now?")
check("Guardrail still holds: assistant refuses an approval request instead of listing issues",
      "can't" in reply.lower() and "approv" in reply.lower())

# 10. RAG still answers a genuine standalone policy question (not a current-submission one).
reply = ask(submitter_finance, "What counts as unusual overtime under policy?")
check("RAG still answers a genuine standalone policy question", len(reply) > 0)


# --- Specialist context hierarchy ------------------------------------------
# Finance has 2 open issues, Operations has 1 -- 3 total across 2 departments.

# 11. Specialist on the global Dashboard: several phrasings must all surface
# the real cross-department workload, not a generic policy passage. Includes
# the exact wording from a live-bug report ("Summarize the issues for me",
# US spelling + trailing "for me") to lock that specific case in, alongside
# the three other phrasings the user also asked to be re-verified.
for q in ("Summarize the issues for me", "What is the issue?", "What needs my attention?",
          "What do I need to review?"):
    reply = ask(specialist, q)
    check(f"Specialist dashboard: '{q}' names Finance", "Finance" in reply)
    check(f"Specialist dashboard: '{q}' names Operations", "Operations" in reply)
    check(f"Specialist dashboard: '{q}' shows the live total (3 issues)", "3" in reply)
    check(f"Specialist dashboard: '{q}' is not the old generic allowance-policy passage",
          "allowance" not in reply.lower())
    check(f"Specialist dashboard: '{q}' does not say 'I don't see a current submission'",
          "i don't see a current submission" not in reply.lower())
    check(f"Specialist dashboard: '{q}' does not say 'Upload a file first'",
          "upload a file first" not in reply.lower())

# 12. Specialist scoped to ONE submission (as if on that department's
# Exception Review page): "What is the issue?" must return only that
# submission's exceptions, not the other department's or the whole workload.
reply = ask(specialist, "What is the issue?", submission_id=sub_finance.id)
check("Specialist on Finance submission: sees Finance's own exception (F2004)", "F2004" in reply)
check("Specialist on Finance submission: does NOT see Operations' exception (OPS999)",
      "OPS999" not in reply)

# 13. Specialist focused on a specific exception: that exception is
# prioritised over both the submission list and the dashboard summary.
reply = ask(specialist, "What is wrong here?", submission_id=sub_ops.id, exception_id=exc_ops.id)
check("Specialist focused on one exception: explains that exact exception (OPS999)",
      "OPS999" in reply or "Unknown employee" in reply)

# 14. Role isolation still holds: a Submitter's dashboard-style question
# never gets the specialist's cross-department view -- it stays scoped to
# their own department only (Finance's F2004, never Operations' OPS999).
reply = ask(submitter_finance, "What needs my attention?")
check("Submitter isolation intact: 'What needs my attention?' still Finance-only",
      "F2004" in reply and "OPS999" not in reply)

# 15. Clean dashboard: once every exception is resolved, the Specialist must
# be told plainly there's nothing outstanding -- never an invented issue or
# a generic policy answer.
for exc in (exc1, exc2, exc_ops):
    exc.status = m.ExceptionStatus.accepted
db.commit()
reply = ask(specialist, "What needs my attention?")
check("Clean dashboard: Specialist is told there are no unresolved issues",
      reply.strip() == "There are no unresolved issues requiring your attention.")

print()
db.close()
engine.dispose()
try:
    if os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)
except PermissionError:
    pass  # Windows may still hold a brief handle; harmless, it's in the temp dir.

if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All assistant contextual-intent regression tests passed.")
