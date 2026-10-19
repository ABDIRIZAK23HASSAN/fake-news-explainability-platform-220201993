"""Profile, preferences and personal dashboard (FR-1, 7.1.2, 7.1.9, 8.2)."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import PredictionHistory, User, UserSetting
from ..schemas import ChangePasswordIn, DeleteAccountIn, ProfileUpdate, SettingsIn
from ..security import hash_password, validate_password_strength, verify_password
from ..services.analysis import summary
from ..services.logging_service import log_event
from .auth import user_payload

router = APIRouter(prefix="/api/users", tags=["users"])
AVATAR_DIR = Path(settings.storage_dir) / "avatars"
_MAGIC = {b"\x89PNG\r\n\x1a\n": ".png", b"\xff\xd8\xff": ".jpg"}


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    return user_payload(user)


@router.put("/profile")
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.email and body.email.lower() != user.email:
        if db.query(User).filter(func.lower(User.email) == body.email.lower(), User.user_id != user.user_id).first():
            raise HTTPException(409, "Email already exists")
        user.email = body.email.lower()
    if body.first_name: user.first_name = body.first_name.strip()
    if body.last_name: user.last_name = body.last_name.strip()
    db.commit()
    return user_payload(user)


@router.put("/password")
def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password):
        raise HTTPException(400, "Incorrect password")
    err = validate_password_strength(body.new_password)
    if err:
        raise HTTPException(422, err)
    user.password = hash_password(body.new_password)
    db.commit()
    log_event(db, "Admin", f"{user.email} changed password", user.user_id, request)
    return {"message": "Password changed successfully"}


@router.post("/profile-image")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "Image is too large (maximum 2 MB)")
    ext = next((e for magic, e in _MAGIC.items() if data.startswith(magic)), None)   # real type, not the filename
    if ext is None:
        raise HTTPException(415, "Invalid file format. Please upload a PNG or JPEG image.")
    name = f"{uuid.uuid4().hex}{ext}"
    (AVATAR_DIR / name).write_bytes(data)
    if user.profile_image:
        (AVATAR_DIR / Path(user.profile_image).name).unlink(missing_ok=True)
    user.profile_image = f"/media/avatars/{name}"
    db.commit()
    return user_payload(user)


def _settings_payload(s: UserSetting) -> dict:
    return {"theme": s.theme, "language": s.language, "email_notification": s.email_notification,
            "default_export_format": s.default_export_format}


@router.get("/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.settings is None:
        user.settings = UserSetting(); db.commit()
    return _settings_payload(user.settings)


@router.put("/settings")
def update_settings(body: SettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.settings is None:
        user.settings = UserSetting()
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user.settings, k, v)
    db.commit()
    return _settings_payload(user.settings)


@router.delete("/profile")
def delete_account(body: DeleteAccountIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password):
        raise HTTPException(400, "Incorrect password")
    if user.role == "Administrator" and db.query(User).filter(User.role == "Administrator", User.is_active.is_(True)).count() <= 1:
        raise HTTPException(400, "You are the only administrator and cannot delete your own account.")
    email = user.email
    db.delete(user); db.commit()
    log_event(db, "Admin", f"Account deleted by owner: {email}", None, request)
    return {"message": "Account deleted"}


@router.get("/dashboard")
def my_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(PredictionHistory).filter(PredictionHistory.user_id == user.user_id)
    total = q.count()
    by_label = dict(db.query(PredictionHistory.prediction_result, func.count())
                    .filter(PredictionHistory.user_id == user.user_id).group_by(PredictionHistory.prediction_result).all())
    avg = db.query(func.avg(PredictionHistory.confidence_score)).filter(PredictionHistory.user_id == user.user_id).scalar()
    recent = q.order_by(PredictionHistory.prediction_date.desc()).limit(5).all()
    return {"welcome": f"Welcome back, {user.first_name}", "total_predictions": total,
            "fake_detected": by_label.get("Fake", 0), "real_detected": by_label.get("Real", 0),
            "average_confidence": float(avg) if avg is not None else None,
            "recent_predictions": [summary(p) for p in recent],
            "recent_uploaded_news": [summary(p) for p in recent if p.submitted_title][:5],
            "recently_analyzed_articles": [{"prediction_id": p.prediction_id, "title": p.submitted_title or p.submitted_content[:60],
                                            "result": p.prediction_result, "date": p.prediction_date.isoformat() + "Z"} for p in recent]}
