import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Submission, SubmissionStatus, Cycle, ColumnMapping, User, Exception as ExceptionModel,
    ExceptionStatus, SubmissionRow,
)
from app.security import require_submitter, get_current_user
from app.audit import log_action
from app import parser, ai_service
from app.validation_service import validate_and_persist, _exc_to_dict

router = APIRouter(prefix="/submissions", tags=["submissions"])


def _current_cycle(db: Session) -> Cycle:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


def _get_or_create_submission(db: Session, department_id: int, cycle_id: int) -> Submission:
    sub = db.query(Submission).filter(
        Submission.department_id == department_id, Submission.cycle_id == cycle_id).first()
    if not sub:
        sub = Submission(department_id=department_id, cycle_id=cycle_id,
                          status=SubmissionStatus.not_submitted, row_count=0)
        db.add(sub)
        db.flush()
    return sub


@router.get("/status")
def submission_status(db: Session = Depends(get_db), user: User = Depends(require_submitter)):
    cycle = _current_cycle(db)
    sub = _get_or_create_submission(db, user.department_id, cycle.id)

    open_questions = []
    if sub.id:
        exceptions = db.query(ExceptionModel).filter(
            ExceptionModel.submission_id == sub.id,
            ExceptionModel.status == ExceptionStatus.query_open,
        ).all()
        open_questions = [_exc_to_dict(e) for e in exceptions]

    past = (
        db.query(Submission)
        .join(Cycle, Submission.cycle_id == Cycle.id)
        .filter(Submission.department_id == user.department_id, Cycle.is_current == False)  # noqa: E712
        .order_by(Cycle.id.desc())
        .all()
    )
    earlier_cycles = []
    for p in past:
        query_count = db.query(ExceptionModel).filter(
            ExceptionModel.submission_id == p.id,
            ExceptionModel.status == ExceptionStatus.query_answered).count()
        if p.status == SubmissionStatus.approved:
            if p.self_fixed_count:
                outcome = f"Approved · {p.self_fixed_count} self-fixed"
            elif query_count:
                outcome = f"Approved · {query_count} query"
            else:
                outcome = "Approved · clean first time"
        else:
            outcome = f"{p.status.value.replace('_', ' ').title()}"
        earlier_cycles.append({
            "cycle": p.cycle.label, "rows": p.row_count, "outcome": outcome,
        })

    return {
        "cycle": {"label": cycle.label, "cutoff_date": cycle.cutoff_date},
        "department": user.department.name,
        "submission": {
            "id": sub.id,
            "status": sub.status.value,
            "row_count": sub.row_count,
            "self_fixed_count": sub.self_fixed_count,
            "uploaded_at": sub.uploaded_at.isoformat() if sub.uploaded_at else None,
            "filename": sub.filename,
        },
        "open_questions": open_questions,
        "earlier_cycles": earlier_cycles,
    }


@router.post("/upload")
async def upload_submission(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_submitter),
):
    content = await file.read()
    try:
        df = parser.read_upload(file.filename, content)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded file has no rows.")

    source_columns = list(df.columns)
    sample_rows = df.head(3).to_dict(orient="records")

    cached = db.query(ColumnMapping).filter(
        ColumnMapping.department_id == user.department_id).first()
    if cached and set(cached.source_columns) == set(source_columns):
        mapping = cached.mapping
        mapping_source = "cached"
    else:
        result = ai_service.map_columns(source_columns, sample_rows)
        mapping = result["mapping"]
        mapping_source = result["source"]
        if cached:
            cached.source_columns = source_columns
            cached.mapping = mapping
        else:
            db.add(ColumnMapping(department_id=user.department_id,
                                  source_columns=source_columns, mapping=mapping))
        db.flush()

    rows = parser.apply_mapping(df, mapping)

    cycle = _current_cycle(db)
    sub = _get_or_create_submission(db, user.department_id, cycle.id)
    previous_exc_count = db.query(ExceptionModel).filter(
        ExceptionModel.submission_id == sub.id).count() if sub.id else 0

    result = validate_and_persist(db, sub, rows, user.department_id, user.department.name)

    sub.filename = file.filename
    sub.uploaded_at = datetime.datetime.utcnow()
    sub.submitted_by = user.name
    sub.last_activity = "Uploaded just now" if previous_exc_count == 0 else "Resubmitted just now"
    if previous_exc_count:
        fixed = max(0, previous_exc_count - len(result["exceptions"]))
        sub.self_fixed_count = (sub.self_fixed_count or 0) + fixed
    db.commit()

    log_action(db, user, "upload", "submission", sub.id,
               f"Uploaded {file.filename} ({len(rows)} rows) for {user.department.name}")

    unmapped = [c for c, f in mapping.items() if not f]
    return {
        "submission_id": sub.id,
        "filename": file.filename,
        "row_count": len(rows),
        "mapping": mapping,
        "mapping_source": mapping_source,
        "unmapped_columns": unmapped,
        "exceptions": result["exceptions"],
        "self_fixed_count": sub.self_fixed_count,
    }


@router.post("/{submission_id}/remap")
def remap_submission(
    submission_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_submitter),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub or sub.department_id != user.department_id:
        raise HTTPException(status_code=404, detail="Submission not found")

    mapping = payload.get("mapping")
    if not mapping:
        raise HTTPException(status_code=400, detail="mapping is required")

    existing_rows = db.query(SubmissionRow).filter(
        SubmissionRow.submission_id == submission_id).order_by(SubmissionRow.row_index).all()
    if not existing_rows:
        raise HTTPException(status_code=400, detail="No rows to remap; upload a file first.")

    rows = []
    for r in existing_rows:
        raw = r.raw or {}
        canonical = {"staff_id": None, "full_name": None, "overtime_hours": None,
                     "basic_pay": None, "allowances": None}
        for source_col, target_field in mapping.items():
            if target_field and source_col in raw:
                canonical[target_field] = raw[source_col]
        rows.append({
            "row_index": r.row_index, "raw": raw,
            "staff_id": parser._clean_staff_id(canonical["staff_id"]),
            "full_name": parser._clean_str(canonical["full_name"]),
            "overtime_hours": parser._to_float(canonical["overtime_hours"]),
            "basic_pay": parser._to_float(canonical["basic_pay"]),
            "allowances": parser._to_float(canonical["allowances"]),
        })

    cached = db.query(ColumnMapping).filter(
        ColumnMapping.department_id == user.department_id).first()
    if cached:
        cached.mapping = mapping
        db.flush()

    result = validate_and_persist(db, sub, rows, user.department_id, user.department.name)
    db.commit()
    log_action(db, user, "remap", "submission", sub.id, "Updated column mapping")

    return {
        "submission_id": sub.id, "row_count": len(rows), "mapping": mapping,
        "exceptions": result["exceptions"],
    }


@router.post("/{submission_id}/submit-anyway")
def submit_anyway(
    submission_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    user: User = Depends(require_submitter),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub or sub.department_id != user.department_id:
        raise HTTPException(status_code=404, detail="Submission not found")
    note = (payload or {}).get("note", "")
    sub.last_activity = "Submitted with note"
    db.commit()
    log_action(db, user, "submit_with_note", "submission", sub.id, note or "(no note)")
    return {"ok": True}
