import hashlib
import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Submission, SubmissionStatus, SubmissionRow, Cycle, User, AuditLog
from app.security import require_specialist
from app.audit import log_action

router = APIRouter(tags=["export"])


def _current_cycle(db: Session) -> Cycle:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


@router.get("/export/preview")
def export_preview(db: Session = Depends(get_db), user: User = Depends(require_specialist)):
    cycle = _current_cycle(db)
    submissions = db.query(Submission).filter(Submission.cycle_id == cycle.id).all()
    ready = [s for s in submissions if s.status == SubmissionStatus.approved]
    not_ready = [s for s in submissions if s.status != SubmissionStatus.approved
                 and s.status != SubmissionStatus.not_submitted]

    def to_row(s, state):
        return {"submission_id": s.id, "department": s.department.name,
                "department_id": s.department_id, "rows": s.row_count, "state": state}

    items = [to_row(s, "APPROVED") for s in ready]
    for s in not_ready:
        state = "QUERY OPEN" if s.status == SubmissionStatus.query_sent else f"{_open_exc_count(db, s.id)} EXCEPTIONS"
        items.append(to_row(s, state))

    return {
        "cycle": cycle.label,
        "ready_department_count": len(ready),
        "ready_row_count": sum(s.row_count or 0 for s in ready),
        "items": items,
    }


def _open_exc_count(db: Session, submission_id: int) -> int:
    from app.models import Exception as ExceptionModel, ExceptionStatus
    return db.query(ExceptionModel).filter(
        ExceptionModel.submission_id == submission_id,
        ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]),
    ).count()


@router.post("/export")
def export_clean_data(payload: dict = Body(...), db: Session = Depends(get_db),
                       user: User = Depends(require_specialist)):
    submission_ids = payload.get("submission_ids") or []
    file_format = payload.get("file_format", "csv")
    if not submission_ids:
        raise HTTPException(status_code=400, detail="submission_ids is required")

    submissions = db.query(Submission).filter(Submission.id.in_(submission_ids)).all()
    not_approved = [s for s in submissions if s.status != SubmissionStatus.approved]
    if not_approved:
        names = ", ".join(s.department.name for s in not_approved)
        raise HTTPException(status_code=400,
                             detail=f"Only approved submissions can be exported. Not approved: {names}")

    records = []
    for s in submissions:
        rows = db.query(SubmissionRow).filter(
            SubmissionRow.submission_id == s.id).order_by(SubmissionRow.row_index).all()
        for r in rows:
            records.append({
                "department": s.department.name, "staff_id": r.staff_id,
                "full_name": r.full_name, "overtime_hours": r.overtime_hours,
                "basic_pay": r.basic_pay, "allowances": r.allowances,
            })

    df = pd.DataFrame(records)
    if file_format == "excel":
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        content_type = "text/csv"
        ext = "csv"

    file_bytes = buf.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    cycle = _current_cycle(db)
    filename = f"payroll_export_{cycle.label.replace(' ', '_').lower()}.{ext}"

    log_action(db, user, "export", "cycle", cycle.id,
               f"Exported {len(records)} rows across {len(submissions)} department(s), "
               f"file={filename}, sha256={file_hash}")

    return StreamingResponse(
        io.BytesIO(file_bytes), media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "X-File-Hash": file_hash, "X-Row-Count": str(len(records))},
    )


@router.get("/audit")
def get_audit_log(limit: int = 100, db: Session = Depends(get_db),
                   user: User = Depends(require_specialist)):
    entries = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [{
        "id": e.id, "actor": e.actor_name or e.actor_email, "action": e.action,
        "entity": e.entity, "entity_id": e.entity_id, "detail": e.detail,
        "timestamp": e.timestamp.isoformat(),
    } for e in entries]
