import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.users import Page, UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(prefix="/api/v1/users", tags=["users"])
admin_only = require_roles(Role.ADMIN)


@router.get("", response_model=Page[UserOut])
def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> Page[UserOut]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(select(User).order_by(User.created_at).limit(limit).offset(offset)).all()
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> User:
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        role=body.role.value,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "email_taken", "A user with this email already exists.",
                       {"email": "Already in use."}) from None
    audit.record(db, action="user.create", entity_type="user", entity_id=user.id, actor=admin,
                 details={"role": user.role})
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "not_found", "User not found.")

    # An admin may not demote or deactivate themselves. Because only admins can
    # change roles, this guarantees at least one active admin always remains.
    if user.id == admin.id:
        if body.role is not None and body.role != Role.ADMIN:
            raise ApiError(400, "cannot_change_own_role", "You cannot change your own role.")
        if body.is_active is False:
            raise ApiError(400, "cannot_deactivate_self", "You cannot deactivate yourself.")

    if body.full_name is not None and body.full_name != user.full_name:
        user.full_name = body.full_name
        audit.record(db, action="user.update", entity_type="user", entity_id=user.id, actor=admin,
                     details={"field": "full_name"})
    if body.role is not None and body.role.value != user.role:
        audit.record(db, action="user.role_change", entity_type="user", entity_id=user.id,
                     actor=admin, details={"from": user.role, "to": body.role.value})
        user.role = body.role.value
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        audit.record(db, action="user.activate" if body.is_active else "user.deactivate",
                     entity_type="user", entity_id=user.id, actor=admin)
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        audit.record(db, action="user.password_reset", entity_type="user", entity_id=user.id,
                     actor=admin)

    db.commit()
    return user
