"""Audit helper.

The event is added to the caller's session and committed in the same
transaction as the action it describes: if the audit write fails, the action
is rolled back too.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    actor: User | None = None,
    system: bool = False,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    if actor is not None:
        actor_type = "user"
    elif system:
        actor_type = "system"
    else:
        actor_type = "anonymous"
    event = AuditEvent(
        actor_type=actor_type,
        actor_user_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details or {},
    )
    db.add(event)
    return event
