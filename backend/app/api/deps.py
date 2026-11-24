import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.models import Role, User
from app.services import audit

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise ApiError(401, "not_authenticated", "Please sign in.")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise ApiError(401, "invalid_token", "Your session is invalid or has expired.") from None
    user = db.get(User, user_id)
    # Checked on every request so deactivating a user takes effect immediately.
    if user is None or not user.is_active:
        raise ApiError(401, "invalid_token", "Your session is invalid or has expired.")
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed = {r.value for r in roles}

    def dependency(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.role not in allowed:
            audit.record(
                db,
                action="access.denied",
                entity_type="route",
                entity_id=f"{request.method} {request.url.path}",
                actor=user,
                details={"role": user.role},
            )
            db.commit()
            raise ApiError(403, "forbidden", "You do not have permission to do this.")
        return user

    return dependency
