from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.users import LoginRequest, TokenResponse, UserOut
from app.services import audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Always run the hash check so timing does not reveal whether the email exists.
    password_ok = verify_password(body.password, user.password_hash if user else None)

    if user is None or not password_ok or not user.is_active:
        audit.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            details={"reason": "inactive" if (user and password_ok) else "bad_credentials"},
        )
        db.commit()
        # Same message for every failure: do not reveal which part was wrong.
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")

    user.last_login_at = datetime.now(UTC)
    audit.record(db, action="auth.login", entity_type="user", entity_id=user.id, actor=user)
    db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=get_settings().access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
