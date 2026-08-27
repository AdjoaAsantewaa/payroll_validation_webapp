from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Cycle, Submission, SubmissionStatus, Exception as ExceptionModel, ExceptionStatus,
    Department,
)
from app.security import require_specialist

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _current_cycle(db: Session) -> Cycle:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


@router.get("")
def get_dashboard(db: Session = Depends(get_db), user=Depends(require_specialist)):
    cycle = _current_cycle(db)
    # is_current is load-bearing: without it, a department with a superseded
    # (resubmitted-over) submission would have its old exceptions/self-fixed
    # counts summed on top of the current version's — this was the root
    # cause of the specialist dashboard showing far more exceptions than the
    # submitter's own current row count.
    # joinedload: without it, every s.department / e.submission.department
    # access below is a separate lazy-loaded round trip -- fine on local
    # SQLite (sub-millisecond), but a real, avoidable cost against a remote
    # Postgres connection (Supabase). One JOIN instead of up to ~N+1 queries.
    submissions = db.query(Submission).options(joinedload(Submission.department)).filter(
        Submission.cycle_id == cycle.id, Submission.is_current == True  # noqa: E712
    ).all()

    total_depts = db.query(Department).count()
    submitted = [s for s in submissions if s.status != SubmissionStatus.not_submitted]
    approved = [s for s in submissions if s.status == SubmissionStatus.approved]
    self_fixed_total = sum(s.self_fixed_count or 0 for s in submissions)

    open_exceptions = (
        db.query(ExceptionModel)
        .join(Submission, ExceptionModel.submission_id == Submission.id)
        .filter(Submission.cycle_id == cycle.id, Submission.is_current == True)  # noqa: E712
        .filter(ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]))
        .all()
    )

    export_rows = sum(s.row_count or 0 for s in approved)

    by_dept = {}
    for s in submissions:
        by_dept.setdefault(s.department.name, 0)
    for e in open_exceptions:
        dept_name = e.submission.department.name
        by_dept[dept_name] = by_dept.get(dept_name, 0) + 1
    chart = sorted(
        [{"department": k, "count": v} for k, v in by_dept.items()],
        key=lambda x: -x["count"],
    )[:6]

    rows = []
    for s in sorted(submissions, key=lambda s: (
        0 if s.status == SubmissionStatus.needs_review else
        1 if s.status == SubmissionStatus.query_sent else
        2 if s.status == SubmissionStatus.not_submitted else 3
    )):
        exc_count = len([e for e in open_exceptions if e.submission_id == s.id])
        exc_high = len([e for e in open_exceptions if e.submission_id == s.id and e.severity.value == "high"])
        rows.append({
            "submission_id": s.id,
            "department": s.department.name,
            "department_id": s.department_id,
            "status": s.status.value,
            "rows": s.row_count,
            "exceptions": exc_count,
            "exceptions_high": exc_high,
            "last_activity": s.last_activity,
        })

    return {
        "cycle": {"id": cycle.id, "label": cycle.label, "cutoff_date": cycle.cutoff_date},
        "pipeline": {
            "submitted": len(submitted),
            "mapped": len(submitted),
            "validated": len(submitted),
            "resolve": len(open_exceptions),
            "approve": len(approved),
            "export": export_rows,
            "total_departments": total_depts,
        },
        "stats": {
            "needs_you": len(open_exceptions),
            "submitted_of_total": f"{len(submitted)} / {total_depts}",
            "not_in_yet": total_depts - len(submitted),
            "self_fixed": self_fixed_total,
            "approved": len(approved),
        },
        "chart": chart,
        "departments": rows,
    }
