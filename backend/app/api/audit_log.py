from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.db import get_db
from app.models import AuditEvent, Role, User
from app.schemas.users import AuditEventOut, Page

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=Page[AuditEventOut])
def list_audit_events(
    action: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
) -> Page[AuditEventOut]:
    stmt = select(AuditEvent)
    count = select(func.count()).select_from(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
        count = count.where(AuditEvent.action == action)
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).all()
    return Page[AuditEventOut](
        items=[AuditEventOut.model_validate(e) for e in rows],
        total=db.scalar(count) or 0,
        limit=limit,
        offset=offset,
    )
