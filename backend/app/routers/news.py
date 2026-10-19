"""News analysis endpoints (FR-3, FR-4, FR-5, FR-6, FR-7)."""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import NewsArticle, PredictionHistory, User
from ..schemas import AnalyzeIn
from ..services import app_settings
from ..services.analysis import analyze_article, full_result, similar_payload
from ..services.files import FileFormatError, extract_text
from ..services.logging_service import log_event
from ..services.prediction import NoActiveModelError, TextTooShortError

router = APIRouter(prefix="/api/news", tags=["news"])


def _run(db: Session, user: User, request: Request, title: str | None, text: str) -> dict:
    try:
        p = analyze_article(db, user.user_id, title, text.strip())
    except NoActiveModelError as e:
        log_event(db, "Error", f"Prediction failed: {e}", user.user_id, request)
        raise HTTPException(503, f"Prediction failed: {e}")
    except TextTooShortError as e:
        raise HTTPException(422, str(e))
    except Exception as e:                                   # noqa: BLE001
        log_event(db, "Error", f"Prediction failed: {type(e).__name__}: {e}", user.user_id, request)
        raise HTTPException(500, "Prediction failed due to an internal error. The incident was logged for the administrator.")
    log_event(db, "Prediction", f"Prediction #{p.prediction_id}: {p.prediction_result} ({p.confidence_score:.3f})", user.user_id, request)
    out = full_result(p)
    out["inference_time"] = getattr(p, "_inference_time", None)
    out["message"] = "Prediction completed"
    return out


@router.post("/analyze")
def analyze(body: AnalyzeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _run(db, user, request, body.title, body.text)


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    max_bytes = int(app_settings.get(db, "max_upload_mb")) * 1024 * 1024
    allowed = {t.strip().lower() for t in app_settings.get(db, "supported_file_types").split(",") if t.strip()}
    data = await file.read(max_bytes + 1)
    try:
        text, title = extract_text(file.filename or "", data, allowed, max_bytes)
    except FileFormatError as e:
        raise HTTPException(415 if "format" in str(e).lower() else 422, str(e))
    return _run(db, user, request, title, text)


@router.get("/similar/{prediction_id}")
def similar(prediction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(PredictionHistory).filter_by(prediction_id=prediction_id, user_id=user.user_id).first()
    if not p:
        raise HTTPException(404, "Prediction not found")
    return {"prediction_id": prediction_id, "similar": similar_payload(p)}


@router.get("/articles/{news_id}")
def open_article(news_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(NewsArticle, news_id)
    if not a:
        raise HTTPException(404, "Article not found")
    return {"news_id": a.news_id, "title": a.title, "content": a.content, "subject": a.subject,
            "label": a.label, "publication_date": a.publication_date}
