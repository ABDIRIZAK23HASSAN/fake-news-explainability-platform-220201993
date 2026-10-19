"""FastAPI dependencies: current user + role-based access control (RBAC)."""
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import RevokedToken, User
from .security import decode_token
from .services.logging_service import log_event

bearer = HTTPBearer(auto_error=False)


def get_current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated. Please log in.")
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")
    if db.get(RevokedToken, payload.get("jti")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session ended. Please log in again.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated.")
    request.state.jti, request.state.token_exp = payload["jti"], payload["exp"]
    return user


def require_admin(request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> User:
    # Role is read from the DB, not from the token, so demotions apply immediately.
    if user.role != "Administrator":
        log_event(db, "Unauthorized", f"Non-admin user {user.email} tried {request.method} {request.url.path}",
                  user.user_id, request)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator privileges are required.")
    return user
