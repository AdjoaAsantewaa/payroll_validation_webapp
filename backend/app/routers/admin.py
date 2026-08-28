import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import User, Department, Role
from app.schemas import DepartmentOut, CreateSubmitterRequest, SubmitterOut
from app.security import require_admin, hash_password
from app.email import send_credentials_email
from app.audit import log_action

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.query(Department).order_by(Department.name).all()


@router.get("/submitters", response_model=list[SubmitterOut])
def list_submitters(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    submitters = (
        db.query(User)
        .options(joinedload(User.department))
        .filter(User.role == Role.submitter)
        .order_by(User.name)
        .all()
    )
    return [
        SubmitterOut(
            id=u.id, name=u.name, email=u.email,
            department=u.department.name if u.department else None,
            department_id=u.department_id,
        )
        for u in submitters
    ]


@router.post("/submitters", response_model=SubmitterOut, status_code=201)
def create_submitter(
    payload: CreateSubmitterRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    department = db.query(Department).filter(Department.id == payload.department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    name = payload.name.strip()
    initials = "".join(part[0] for part in name.split() if part)[:3].upper() or "NA"
    password = secrets.token_urlsafe(9)

    user = User(
        email=email, name=name, initials=initials, role=Role.submitter,
        password_hash=hash_password(password), department_id=department.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    send_credentials_email(email, name, password)
    log_action(db, admin, "submitter_created", entity="user", entity_id=user.id,
               detail=f"Created submitter {email} in {department.name}")

    return SubmitterOut(
        id=user.id, name=user.name, email=user.email,
        department=department.name, department_id=department.id,
    )
