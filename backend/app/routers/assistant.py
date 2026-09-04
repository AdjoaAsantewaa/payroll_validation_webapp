from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import AssistantChatRequest
from app.security import get_current_user
from app import assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat")
def chat(payload: AssistantChatRequest, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Available to any authenticated role. Role/department scoping for
    context happens inside assistant_service.build_context() based on the
    authenticated `user`, not on anything in `payload` -- see that module's
    docstring. This endpoint has no write path: it only ever returns text."""
    return assistant_service.answer(
        db, user, payload.message, payload.page or "",
        payload.submission_id, payload.exception_id,
    )


@router.get("/prompts")
def prompts(user: User = Depends(get_current_user)):
    return {"prompts": assistant_service.SUGGESTED_PROMPTS.get(user.role.value, [])}
