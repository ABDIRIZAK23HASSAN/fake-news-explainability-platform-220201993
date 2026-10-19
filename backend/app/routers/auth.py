"""Authentication endpoints (FR-1 / 8.1)."""
import logging
import smtplib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import PasswordResetToken, RevokedToken, User, UserSetting
from ..schemas import ForgotIn, LoginIn, RegisterIn, ResetIn
from ..security import (create_access_token, hash_password, hash_reset_token, new_reset_token,
                        validate_password_strength, verify_password)
from ..services.logging_service import client_ip, log_event

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("app")

# very small in-memory brute-force guard: 5 failures / 10 min per (email, ip)
_FAILS: dict[tuple, deque] = defaultdict(deque)
MAX_FAILS, WINDOW = 5, 600


def user_payload(u: User) -> dict:
    return {"id": u.user_id, "first_name": u.first_name, "last_name": u.last_name, "email": u.email,
            "role": u.role, "is_active": u.is_active, "profile_image": u.profile_image,
            "registration_date": u.registration_date.isoformat() + "Z",
            "last_login": u.last_login.isoformat() + "Z" if u.last_login else None}


def _token_response(u: User) -> dict:
    token, _, exp = create_access_token(u.user_id, u.role)
    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat(), "user": user_payload(u)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    err = validate_password_strength(body.password)
    if err:
        raise HTTPException(422, err)
    if db.query(User).filter(func.lower(User.email) == body.email.lower()).first():
        raise HTTPException(409, "Email already exists")
    u = User(first_name=body.first_name, last_name=body.last_name, email=body.email.lower(),
             password=hash_password(body.password), role="User", last_login=datetime.utcnow())
    u.settings = UserSetting()
    db.add(u); db.commit(); db.refresh(u)
    log_event(db, "Register", f"New user registered: {u.email}", u.user_id, request)
    return _token_response(u)


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = (body.email.lower(), client_ip(request))
    q, now = _FAILS[key], time.time()
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= MAX_FAILS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Please try again in a few minutes.")
    u = db.query(User).filter(func.lower(User.email) == body.email.lower()).first()
    if u is None or not verify_password(body.password, u.password):
        q.append(now)
        log_event(db, "Unauthorized", f"Failed login for {body.email}", u.user_id if u else None, request)
        raise HTTPException(401, "Incorrect email or password")
    if not u.is_active:
        raise HTTPException(403, "This account has been deactivated. Please contact an administrator.")
    q.clear()
    u.last_login = datetime.utcnow()
    db.commit()
    log_event(db, "Login", f"{u.email} logged in", u.user_id, request)
    return _token_response(u)


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exp = datetime.utcfromtimestamp(request.state.token_exp)
    db.merge(RevokedToken(jti=request.state.jti, expires_at=exp))
    db.query(RevokedToken).filter(RevokedToken.expires_at < datetime.utcnow()).delete()   # housekeeping
    db.commit()
    log_event(db, "Logout", f"{user.email} logged out", user.user_id, request)
    return {"message": "Logged out successfully"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


def _send_reset_email(to: str, link: str) -> None:
    if not settings.smtp_host:
        log.warning("PASSWORD RESET LINK for %s (SMTP not configured): %s", to, link)
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Reset your password", settings.smtp_from, to
    msg.set_content(f"Use this link to reset your password (valid {settings.reset_token_minutes} minutes):\n{link}")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    generic = {"message": "If an account with that email exists, a password reset link has been sent."}
    u = db.query(User).filter(func.lower(User.email) == body.email.lower(), User.is_active.is_(True)).first()
    if not u:
        return generic                                  # do not reveal which emails exist
    raw, hashed = new_reset_token()
    db.add(PasswordResetToken(user_id=u.user_id, token_hash=hashed,
                              expires_at=datetime.utcnow() + timedelta(minutes=settings.reset_token_minutes)))
    db.commit()
    link = f"{settings.frontend_url}/reset-password?token={raw}"
    try:
        _send_reset_email(u.email, link)
    except Exception as e:                              # noqa: BLE001
        log_event(db, "Error", f"Could not send reset e-mail to {u.email}: {e}", u.user_id, request)
    log_event(db, "Admin", f"Password reset requested for {u.email}", u.user_id, request)
    if settings.expose_reset_token:                     # demo only, off by default
        generic["dev_reset_token"] = raw
    return generic


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    err = validate_password_strength(body.new_password)
    if err:
        raise HTTPException(422, err)
    rec = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == hash_reset_token(body.token)).first()
    if not rec or rec.used or rec.expires_at < datetime.utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    u = db.get(User, rec.user_id)
    u.password = hash_password(body.new_password)
    rec.used = True
    db.commit()
    log_event(db, "Admin", f"Password reset completed for {u.email}", u.user_id, request)
    return {"message": "Password has been reset. You can now log in."}
