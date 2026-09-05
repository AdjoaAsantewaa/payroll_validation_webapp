"""Read-only application "tools" the Payroll Assistant's LLM can call.

This is the permission boundary for the whole tool-use architecture: every
function here takes the AUTHENTICATED `user` (from the JWT, via
get_current_user) and derives what that user is allowed to see itself. The
LLM supplies only *which* department/submission/exception it wants to look
at -- it is never trusted to decide whether the asker is allowed to see it.
A Submitter passing a different department's name, or a smuggled
submission_id/exception_id belonging to another department, gets silently
redirected to their own department or an explicit error, exactly like
build_context()'s existing role-isolation boundary in assistant_service.py.

Every function here is a pure read: none of them call db.add/db.commit, none
of them touch a write endpoint. There is no mechanism by which a tool call
can approve, reject, modify a value, send a query, resubmit a file, or
create a user -- see assistant_service.GUARDRAILS for the corresponding
instruction to the model, but this module is the actual guarantee, not the
prompt.

Admins get no payroll-detail tools at all here (same boundary as the rest of
the app: an Admin manages accounts, not payroll data) -- they still get
search_payroll_guidance, which is policy text, not application data.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    User, Role, Department, Employee, Cycle, Submission, SubmissionStatus,
    SubmissionRow, Exception as ExceptionModel, ExceptionStatus,
    CorrectionQuery, QueryAnswer,
)
from app.issue_presentation import present_issue
from app import rag

_DENIED_ADMIN = (
    "Department and submission detail isn't available through this assistant "
    "for your role -- that's reviewed by the Payroll Specialist."
)


# ---------------------------------------------------------------------------
# Scope resolution -- the actual permission enforcement. Every tool below
# goes through one of these before touching payroll data.
# ---------------------------------------------------------------------------

def _current_cycle(db: Session) -> Cycle | None:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


def _current_submission_for(db: Session, department_id: int, cycle_id: int) -> Submission | None:
    return db.query(Submission).filter(
        Submission.department_id == department_id, Submission.cycle_id == cycle_id,
        Submission.is_current == True,  # noqa: E712
    ).first()


def _resolve_department(db: Session, user: User, department_name: str | None,
                         ctx: dict | None = None) -> tuple[Department | None, str | None]:
    """Returns (department, error_message). A Submitter always gets their own
    department, regardless of what name is passed -- it is never looked up
    by the given name for that role. A Specialist may name any department
    (case-insensitive, partial match allowed). Falls back to the department
    the user is currently looking at (ctx) if no name was given."""
    if user.role == Role.admin:
        return None, _DENIED_ADMIN
    if user.role == Role.submitter:
        return user.department, None

    name = (department_name or "").strip()
    if not name and ctx:
        name = ctx.get("department") or ""
    if not name:
        return None, "Which department did you mean? Please name one."

    dept = db.query(Department).filter(Department.name.ilike(name)).first()
    if not dept:
        dept = db.query(Department).filter(Department.name.ilike(f"%{name}%")).first()
    if not dept:
        return None, f"No department found matching '{department_name}'."
    return dept, None


def _resolve_submission(db: Session, user: User, department_name: str | None = None,
                         submission_id: int | None = None,
                         ctx: dict | None = None) -> tuple[Submission | None, str | None]:
    """Returns (submission, error_message). Ownership is re-checked here even
    when a submission_id is supplied directly -- a Submitter can never load a
    submission_id belonging to another department just by naming its id."""
    if user.role == Role.admin:
        return None, _DENIED_ADMIN

    if submission_id:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            return None, f"No submission found with id {submission_id}."
        if user.role == Role.submitter and sub.department_id != user.department_id:
            # Never followed -- fall through to the submitter's own current
            # submission instead of silently failing, same convention as
            # build_context().
            pass
        else:
            return sub, None

    dept, err = _resolve_department(db, user, department_name, ctx)
    if err:
        return None, err
    cycle = _current_cycle(db)
    if not cycle:
        return None, "No current payroll cycle is configured."
    sub = _current_submission_for(db, dept.id, cycle.id)
    if not sub:
        return None, f"{dept.name} has no submission yet for the current cycle."
    return sub, None


def _exception_dict(db: Session, e: ExceptionModel, row: SubmissionRow | None) -> dict:
    presentation = present_issue(
        field=e.field, source=e.source.value, issue_text=e.issue_text,
        submitted_value=e.submitted_value, usual_value=e.usual_value,
        ai_explanation=e.ai_explanation, existing_recommended_action=e.recommended_action,
        staff_id=row.staff_id if row else None, full_name=row.full_name if row else None,
    )
    out = {
        "exception_id": e.id,
        "row_label": e.row_label,
        "issue_type": presentation["issue_type"],
        "problem": presentation["problem"],
        "recommended_action": presentation["recommended_action"],
        "status": e.status.value,
        "staff_id": row.staff_id if row else None,
        "employee_name": row.full_name if row else None,
        "submitted_value": e.submitted_value,
        "usual_value": e.usual_value,
    }
    if e.status == ExceptionStatus.query_answered:
        ans = db.query(QueryAnswer).filter(QueryAnswer.exception_id == e.id).order_by(
            QueryAnswer.id.desc()
        ).first()
        if ans:
            out["submitter_answer"] = ans.answer_type
            out["submitter_answer_note"] = ans.note
    return out


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def get_cycle_summary(db: Session, user: User, **_kwargs) -> dict:
    """Current cycle progress. Full department-level breakdown is
    Specialist/Admin only; a Submitter gets the cycle label/cut-off plus a
    note pointing them at their own department."""
    cycle = _current_cycle(db)
    if not cycle:
        return {"error": "No current payroll cycle is configured."}
    out = {"cycle_label": cycle.label, "cutoff_date": cycle.cutoff_date}

    if user.role == Role.submitter:
        out["note"] = (
            "Department-by-department totals for the whole cycle are visible to the "
            "Payroll Specialist. Ask about your own department's submission instead."
        )
        return out
    if user.role == Role.admin:
        return out

    total_departments = db.query(Department).count()
    subs = db.query(Submission).filter(
        Submission.cycle_id == cycle.id, Submission.is_current == True  # noqa: E712
    ).all()
    submitted = [s for s in subs if s.status != SubmissionStatus.not_submitted]
    approved = [s for s in subs if s.status == SubmissionStatus.approved]
    sub_ids = [s.id for s in subs]
    exceptions = (
        db.query(ExceptionModel).filter(ExceptionModel.submission_id.in_(sub_ids)).all()
        if sub_ids else []
    )
    unresolved = sum(1 for e in exceptions if e.status in (ExceptionStatus.open, ExceptionStatus.query_open))
    out.update({
        "total_departments": total_departments,
        "submitted_count": len(submitted),
        "outstanding_count": total_departments - len(submitted),
        "mapped_count": len(submitted),
        "validated_count": len(submitted),
        "unresolved_exception_count": unresolved,
        "self_fixed_count": sum(s.self_fixed_count or 0 for s in subs),
        "approved_count": len(approved),
        "export_ready_department_count": len(approved),
        "export_ready_row_count": sum(s.row_count or 0 for s in approved),
    })
    return out


def get_department_statuses(db: Session, user: User, **_kwargs) -> dict:
    """Every department's status this cycle -- Specialist/Admin only (a
    Submitter only ever has one department to look at; point them at
    get_department_details instead)."""
    if user.role == Role.admin:
        return {"error": _DENIED_ADMIN}
    if user.role == Role.submitter:
        return {"error": "You can only see your own department -- use get_department_details instead."}

    cycle = _current_cycle(db)
    if not cycle:
        return {"error": "No current payroll cycle is configured."}
    subs = db.query(Submission).filter(
        Submission.cycle_id == cycle.id, Submission.is_current == True  # noqa: E712
    ).all()
    open_exceptions = (
        db.query(ExceptionModel)
        .join(Submission, ExceptionModel.submission_id == Submission.id)
        .filter(Submission.cycle_id == cycle.id, Submission.is_current == True)  # noqa: E712
        .filter(ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]))
        .all()
    )
    departments = []
    for s in subs:
        exc_count = sum(1 for e in open_exceptions if e.submission_id == s.id)
        exc_high = sum(1 for e in open_exceptions if e.submission_id == s.id and e.severity.value == "high")
        departments.append({
            "department": s.department.name,
            "status": s.status.value,
            "row_count": s.row_count,
            "open_exception_count": exc_count,
            "high_severity_count": exc_high,
            "last_activity": s.last_activity,
        })
    departments.sort(key=lambda d: -d["open_exception_count"])
    return {"cycle_label": cycle.label, "departments": departments}


def get_department_details(db: Session, user: User, department_name: str | None = None,
                            ctx: dict | None = None, **_kwargs) -> dict:
    """One department's current standing this cycle: status, row/issue
    counts by type, query state, approval/export readiness. A Submitter
    always gets their own department here regardless of what name is
    passed."""
    dept, err = _resolve_department(db, user, department_name, ctx)
    if err:
        return {"error": err}
    cycle = _current_cycle(db)
    if not cycle:
        return {"error": "No current payroll cycle is configured."}
    sub = _current_submission_for(db, dept.id, cycle.id)
    if not sub:
        return {"department": dept.name, "status": "not_submitted", "note": "No submission yet this cycle."}

    exceptions = db.query(ExceptionModel).filter(ExceptionModel.submission_id == sub.id).all()
    row_ids = [e.row_id for e in exceptions if e.row_id]
    rows_by_id = {r.id: r for r in db.query(SubmissionRow).filter(SubmissionRow.id.in_(row_ids)).all()} if row_ids else {}
    open_ones = [e for e in exceptions if e.status in (ExceptionStatus.open, ExceptionStatus.query_open)]
    by_type: dict[str, int] = {}
    for e in open_ones:
        row = rows_by_id.get(e.row_id)
        p = present_issue(
            field=e.field, source=e.source.value, issue_text=e.issue_text,
            submitted_value=e.submitted_value, usual_value=e.usual_value,
            ai_explanation=e.ai_explanation, existing_recommended_action=e.recommended_action,
            staff_id=row.staff_id if row else None, full_name=row.full_name if row else None,
        )
        by_type[p["issue_type"]] = by_type.get(p["issue_type"], 0) + 1

    latest_query = db.query(CorrectionQuery).filter(
        CorrectionQuery.submission_id == sub.id
    ).order_by(CorrectionQuery.id.desc()).first()

    return {
        "department": dept.name,
        "submission_id": sub.id,
        "status": sub.status.value,
        "row_count": sub.row_count,
        "open_issue_count": len(open_ones),
        "issue_types": by_type,
        "last_activity": sub.last_activity,
        "query_sent": latest_query is not None and latest_query.status.value in ("sent",),
        "query_subject": latest_query.subject if latest_query else None,
        "query_sent_at": latest_query.sent_at.isoformat() if latest_query and latest_query.sent_at else None,
        "approved": sub.status == SubmissionStatus.approved,
        "approved_at": sub.approved_at.isoformat() if sub.approved_at else None,
        "export_ready": sub.status == SubmissionStatus.approved,
    }


def get_submission_details(db: Session, user: User, department_name: str | None = None,
                            submission_id: int | None = None,
                            ctx: dict | None = None, **_kwargs) -> dict:
    """One submission's record: version, row count, status, dates,
    current/superseded state."""
    sub, err = _resolve_submission(db, user, department_name, submission_id, ctx)
    if err:
        return {"error": err}
    return {
        "submission_id": sub.id,
        "department": sub.department.name,
        "version": sub.version,
        "is_current": sub.is_current,
        "status": sub.status.value,
        "row_count": sub.row_count,
        "self_fixed_count": sub.self_fixed_count,
        "filename": sub.filename,
        "submitted_by": sub.submitted_by,
        "uploaded_at": sub.uploaded_at.isoformat() if sub.uploaded_at else None,
        "approved_at": sub.approved_at.isoformat() if sub.approved_at else None,
        "approved_by": sub.approved_by,
        "superseded_at": sub.superseded_at.isoformat() if sub.superseded_at else None,
        "last_activity": sub.last_activity,
    }


def get_submission_exceptions(db: Session, user: User, department_name: str | None = None,
                               submission_id: int | None = None, status_filter: str | None = None,
                               ctx: dict | None = None, **_kwargs) -> dict:
    """All exceptions on one submission, optionally filtered by status
    ('open', 'query_open', 'query_answered', 'accepted', 'rejected')."""
    sub, err = _resolve_submission(db, user, department_name, submission_id, ctx)
    if err:
        return {"error": err}
    q = db.query(ExceptionModel).filter(ExceptionModel.submission_id == sub.id)
    if status_filter:
        q = q.filter(ExceptionModel.status == status_filter)
    exceptions = q.order_by(ExceptionModel.id).limit(30).all()
    row_ids = [e.row_id for e in exceptions if e.row_id]
    rows_by_id = {r.id: r for r in db.query(SubmissionRow).filter(SubmissionRow.id.in_(row_ids)).all()} if row_ids else {}
    return {
        "department": sub.department.name,
        "submission_id": sub.id,
        "exceptions": [_exception_dict(db, e, rows_by_id.get(e.row_id)) for e in exceptions],
    }


def get_exception_details(db: Session, user: User, exception_id: int, **_kwargs) -> dict:
    """One exception in full, including the employee master record it was
    checked against, where authorised."""
    exc = db.query(ExceptionModel).filter(ExceptionModel.id == exception_id).first()
    if not exc:
        return {"error": f"No exception found with id {exception_id}."}
    owning_submission = db.query(Submission).filter(Submission.id == exc.submission_id).first()
    if user.role == Role.admin:
        return {"error": _DENIED_ADMIN}
    if user.role == Role.submitter and (
        not owning_submission or owning_submission.department_id != user.department_id
    ):
        return {"error": "That exception isn't in your department."}

    row = db.query(SubmissionRow).filter(SubmissionRow.id == exc.row_id).first() if exc.row_id else None
    out = _exception_dict(db, exc, row)
    out["department"] = owning_submission.department.name if owning_submission else None
    out["submission_id"] = exc.submission_id

    if row and row.staff_id:
        employee = db.query(Employee).filter(Employee.staff_id == row.staff_id).first()
        if employee and (user.role == Role.specialist or employee.department_id == user.department_id):
            out["employee"] = {
                "staff_id": employee.staff_id,
                "full_name": employee.full_name,
                "status": employee.status.value,
                "exited_date": employee.exited_date,
                "avg_overtime_hours": employee.avg_overtime_hours,
            }
            out["current_payroll_row"] = {
                "overtime_hours": row.overtime_hours,
                "basic_pay": row.basic_pay,
                "allowances": row.allowances,
            }
    return out


def get_correction_query_details(db: Session, user: User, department_name: str | None = None,
                                  submission_id: int | None = None,
                                  ctx: dict | None = None, **_kwargs) -> dict:
    """Whether a correction query has been sent for a submission, and which
    queried issues are still unanswered vs already answered (with the
    submitter's actual answer, where available)."""
    sub, err = _resolve_submission(db, user, department_name, submission_id, ctx)
    if err:
        return {"error": err}

    query = db.query(CorrectionQuery).filter(
        CorrectionQuery.submission_id == sub.id
    ).order_by(CorrectionQuery.id.desc()).first()
    if not query:
        return {"department": sub.department.name, "query_sent": False}

    queried_ids = query.exception_ids or []
    exceptions = db.query(ExceptionModel).filter(ExceptionModel.id.in_(queried_ids)).all() if queried_ids else []
    unanswered, answered = [], []
    for e in exceptions:
        if e.status == ExceptionStatus.query_open:
            unanswered.append({"row_label": e.row_label, "issue_text": e.issue_text})
        else:
            ans = db.query(QueryAnswer).filter(QueryAnswer.exception_id == e.id).order_by(
                QueryAnswer.id.desc()
            ).first()
            answered.append({
                "row_label": e.row_label,
                "issue_text": e.issue_text,
                "answer": ans.answer_type if ans else e.status.value,
                "answer_note": ans.note if ans else None,
            })

    return {
        "department": sub.department.name,
        "query_sent": query.status.value == "sent",
        "sent_at": query.sent_at.isoformat() if query.sent_at else None,
        "subject": query.subject,
        "queried_issue_count": len(queried_ids),
        "unanswered": unanswered,
        "answered": answered,
    }


def get_employee_details(db: Session, user: User, staff_id: str, **_kwargs) -> dict:
    """Employee master record, if the requester is authorised to see it."""
    if user.role == Role.admin:
        return {"error": _DENIED_ADMIN}
    employee = db.query(Employee).filter(Employee.staff_id == staff_id).first()
    if not employee:
        return {"error": f"No employee found with Staff ID '{staff_id}'."}
    if user.role == Role.submitter and employee.department_id != user.department_id:
        return {"error": "That employee isn't in your department."}
    return {
        "staff_id": employee.staff_id,
        "full_name": employee.full_name,
        "department": employee.department.name if employee.department else None,
        "status": employee.status.value,
        "grade": employee.grade,
        "basic_pay": employee.basic_pay,
        "allowances": employee.allowances,
        "avg_overtime_hours": employee.avg_overtime_hours,
        "exited_date": employee.exited_date,
    }


def get_export_readiness(db: Session, user: User, **_kwargs) -> dict:
    """Which departments are approved and ready to export -- Specialist/Admin
    only, matching the Query & Export screen's own access."""
    if user.role != Role.specialist:
        return {"error": "Export readiness is only available to the Payroll Specialist."}
    cycle = _current_cycle(db)
    if not cycle:
        return {"error": "No current payroll cycle is configured."}
    subs = db.query(Submission).filter(
        Submission.cycle_id == cycle.id, Submission.is_current == True  # noqa: E712
    ).all()
    items = []
    for s in subs:
        if s.status == SubmissionStatus.not_submitted:
            continue
        if s.status == SubmissionStatus.approved:
            state = "APPROVED"
        elif s.status == SubmissionStatus.query_sent:
            state = "QUERY OPEN"
        else:
            open_count = db.query(ExceptionModel).filter(
                ExceptionModel.submission_id == s.id,
                ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]),
            ).count()
            state = f"{open_count} EXCEPTIONS"
        items.append({"department": s.department.name, "row_count": s.row_count, "state": state})
    approved = [s for s in subs if s.status == SubmissionStatus.approved]
    return {
        "cycle_label": cycle.label,
        "ready_department_count": len(approved),
        "ready_row_count": sum(s.row_count or 0 for s in approved),
        "departments": items,
    }


def search_payroll_guidance(db: Session, user: User, query: str, **_kwargs) -> dict:
    """Searches the payroll policy/procedure knowledge base. Use this for
    questions about POLICY and PROCESS (e.g. what should happen, what the
    rules are) -- never for live operational facts like current counts or
    statuses, which come from the other tools instead."""
    chunks = rag.retrieve(query, k=4)
    return {
        "results": [
            {"topic": c["doc_title"], "section": c["heading"], "text": c["text"]}
            for c in chunks
        ]
    }


TOOLS = {
    "get_cycle_summary": get_cycle_summary,
    "get_department_statuses": get_department_statuses,
    "get_department_details": get_department_details,
    "get_submission_details": get_submission_details,
    "get_submission_exceptions": get_submission_exceptions,
    "get_exception_details": get_exception_details,
    "get_correction_query_details": get_correction_query_details,
    "get_employee_details": get_employee_details,
    "get_export_readiness": get_export_readiness,
    "search_payroll_guidance": search_payroll_guidance,
}


def call_tool(name: str, args: dict, db: Session, user: User, ctx: dict | None = None) -> dict:
    """Dispatches one tool call. Never raises -- a bad/malformed call from
    the model comes back as {"error": ...} so the model can adjust and try
    again instead of the whole request failing."""
    func = TOOLS.get(name)
    if not func:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return func(db=db, user=user, ctx=ctx, **(args or {}))
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception:
        return {"error": f"Could not complete {name} right now."}


# ---------------------------------------------------------------------------
# Anthropic tool schemas -- the *only* thing the model sees about these
# functions. Descriptions steer the model toward the right tool; the actual
# permission enforcement happens in the functions above regardless of what
# the model asks for.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "get_cycle_summary",
        "description": (
            "Overall progress for the current payroll cycle: cut-off date, how many "
            "departments have submitted/are outstanding, unresolved exception count, "
            "approvals and export-ready counts. Use for 'are we nearly done', 'how many "
            "departments have submitted', progress-overview questions. Department-level "
            "totals are only returned for a Specialist/Admin."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_department_statuses",
        "description": (
            "The status of every department this cycle (submitted/needs review/query "
            "sent/approved/not submitted), with issue counts. Specialist/Admin only -- "
            "use for 'who hasn't submitted', 'which department looks most problematic', "
            "'what should I look at first'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_department_details",
        "description": (
            "One department's current standing: status, row/issue counts by type, "
            "whether a correction query has been sent, approval/export state. Omit "
            "department_name to mean 'the one currently open on screen'. A Submitter "
            "always gets their own department regardless of the name given."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "department_name": {"type": "string", "description": "Department name, e.g. 'Operations'. Optional."},
            },
        },
    },
    {
        "name": "get_submission_details",
        "description": (
            "One submission's record: version, row count, status, upload/approval "
            "dates, current-vs-superseded state. Provide either department_name or "
            "submission_id; omit both to mean the one currently open on screen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "department_name": {"type": "string"},
                "submission_id": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_submission_exceptions",
        "description": (
            "The list of validation issues on one submission -- issue type, row, "
            "Staff ID, employee name, submitted vs usual value, problem, recommended "
            "action. Optionally filter by status: 'open', 'query_open' (queried, "
            "awaiting reply), 'query_answered', 'accepted', 'rejected'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "department_name": {"type": "string"},
                "submission_id": {"type": "integer"},
                "status_filter": {"type": "string"},
            },
        },
    },
    {
        "name": "get_exception_details",
        "description": (
            "Full detail on one specific exception by id, including the employee "
            "master record it was checked against where authorised."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"exception_id": {"type": "integer"}},
            "required": ["exception_id"],
        },
    },
    {
        "name": "get_correction_query_details",
        "description": (
            "Whether a correction query has been sent to a department, and which "
            "queried issues are still unanswered vs already answered -- including the "
            "submitter's actual answer text where available. Use for 'has X replied "
            "yet', 'what was X asked to correct', 'what is holding X up'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "department_name": {"type": "string"},
                "submission_id": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_employee_details",
        "description": "One employee's master record (status, grade, pay, average overtime), if authorised.",
        "input_schema": {
            "type": "object",
            "properties": {"staff_id": {"type": "string"}},
            "required": ["staff_id"],
        },
    },
    {
        "name": "get_export_readiness",
        "description": (
            "Which departments are approved and ready to export this cycle, and which "
            "aren't yet and why. Specialist only."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_payroll_guidance",
        "description": (
            "Searches payroll POLICY and PROCEDURE documentation (submission policy, "
            "employee master data rules, overtime guidance, correction/resubmission "
            "procedure, exited-employee guidance, data quality standards, role "
            "responsibilities, FAQ). Use for what-should-happen / what's-the-process "
            "questions -- never for live counts or statuses, which come from the other "
            "tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to search for."}},
            "required": ["query"],
        },
    },
]
