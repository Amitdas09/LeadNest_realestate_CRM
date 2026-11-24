import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.errors import ApiError
from app.models import Lead, User


def is_manager(user: User) -> bool:
    return user.role in ("admin", "manager")


def scope_leads(stmt: Select, user: User) -> Select:
    """Agents see leads assigned to them plus unassigned ones; managers/admins see all."""
    if is_manager(user):
        return stmt
    return stmt.where(or_(Lead.owner_id == user.id, Lead.owner_id.is_(None)))


def get_lead(db: Session, lead_id: uuid.UUID, user: User) -> Lead:
    lead = db.scalar(scope_leads(select(Lead).where(Lead.id == lead_id), user))
    if lead is None:
        raise ApiError(404, "not_found", "Lead not found.")
    return lead


def users_by_id(db: Session) -> dict[uuid.UUID, User]:
    return {u.id: u for u in db.scalars(select(User))}
