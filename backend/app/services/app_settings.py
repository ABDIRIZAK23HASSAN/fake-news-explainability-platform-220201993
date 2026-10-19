"""System-wide settings edited by administrators (7.2.8), stored in the app_settings table."""
from sqlalchemy.orm import Session

from ..models import AppSetting

DEFAULTS = {
    "max_upload_mb": "10",
    "supported_file_types": "txt,pdf",
    "keyword_method": "tfidf",          # tfidf | rake
    "active_dataset": "all",            # 'all' or a dataset id used for training
    "theme": "light",
    "keywords_top_n": "10",
}


def get_all(db: Session) -> dict[str, str]:
    stored = {r.key: r.value for r in db.query(AppSetting).all()}
    return {**DEFAULTS, **stored}


def get(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else DEFAULTS[key]


def set_value(db: Session, key: str, value: str) -> None:
    if key not in DEFAULTS:
        raise ValueError(f"Unknown setting '{key}'")
    row = db.get(AppSetting, key)
    if row:
        row.value = str(value)
    else:
        db.add(AppSetting(key=key, value=str(value)))
    db.commit()
