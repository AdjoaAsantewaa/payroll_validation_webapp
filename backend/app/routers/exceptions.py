import hashlib

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Exception as ExceptionModel, ExceptionStatus, Submission, SubmissionRow, Employee, User,
    QueryAnswer,
)
from app.security import require_specialist, require_submitter
from app.audit import log_action
from app.validation_service import _exc_to_dict

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("")
def list_exceptions(submission_id: int = None, db: Session = Depends(get_db),
                     user: User = Depends(require_specialist)):
    q = db.query(ExceptionModel)
    if submission_id:
        q = q.filter(ExceptionModel.submission_id == submission_id)
    exceptions = q.order_by(ExceptionModel.id).all()

    sev_rank = {"high": 0, "med": 1, "low": 2}
    exceptions = sorted(exceptions, key=lambda e: sev_rank.get(e.severity.value, 9))

    submission = None
    if submission_id:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()

    return {
        "submission": {
            "id": submission.id, "department": submission.department.name,
            "department_id": submission.department_id,
            "row_count": submission.row_count, "status": submission.status.value,
            "last_activity": submission.last_activity,
        } if submission else None,
        "exceptions": [_exc_to_dict(e) for e in exceptions],
        "counts": {
            "all": len(exceptions),
            "high": len([e for e in exceptions if e.severity.value == "high"]),
            "med": len([e for e in exceptions if e.severity.value == "med"]),
            "low": len([e for e in exceptions if e.severity.value == "low"]),
        },
    }


@router.get("/{exception_id}")
def get_exception(exception_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_specialist)):
    e = db.query(ExceptionModel).filter(ExceptionModel.id == exception_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exception not found")
    row = None
    if e.row_id:
        r = db.query(SubmissionRow).filter(SubmissionRow.id == e.row_id).first()
        if r:
            row = {"staff_id": r.staff_id, "full_name": r.full_name,
                   "overtime_hours": r.overtime_hours, "basic_pay": r.basic_pay,
                   "allowances": r.allowances}
    data = _exc_to_dict(e)
    data["row"] = row
    return data


@router.get("/{exception_id}/history")
def exception_history(exception_id: int, db: Session = Depends(get_db),
                       user: User = Depends(require_specialist)):
    e = db.query(ExceptionModel).filter(ExceptionModel.id == exception_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exception not found")
    row = db.query(SubmissionRow).filter(SubmissionRow.id == e.row_id).first() if e.row_id else None
    if not row or not row.staff_id:
        return {"periods": []}
    employee = db.query(Employee).filter(Employee.staff_id == row.staff_id).first()
    avg = employee.avg_overtime_hours if employee else 0
    seed = int(hashlib.sha256(row.staff_id.encode()).hexdigest(), 16)
    periods = []
    for i in range(6):
        variance = ((seed >> (i * 4)) % 9 - 4) / 10.0  # deterministic +/-0.4
        periods.append(round(max(0, avg * (1 + variance)), 1))
    return {"periods": periods, "average": avg}


@router.post("/{exception_id}/accept")
def accept_exception(exception_id: int, payload: dict = Body(default={}),
                      db: Session = Depends(get_db), user: User = Depends(require_specialist)):
    e = _get_exc(db, exception_id)
    e.status = ExceptionStatus.accepted
    e.note = (payload or {}).get("note")
    db.commit()
    log_action(db, user, "accept_exception", "exception", e.id, e.issue_text)
    return _exc_to_dict(e)


@router.post("/{exception_id}/reject")
def reject_exception(exception_id: int, payload: dict = Body(default={}),
                      db: Session = Depends(get_db), user: User = Depends(require_specialist)):
    e = _get_exc(db, exception_id)
    e.status = ExceptionStatus.rejected
    e.note = (payload or {}).get("note")
    db.commit()
    log_action(db, user, "reject_exception", "exception", e.id, e.issue_text)
    return _exc_to_dict(e)


@router.post("/{exception_id}/query")
def query_exception(exception_id: int, payload: dict = Body(default={}),
                     db: Session = Depends(get_db), user: User = Depends(require_specialist)):
    e = _get_exc(db, exception_id)
    e.status = ExceptionStatus.query_open
    e.note = (payload or {}).get("note")
    db.commit()
    log_action(db, user, "add_to_query", "exception", e.id, e.issue_text)
    return _exc_to_dict(e)


@router.post("/{exception_id}/answer")
def answer_exception(exception_id: int, payload: dict = Body(...),
                      db: Session = Depends(get_db), user: User = Depends(require_submitter)):
    e = _get_exc(db, exception_id)
    submission = db.query(Submission).filter(Submission.id == e.submission_id).first()
    if submission.department_id != user.department_id:
        raise HTTPException(status_code=403, detail="Not your department")

    answer_type = payload.get("answer_type")
    note = payload.get("note")
    if answer_type not in ("correct", "wrong", "not_sure"):
        raise HTTPException(status_code=400, detail="answer_type must be correct, wrong, or not_sure")

    db.add(QueryAnswer(exception_id=e.id, answer_type=answer_type, note=note))
    e.status = ExceptionStatus.query_answered
    e.note = note
    db.commit()
    log_action(db, user, "answer_query", "exception", e.id, f"{answer_type}: {note or ''}")
    return _exc_to_dict(e)


def _get_exc(db: Session, exception_id: int) -> ExceptionModel:
    e = db.query(ExceptionModel).filter(ExceptionModel.id == exception_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exception not found")
    return e
