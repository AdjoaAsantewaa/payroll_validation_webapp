from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log_action(db: Session, user: User, action: str, entity: str = None,
                entity_id: str = None, detail: str = None):
    entry = AuditLog(
        actor_email=user.email,
        actor_name=user.name,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail,
    )
    db.add(entry)
    db.commit()
