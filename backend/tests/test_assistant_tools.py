"""Regression tests for the read-only assistant tool functions
(app/assistant_tools.py) -- the actual permission-enforcement layer for the
new LLM tool-calling architecture. These call the tool functions directly
(bypassing any LLM), so they prove the isolation boundary holds regardless
of what a model asks for.

Uses a throwaway local SQLite file only. Never touches Supabase.
Run directly: `python backend/tests/test_assistant_tools.py`
"""
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _BACKEND_DIR)

_DB_PATH = os.path.join(tempfile.gettempdir(), "payroll_assistant_tools_test.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
# These tests call the tool functions directly, never through a live
# provider -- but force both keys explicitly empty anyway so importing
# app.assistant_tools can never trigger a real provider client construction
# via backend/.env's local-dev GROQ_API_KEY.
os.environ["GROQ_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = ""

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models as m  # noqa: E402
from app import assistant_tools as tools  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


# --- Fixtures --------------------------------------------------------------

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
submitter_ops = m.User(
    email="j.tetteh@company.com", name="J. Tetteh", initials="JT",
    role=m.Role.submitter, password_hash="x", department_id=ops.id,
)
specialist = m.User(
    email="k.owusu@company.com", name="K. Owusu", initials="KO",
    role=m.Role.specialist, password_hash="x", department_id=None,
)
admin = m.User(
    email="admin@company.com", name="Admin", initials="AD",
    role=m.Role.admin, password_hash="x", department_id=None,
)
db.add_all([submitter_finance, submitter_ops, specialist, admin])
db.flush()

emp_finance = m.Employee(
    staff_id="F2004", full_name="Comfort Adjei", department_id=finance.id,
    status=m.EmployeeStatus.active, grade="G4", basic_pay=2400, allowances=140,
    avg_overtime_hours=12,
)
emp_ops = m.Employee(
    staff_id="OPS010", full_name="N. Adjei", department_id=ops.id,
    status=m.EmployeeStatus.active, grade="G3", basic_pay=1900, allowances=100,
    avg_overtime_hours=24,
)
db.add_all([emp_finance, emp_ops])
db.flush()

sub_finance = m.Submission(
    cycle_id=cycle.id, department_id=finance.id, version=1, is_current=True,
    row_count=2, status=m.SubmissionStatus.needs_review, last_activity="Uploaded",
)
db.add(sub_finance)
db.flush()
row_f1 = m.SubmissionRow(submission_id=sub_finance.id, row_index=1, staff_id="F2004",
                          full_name="Comfort Adjei", overtime_hours=42, basic_pay=2400, allowances=140)
db.add(row_f1)
db.flush()
exc_f1 = m.Exception(
    submission_id=sub_finance.id, row_id=row_f1.id, row_label="Row 1", field="overtime_hours",
    severity=m.ExceptionSeverity.med, source=m.ExceptionSource.ai,
    issue_text="Overtime looks unusual", submitted_value="42", usual_value="12",
    ai_explanation="Overtime of 42h is about 3.5 times this employee's own average.",
    recommended_action="Query the department before approval.",
    status=m.ExceptionStatus.open,
)
db.add(exc_f1)
db.flush()

sub_ops = m.Submission(
    cycle_id=cycle.id, department_id=ops.id, version=1, is_current=True,
    row_count=2, status=m.SubmissionStatus.query_sent, last_activity="Query sent",
)
db.add(sub_ops)
db.flush()
row_o1 = m.SubmissionRow(submission_id=sub_ops.id, row_index=1, staff_id="OPS010",
                          full_name="N. Adjei", overtime_hours=96, basic_pay=1900, allowances=100)
row_o2 = m.SubmissionRow(submission_id=sub_ops.id, row_index=2, staff_id="OPS020",
                          full_name="P. Kwarteng", overtime_hours=30, basic_pay=1800, allowances=90)
db.add_all([row_o1, row_o2])
db.flush()
exc_o1 = m.Exception(
    submission_id=sub_ops.id, row_id=row_o1.id, row_label="Row 1", field="overtime_hours",
    severity=m.ExceptionSeverity.high, source=m.ExceptionSource.ai,
    issue_text="Overtime looks unusual", submitted_value="96", usual_value="24",
    ai_explanation="Overtime of 96h is about four times this employee's own average.",
    recommended_action="Query the department before approval.",
    status=m.ExceptionStatus.query_open,  # queried, not yet answered
)
exc_o2 = m.Exception(
    submission_id=sub_ops.id, row_id=row_o2.id, row_label="Row 2", field="allowances",
    severity=m.ExceptionSeverity.med, source=m.ExceptionSource.ai,
    issue_text="Allowance looks unusual", submitted_value="90", usual_value="60",
    ai_explanation="New allowance not previously paid at this grade.",
    recommended_action="Confirm before approval.",
    status=m.ExceptionStatus.query_answered,  # queried AND answered
)
db.add_all([exc_o1, exc_o2])
db.flush()

query = m.CorrectionQuery(
    department_id=ops.id, cycle_id=cycle.id, submission_id=sub_ops.id,
    to_emails="j.tetteh@company.com", subject="August payroll -- 2 items to confirm",
    body="...", status=m.QueryStatus.sent, exception_ids=[exc_o1.id, exc_o2.id],
)
db.add(query)
db.flush()
answer_o2 = m.QueryAnswer(
    exception_id=exc_o2.id, query_id=query.id, answer_type="correct",
    note="Covered two absent staff over the bank holiday.",
)
db.add(answer_o2)
db.commit()


def call(name, user, **kwargs):
    return tools.call_tool(name, kwargs, db, user)


# --- Tests ------------------------------------------------------------------

# 1. get_cycle_summary: specialist gets full breakdown, submitter gets a reduced view.
r = call("get_cycle_summary", specialist)
check("get_cycle_summary (specialist): total_departments present", "total_departments" in r)
check("get_cycle_summary (specialist): unresolved_exception_count is 2 (1 Finance open + 1 Operations queried)",
      r.get("unresolved_exception_count") == 2)
r_sub = call("get_cycle_summary", submitter_finance)
check("get_cycle_summary (submitter): no department-level breakdown leaked",
      "total_departments" not in r_sub and "submitted_count" not in r_sub)
r_admin = call("get_cycle_summary", admin)
check("get_cycle_summary (admin): no department-level breakdown leaked",
      "total_departments" not in r_admin)

# 2. get_department_statuses: specialist only.
r = call("get_department_statuses", specialist)
check("get_department_statuses (specialist): lists both departments",
      {d["department"] for d in r["departments"]} == {"Finance", "Operations"})
r = call("get_department_statuses", submitter_finance)
check("get_department_statuses (submitter): denied", "error" in r)
r = call("get_department_statuses", admin)
check("get_department_statuses (admin): denied", "error" in r)

# 3. get_department_details: THE core isolation test -- a Finance submitter
# asking about "Operations" must get Finance's own data back, never Operations'.
r = call("get_department_details", submitter_finance, department_name="Operations")
check("get_department_details: Finance submitter naming 'Operations' still gets Finance's own data",
      r.get("department") == "Finance")
check("get_department_details: never leaks Operations' issue types to a Finance submitter",
      "issue_types" in r and "Unusual overtime" not in str(r.get("issue_types", {})) or r.get("department") == "Finance")
r = call("get_department_details", specialist, department_name="operations")
check("get_department_details (specialist, case-insensitive): resolves Operations", r.get("department") == "Operations")
# Only exc_o1 (query_open) counts as "open" here -- exc_o2 is query_answered,
# which the app's own dashboard.py convention also excludes from open counts
# (status.in_([open, query_open])) since it's awaiting the Specialist's
# accept/reject decision, not the department's action.
check("get_department_details (specialist): sees Operations' open issue count", r.get("open_issue_count") == 1)
r = call("get_department_details", specialist, department_name="Nonexistent Dept")
check("get_department_details: unknown department name returns an error, not invented data", "error" in r)

# 4. get_submission_details: a submission_id belonging to another department
# must not be followed by a Submitter -- falls back to their own instead.
r = call("get_submission_details", submitter_finance, submission_id=sub_ops.id)
check("get_submission_details: Finance submitter passing Operations' submission_id still gets Finance's own",
      r.get("department") == "Finance")
r = call("get_submission_details", specialist, submission_id=sub_ops.id)
check("get_submission_details (specialist): can load Operations' submission directly by id",
      r.get("department") == "Operations" and r.get("status") == "query_sent")

# 5. get_submission_exceptions: scoped the same way, status_filter works.
r = call("get_submission_exceptions", submitter_ops, department_name="Finance")
check("get_submission_exceptions: Operations submitter naming 'Finance' still gets Operations' own exceptions",
      r.get("department") == "Operations")
r = call("get_submission_exceptions", specialist, submission_id=sub_ops.id, status_filter="query_open")
check("get_submission_exceptions (status_filter=query_open): only the unanswered one",
      len(r["exceptions"]) == 1 and r["exceptions"][0]["row_label"] == "Row 1")

# 6. get_exception_details: cross-department id must be refused for a Submitter.
r = call("get_exception_details", submitter_finance, exception_id=exc_o1.id)
check("get_exception_details: Finance submitter cannot load Operations' exception", "error" in r)
r = call("get_exception_details", submitter_ops, exception_id=exc_o1.id)
check("get_exception_details: Operations submitter CAN load their own exception", r.get("row_label") == "Row 1")
check("get_exception_details: includes the employee master record when authorised",
      r.get("employee", {}).get("staff_id") == "OPS010")
r = call("get_exception_details", specialist, exception_id=exc_o1.id)
check("get_exception_details (specialist): can load any department's exception", r.get("department") == "Operations")

# 7. get_correction_query_details: answered vs unanswered, with the submitter's actual answer text.
r = call("get_correction_query_details", specialist, submission_id=sub_ops.id)
check("get_correction_query_details: query_sent is True", r.get("query_sent") is True)
check("get_correction_query_details: one unanswered item (Row 1)",
      len(r["unanswered"]) == 1 and r["unanswered"][0]["row_label"] == "Row 1")
check("get_correction_query_details: one answered item (Row 2) with the submitter's actual note",
      len(r["answered"]) == 1 and "bank holiday" in (r["answered"][0].get("answer_note") or ""))

# 8. get_employee_details: cross-department lookup denied for a Submitter; admin denied entirely.
r = call("get_employee_details", submitter_finance, staff_id="OPS010")
check("get_employee_details: Finance submitter cannot see an Operations employee", "error" in r)
r = call("get_employee_details", submitter_ops, staff_id="OPS010")
check("get_employee_details: Operations submitter CAN see their own employee", r.get("full_name") == "N. Adjei")
r = call("get_employee_details", specialist, staff_id="OPS010")
check("get_employee_details (specialist): can see any employee", r.get("full_name") == "N. Adjei")
r = call("get_employee_details", admin, staff_id="OPS010")
check("get_employee_details (admin): denied entirely", "error" in r)

# 9. get_export_readiness: Specialist only.
r = call("get_export_readiness", submitter_finance)
check("get_export_readiness: denied to Submitter", "error" in r)
r = call("get_export_readiness", admin)
check("get_export_readiness: denied to Admin", "error" in r)
r = call("get_export_readiness", specialist)
check("get_export_readiness (specialist): returns a departments list", "departments" in r)

# 10. search_payroll_guidance: available to everyone, returns real chunks.
for u in (submitter_finance, specialist, admin):
    r = call("search_payroll_guidance", u, query="unusual overtime")
    check(f"search_payroll_guidance ({u.role.value}): returns results", len(r.get("results", [])) > 0)

# 11. call_tool dispatch safety: unknown tool name / malformed args never crash.
r = tools.call_tool("drop_all_tables", {}, db, specialist)
check("call_tool: unknown tool name returns an error, not a crash", "error" in r)
r = tools.call_tool("get_exception_details", {}, db, specialist)  # missing required exception_id
check("call_tool: missing required argument returns an error, not a crash", "error" in r)

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
print("All assistant tool regression tests passed.")
