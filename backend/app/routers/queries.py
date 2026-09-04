import datetime

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Department, Cycle, Submission, Exception as ExceptionModel, ExceptionStatus,
    CorrectionQuery, QueryStatus, SubmissionStatus, User, Role,
)
from app.security import require_specialist
from app.audit import log_action
from app import ai_service
from app.validation_service import _exc_to_dict

router = APIRouter(tags=["queries"])


def _current_cycle(db: Session) -> Cycle:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


@router.post("/queries/draft")
def draft_query(payload: dict = Body(...), db: Session = Depends(get_db),
                 user: User = Depends(require_specialist)):
    department_id = payload.get("department_id")
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    cycle = _current_cycle(db)
    submission = db.query(Submission).filter(
        Submission.department_id == department_id, Submission.cycle_id == cycle.id,
        Submission.is_current == True,  # noqa: E712
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="No submission for this department this cycle")

    exception_ids = payload.get("exception_ids")
    q = db.query(ExceptionModel).filter(ExceptionModel.submission_id == submission.id)
    q = q.filter(ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]))
    if exception_ids:
        q = q.filter(ExceptionModel.id.in_(exception_ids))
    exceptions = q.all()
    if not exceptions:
        raise HTTPException(status_code=400, detail="No open exceptions to query")

    exc_dicts = [_exc_to_dict(e) for e in exceptions]
    # Only pass a cut-off date through if it's genuinely still ahead of us --
    # a past date would produce a draft that tells the department to reply
    # by a deadline that's already gone. cycle.cutoff_date is stored as
    # "YYYY-MM-DD"; a malformed value is treated as "no usable deadline"
    # rather than erroring the draft.
    future_cutoff = None
    try:
        if cycle.cutoff_date and datetime.datetime.strptime(cycle.cutoff_date, "%Y-%m-%d").date() >= datetime.date.today():
            future_cutoff = cycle.cutoff_date
    except ValueError:
        pass
    draft = ai_service.draft_correction(dept.name, cycle.label, exc_dicts, future_cutoff or "")

    return {
        "to_emails": _department_recipient(db, department_id, dept),
        "subject": draft["subject"],
        "body": draft["body"],
        "exception_ids": [e.id for e in exceptions],
    }


def _department_recipient(db: Session, department_id: int, dept: Department) -> str:
    """The correction query recipient is the department's actual Submitter
    account(s) -- never a made-up address. Falls back to the department's
    configured contact_email only if no submitter account exists yet for
    that department; if neither is available, returns an empty string so
    the specialist has to fill it in themselves rather than being handed a
    guessed address."""
    submitters = (
        db.query(User)
        .filter(User.role == Role.submitter, User.department_id == department_id)
        .order_by(User.name)
        .all()
    )
    if submitters:
        return ", ".join(u.email for u in submitters)
    return dept.contact_email or ""


@router.post("/queries/send")
def send_query(payload: dict = Body(...), db: Session = Depends(get_db),
               user: User = Depends(require_specialist)):
    department_id = payload.get("department_id")
    to_emails = payload.get("to_emails")
    subject = payload.get("subject")
    body = payload.get("body")
    exception_ids = payload.get("exception_ids") or []

    if not (department_id and to_emails and subject and body and exception_ids):
        raise HTTPException(status_code=400, detail="Missing required fields")

    cycle = _current_cycle(db)
    submission = db.query(Submission).filter(
        Submission.department_id == department_id, Submission.cycle_id == cycle.id,
        Submission.is_current == True,  # noqa: E712
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="No submission for this department this cycle")

    q = CorrectionQuery(
        department_id=department_id, cycle_id=cycle.id, submission_id=submission.id,
        to_emails=to_emails, subject=subject, body=body, status=QueryStatus.sent,
        sent_at=datetime.datetime.utcnow(), exception_ids=exception_ids,
    )
    db.add(q)

    exceptions = db.query(ExceptionModel).filter(ExceptionModel.id.in_(exception_ids)).all()
    for e in exceptions:
        e.status = ExceptionStatus.query_open

    submission.status = SubmissionStatus.query_sent
    submission.last_activity = "Query sent " + datetime.datetime.utcnow().strftime("%d %b")
    db.commit()

    log_action(db, user, "query_sent", "department", department_id,
               f"Sent correction request ({len(exception_ids)} items) to {to_emails}")

    return {"ok": True, "query_id": q.id}


@router.post("/submissions/{submission_id}/approve")
def approve_submission(submission_id: int, db: Session = Depends(get_db),
                        user: User = Depends(require_specialist)):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if (submission.last_activity or "").startswith("Blocked"):
        raise HTTPException(
            status_code=400,
            detail="This submission was blocked before validation ran (mapping conflict or the "
                   "file doesn't look like payroll data) and has never actually been checked. "
                   "It cannot be approved until the submitter fixes and re-uploads.",
        )

    blocking = db.query(ExceptionModel).filter(
        ExceptionModel.submission_id == submission_id,
        ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]),
    ).count()
    if blocking:
        raise HTTPException(status_code=400,
                             detail=f"{blocking} unresolved exception(s) must be accepted, "
                                    f"rejected, or answered before approval")

    submission.status = SubmissionStatus.approved
    submission.approved_at = datetime.datetime.utcnow()
    submission.approved_by = user.name
    submission.last_activity = "Approved " + datetime.datetime.utcnow().strftime("%d %b")
    db.commit()

    log_action(db, user, "approved", "submission", submission.id,
               f"Approved {submission.department.name} submission ({submission.row_count} rows)")

    return {"ok": True, "status": submission.status.value}
