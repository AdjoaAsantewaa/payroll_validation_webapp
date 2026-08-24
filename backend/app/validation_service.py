"""Orchestrates rule + AI validation for a set of parsed rows and persists the
result (SubmissionRow + Exception records) against a Submission."""
from sqlalchemy.orm import Session

from app.models import (
    Submission, SubmissionRow, Exception as ExceptionModel, ExceptionSeverity,
    ExceptionSource, ExceptionStatus, Employee, EmployeeStatus,
)
from app import rules_engine, ai_service


def _severity(s: str) -> ExceptionSeverity:
    return ExceptionSeverity(s)


def _source(s: str) -> ExceptionSource:
    return ExceptionSource(s)


def validate_and_persist(db: Session, submission: Submission, rows: list[dict],
                          department_id: int, department_name: str) -> dict:
    # Clear previous rows/exceptions for a clean re-validation (upload/remap/resubmit)
    db.query(ExceptionModel).filter(ExceptionModel.submission_id == submission.id).delete()
    db.query(SubmissionRow).filter(SubmissionRow.submission_id == submission.id).delete()
    db.flush()

    employees = db.query(Employee).filter(Employee.department_id == department_id).all()
    employees_by_id = {e.staff_id: e for e in employees}

    row_objs = {}
    for row in rows:
        r = SubmissionRow(
            submission_id=submission.id, row_index=row["row_index"],
            staff_id=row.get("staff_id"), full_name=row.get("full_name"),
            overtime_hours=row.get("overtime_hours"), basic_pay=row.get("basic_pay"),
            allowances=row.get("allowances"), raw=row.get("raw") or {},
        )
        db.add(r)
        row_objs[row["row_index"]] = r
    db.flush()

    rule_exceptions = rules_engine.validate_rows(rows, employees_by_id)
    flagged_row_indices = {e["row_index"] for e in rule_exceptions}

    for exc in rule_exceptions:
        db.add(ExceptionModel(
            submission_id=submission.id, row_id=row_objs.get(exc["row_index"]).id
            if row_objs.get(exc["row_index"]) else None,
            row_label=exc["row_label"], field=exc["field"],
            severity=_severity(exc["severity"]), source=_source(exc["source"]),
            issue_text=exc["issue_text"], submitted_value=exc.get("submitted_value"),
            usual_value=exc.get("usual_value"),
        ))

    # AI judgement only on rows that passed every rule check
    total_submitted_pay = 0.0
    for row in rows:
        if row["row_index"] in flagged_row_indices:
            continue
        staff_id = row.get("staff_id")
        employee = employees_by_id.get(staff_id) if staff_id else None
        if employee is None:
            continue
        total_submitted_pay += (row.get("basic_pay") or 0) + (row.get("allowances") or 0)

        candidate = rules_engine.detect_overtime_candidate(row, employee)
        if candidate:
            judged = ai_service.explain_anomaly(candidate, row, employee, department_name)
            db.add(ExceptionModel(
                submission_id=submission.id, row_id=row_objs[row["row_index"]].id,
                row_label=f"Row {row['row_index']}", field="overtime_hours",
                severity=_severity(judged.get("severity", "med")), source=ExceptionSource.ai,
                issue_text=judged.get("explanation", "")[:120],
                submitted_value=str(candidate["submitted_value"]),
                usual_value=f"{candidate['usual_value']:g} avg",
                ai_explanation=judged.get("explanation"),
                recommended_action=judged.get("recommended_action"),
            ))
            continue

        allowance_candidate = rules_engine.detect_allowance_candidate(row, employee)
        if allowance_candidate:
            judged = ai_service.explain_anomaly(allowance_candidate, row, employee, department_name)
            db.add(ExceptionModel(
                submission_id=submission.id, row_id=row_objs[row["row_index"]].id,
                row_label=f"Row {row['row_index']}", field="allowances",
                severity=_severity(judged.get("severity", "med")), source=ExceptionSource.ai,
                issue_text=judged.get("explanation", "")[:120],
                submitted_value=str(allowance_candidate["submitted_value"]),
                usual_value=str(allowance_candidate["usual_value"]),
                ai_explanation=judged.get("explanation"),
                recommended_action=judged.get("recommended_action"),
            ))

    # Department-level wage bill variance (aggregate, not tied to a single row)
    usual_total = sum((e.basic_pay or 0) + (e.allowances or 0) for e in employees)
    submitted_headcount = len({r.get("staff_id") for r in rows if r.get("staff_id")})
    usual_headcount = len(employees)
    variance = rules_engine.detect_wage_bill_variance(
        department_name, total_submitted_pay, usual_total, submitted_headcount, usual_headcount)
    if variance:
        judged = ai_service.explain_anomaly(variance, {"full_name": None, "staff_id": None},
                                             None, department_name)
        db.add(ExceptionModel(
            submission_id=submission.id, row_id=None, row_label="Department total",
            field="wage_bill", severity=_severity(judged.get("severity", "med")),
            source=ExceptionSource.ai, issue_text=judged.get("explanation", "")[:120],
            submitted_value=f"{variance['variance_pct']:g}%", usual_value="0% (no headcount change)",
            ai_explanation=judged.get("explanation"),
            recommended_action=judged.get("recommended_action"),
        ))

    db.flush()
    exceptions = db.query(ExceptionModel).filter(
        ExceptionModel.submission_id == submission.id).all()

    submission.row_count = len(rows)
    submission.status = submission.status.__class__.needs_review

    db.commit()
    db.refresh(submission)

    return {
        "submission_id": submission.id,
        "row_count": len(rows),
        "exceptions": [_exc_to_dict(e) for e in exceptions],
    }


def _exc_to_dict(e: ExceptionModel) -> dict:
    return {
        "id": e.id,
        "row_label": e.row_label,
        "field": e.field,
        "severity": e.severity.value,
        "source": e.source.value,
        "issue_text": e.issue_text,
        "submitted_value": e.submitted_value,
        "usual_value": e.usual_value,
        "ai_explanation": e.ai_explanation,
        "recommended_action": e.recommended_action,
        "status": e.status.value,
        "note": e.note,
    }
