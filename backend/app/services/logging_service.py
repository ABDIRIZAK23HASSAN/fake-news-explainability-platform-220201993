"""Logging & Monitoring Service (spec 8.13). Writes to the SystemLogs table."""
import logging

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import SystemLog

logger = logging.getLogger("app")


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def log_event(db: Session, event_type: str, description: str, user_id: int | None = None,
              request: Request | None = None) -> None:
    """event_type: Login, Logout, Register, Prediction, Training, Import, Activation,
    Error, Unauthorized, Admin."""
    try:
        db.add(SystemLog(user_id=user_id, event_type=event_type, description=description[:2000],
                         ip_address=client_ip(request)))
        db.commit()
    except Exception:           # logging must never break the request
        db.rollback()
        logger.exception("could not write system log")
