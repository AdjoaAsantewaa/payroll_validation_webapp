from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse
from app.security import verify_password, create_access_token, get_current_user
from app.audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user)
    log_action(db, user, "login")
    return LoginResponse(
        access_token=token, role=user.role.value, name=user.name, initials=user.initials,
        email=user.email,
        department=user.department.name if user.department else None,
        department_id=user.department_id,
    )


@router.get("/me", response_model=LoginResponse)
def me(user: User = Depends(get_current_user)):
    from app.security import create_access_token as _mint
    return LoginResponse(
        access_token=_mint(user), role=user.role.value, name=user.name, initials=user.initials,
        email=user.email,
        department=user.department.name if user.department else None,
        department_id=user.department_id,
    )
