import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Body
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Submission, SubmissionStatus, Cycle, ColumnMapping, User, Role,
    Exception as ExceptionModel, ExceptionStatus, SubmissionRow, CorrectionQuery,
)
from app.security import require_submitter, get_current_user
from app.audit import log_action
from app import parser, ai_service
from app.validation_service import validate_and_persist, _exc_to_dict

router = APIRouter(prefix="/submissions", tags=["submissions"])


def _current_cycle(db: Session) -> Cycle:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


def _get_current_submission(db: Session, department_id: int, cycle_id: int) -> Submission | None:
    """The one and only row that should ever be treated as "the" submission
    for this department+cycle. Never use a plain (department_id, cycle_id)
    filter without is_current elsewhere — that was the root cause of the
    specialist dashboard counting exceptions from superseded submissions on
    top of the current one (see Submission model docstring)."""
    return db.query(Submission).filter(
        Submission.department_id == department_id,
        Submission.cycle_id == cycle_id,
        Submission.is_current == True,  # noqa: E712
    ).first()


def _create_new_version(db: Session, department_id: int, cycle_id: int) -> Submission:
    """Supersede the current version (if any) and insert a fresh one, one
    version number higher. Race-safe: the partial unique index on
    (department_id, cycle_id) WHERE is_current guarantees the database
    itself rejects a second concurrent "current" row, even if two uploads
    for a brand-new (never-submitted) department land at the same instant
    and both see no existing row. Callers must catch IntegrityError."""
    current = _get_current_submission(db, department_id, cycle_id)
    next_version = 1
    carried_self_fixed = 0
    if current:
        next_version = current.version + 1
        carried_self_fixed = current.self_fixed_count or 0
        current.is_current = False
        current.superseded_at = datetime.datetime.utcnow()
        db.flush()

    new_sub = Submission(
        department_id=department_id, cycle_id=cycle_id, version=next_version,
        is_current=True, status=SubmissionStatus.not_submitted, row_count=0,
        self_fixed_count=carried_self_fixed,
    )
    db.add(new_sub)
    db.flush()
    return new_sub


@router.get("/status")
def submission_status(db: Session = Depends(get_db), user: User = Depends(require_submitter)):
    cycle = _current_cycle(db)
    sub = _get_current_submission(db, user.department_id, cycle.id)

    open_questions = []
    if sub:
        exceptions = db.query(ExceptionModel).filter(
            ExceptionModel.submission_id == sub.id,
            ExceptionModel.status == ExceptionStatus.query_open,
        ).all()
        open_questions = [_exc_to_dict(e) for e in exceptions]

    # Superseded versions of THIS cycle's submission (resubmission history).
    previous_versions = (
        db.query(Submission)
        .filter(
            Submission.department_id == user.department_id,
            Submission.cycle_id == cycle.id,
            Submission.is_current == False,  # noqa: E712
        )
        .order_by(Submission.version.desc())
        .all()
    )

    # Other (fully separate) cycles this department has submitted in.
    past = (
        db.query(Submission)
        .join(Cycle, Submission.cycle_id == Cycle.id)
        .filter(
            Submission.department_id == user.department_id,
            Submission.is_current == True,  # noqa: E712
            Cycle.is_current == False,  # noqa: E712
        )
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
            "submission_id": p.id, "cycle": p.cycle.label, "rows": p.row_count, "outcome": outcome,
        })

    return {
        "cycle": {"label": cycle.label, "cutoff_date": cycle.cutoff_date},
        "department": user.department.name,
        "submission": {
            "id": sub.id if sub else None,
            "version": sub.version if sub else None,
            "status": sub.status.value if sub else "not_submitted",
            "row_count": sub.row_count if sub else 0,
            "self_fixed_count": sub.self_fixed_count if sub else 0,
            "uploaded_at": sub.uploaded_at.isoformat() if sub and sub.uploaded_at else None,
            "filename": sub.filename if sub else None,
        },
        "open_questions": open_questions,
        "previous_versions": [
            {
                "submission_id": v.id, "version": v.version, "rows": v.row_count,
                "filename": v.filename,
                "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
                "superseded_at": v.superseded_at.isoformat() if v.superseded_at else None,
            }
            for v in previous_versions
        ],
        "earlier_cycles": earlier_cycles,
    }


@router.get("/{submission_id}")
def get_submission_detail(submission_id: int, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """Backs the "View file" / historical submission view for both roles.
    Submitters may only view submissions from their own department;
    specialists may view any. Original file bytes are not retained (only
    parsed row data), so this returns the structured record rather than a
    downloadable file — see README for why."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if user.role == Role.submitter and sub.department_id != user.department_id:
        raise HTTPException(status_code=403, detail="Not your department")

    exceptions = db.query(ExceptionModel).filter(
        ExceptionModel.submission_id == sub.id).order_by(ExceptionModel.id).all()
    queries = db.query(CorrectionQuery).filter(
        CorrectionQuery.submission_id == sub.id).order_by(CorrectionQuery.id).all()

    return {
        "id": sub.id,
        "department": sub.department.name,
        "department_id": sub.department_id,
        "cycle": sub.cycle.label,
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
        "exceptions": [_exc_to_dict(e) for e in exceptions],
        "queries": [
            {
                "subject": q.subject, "status": q.status.value,
                "sent_at": q.sent_at.isoformat() if q.sent_at else None,
                "to_emails": q.to_emails,
            }
            for q in queries
        ],
        "file_retained": False,
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

    # Deterministic gates, in order -- both enforced here (backend, not just
    # the mapping-edit UI) so neither can be bypassed by calling the API
    # directly. A conflict is checked first: if a field is ambiguous, the
    # payroll-shape check below can't trust it either way.
    conflicts = parser.find_mapping_conflicts(mapping)
    missing_fields = [] if conflicts else parser.missing_required_fields(mapping)
    rows = parser.apply_mapping(df, mapping)  # defensively drops conflicting fields either way

    cycle = _current_cycle(db)
    previous = _get_current_submission(db, user.department_id, cycle.id)
    previous_exc_count = (
        db.query(ExceptionModel).filter(ExceptionModel.submission_id == previous.id).count()
        if previous else 0
    )

    try:
        sub = _create_new_version(db, user.department_id, cycle.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another upload for this department just completed. Please refresh and try again.",
        )

    unmapped = [c for c, f in mapping.items() if not f]

    if conflicts or missing_fields:
        # Rows are still persisted (raw + whatever fields aren't ambiguous)
        # so /remap can fix the mapping without forcing a re-upload -- but
        # no rule/AI validation runs, so this can't generate a wall of
        # per-row exceptions off a file that isn't payroll data in the
        # first place.
        result = validate_and_persist(db, sub, rows, user.department_id, user.department.name,
                                       skip_validation=True)
        sub.filename = file.filename
        sub.uploaded_at = datetime.datetime.utcnow()
        sub.submitted_by = user.name
        block_reason = "mapping_conflict" if conflicts else "not_payroll_shaped"
        message = (
            "Two columns are mapped to the same field. Resolve the conflict before this file "
            "can be validated."
            if conflicts else
            "This file does not appear to contain the required payroll fields. Please review "
            "the file or column mapping."
        )
        sub.last_activity = f"Blocked — {'mapping conflict' if conflicts else 'not payroll data'}"
        db.commit()
        log_action(db, user, "upload_blocked", "submission", sub.id,
                   f"{block_reason}: {file.filename} for {user.department.name}")
        return {
            "submission_id": sub.id, "version": sub.version, "filename": file.filename,
            "row_count": len(rows), "mapping": mapping, "mapping_source": mapping_source,
            "unmapped_columns": unmapped, "exceptions": [], "self_fixed_count": sub.self_fixed_count,
            "blocked": True, "block_reason": block_reason, "message": message,
            "mapping_conflicts": conflicts, "missing_fields": missing_fields,
        }

    result = validate_and_persist(db, sub, rows, user.department_id, user.department.name)

    sub.filename = file.filename
    sub.uploaded_at = datetime.datetime.utcnow()
    sub.submitted_by = user.name
    sub.last_activity = "Uploaded just now" if previous is None else "Resubmitted just now"
    if previous:
        fixed = max(0, previous_exc_count - len(result["exceptions"]))
        sub.self_fixed_count = (sub.self_fixed_count or 0) + fixed
    db.commit()

    log_action(db, user, "upload", "submission", sub.id,
               f"Uploaded {file.filename} ({len(rows)} rows) for {user.department.name} "
               f"(version {sub.version})")

    return {
        "submission_id": sub.id,
        "version": sub.version,
        "filename": file.filename,
        "row_count": len(rows),
        "mapping": mapping,
        "mapping_source": mapping_source,
        "unmapped_columns": unmapped,
        "exceptions": result["exceptions"],
        "self_fixed_count": sub.self_fixed_count,
        "blocked": False,
    }


@router.post("/{submission_id}/remap")
def remap_submission(
    submission_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_submitter),
):
    """Re-interprets the SAME uploaded file with a corrected column mapping.
    This is not a new file, so unlike /upload it edits the current version
    in place rather than creating a new one."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub or sub.department_id != user.department_id:
        raise HTTPException(status_code=404, detail="Submission not found")
    if not sub.is_current:
        raise HTTPException(status_code=400, detail="This submission has been superseded by a newer upload.")

    mapping = payload.get("mapping")
    if not mapping:
        raise HTTPException(status_code=400, detail="mapping is required")

    existing_rows = db.query(SubmissionRow).filter(
        SubmissionRow.submission_id == submission_id).order_by(SubmissionRow.row_index).all()
    if not existing_rows:
        raise HTTPException(status_code=400, detail="No rows to remap; upload a file first.")

    conflicts = parser.find_mapping_conflicts(mapping)
    missing_fields = [] if conflicts else parser.missing_required_fields(mapping)
    # Same defensive rule as parser.apply_mapping: a field involved in a
    # conflict is left unmapped here rather than letting whichever source
    # column is processed last silently win.
    safe_mapping = {
        source_col: (None if target_field in conflicts else target_field)
        for source_col, target_field in mapping.items()
    }

    rows = []
    for r in existing_rows:
        raw = r.raw or {}
        canonical = {"staff_id": None, "full_name": None, "overtime_hours": None,
                     "basic_pay": None, "allowances": None}
        for source_col, target_field in safe_mapping.items():
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

    if conflicts or missing_fields:
        result = validate_and_persist(db, sub, rows, user.department_id, user.department.name,
                                       skip_validation=True)
        block_reason = "mapping_conflict" if conflicts else "not_payroll_shaped"
        message = (
            "Two columns are mapped to the same field. Resolve the conflict before this file "
            "can be validated."
            if conflicts else
            "This file does not appear to contain the required payroll fields. Please review "
            "the file or column mapping."
        )
        sub.last_activity = f"Blocked — {'mapping conflict' if conflicts else 'not payroll data'}"
        db.commit()
        log_action(db, user, "remap_blocked", "submission", sub.id, block_reason)
        return {
            "submission_id": sub.id, "row_count": len(rows), "mapping": mapping,
            "exceptions": [], "blocked": True, "block_reason": block_reason, "message": message,
            "mapping_conflicts": conflicts, "missing_fields": missing_fields,
        }

    result = validate_and_persist(db, sub, rows, user.department_id, user.department.name)
    db.commit()
    log_action(db, user, "remap", "submission", sub.id, "Updated column mapping")

    return {
        "submission_id": sub.id, "row_count": len(rows), "mapping": mapping,
        "exceptions": result["exceptions"], "blocked": False,
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
