"""Prediction history, explanations and report export (FR-8, FR-11, 7.1.8)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Keyword, PredictionHistory, User
from ..schemas import DeletePredictionsIn
from ..services.analysis import explanation_for, full_result, summary
from ..services.report import prediction_pdf, predictions_csv

router = APIRouter(tags=["predictions"])

SORTABLE = {"date": PredictionHistory.prediction_date, "confidence": PredictionHistory.confidence_score,
            "result": PredictionHistory.prediction_result, "processing_time": PredictionHistory.processing_time}


def _own(db: Session, user: User, pid: int) -> PredictionHistory:
    p = db.query(PredictionHistory).filter_by(prediction_id=pid, user_id=user.user_id).first()
    if not p:                                    # 404 (not 403) so other users' ids are not revealed
        raise HTTPException(404, "Prediction not found")
    return p


@router.get("/api/predictions/history")
def history(search: str | None = None, result: str | None = Query(None, pattern="^(Fake|Real)$"),
            sort: str = "date", order: str = Query("desc", pattern="^(asc|desc)$"),
            date_from: datetime | None = None, date_to: datetime | None = None,
            page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(PredictionHistory).filter(PredictionHistory.user_id == user.user_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(PredictionHistory.submitted_title.ilike(like), PredictionHistory.submitted_content.ilike(like),
                         exists().where(Keyword.prediction_id == PredictionHistory.prediction_id, Keyword.keyword.ilike(like))))
    if result:
        q = q.filter(PredictionHistory.prediction_result == result)
    if date_from:
        q = q.filter(PredictionHistory.prediction_date >= date_from)
    if date_to:
        q = q.filter(PredictionHistory.prediction_date <= date_to)
    total = q.count()
    col = SORTABLE.get(sort, PredictionHistory.prediction_date)
    q = q.order_by(col.asc() if order == "asc" else col.desc(), PredictionHistory.prediction_id.desc())
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [summary(p) for p in items], "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


@router.get("/api/predictions/export")
def export_many(ids: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CSV of the given prediction ids (comma-separated) or of the whole history."""
    q = db.query(PredictionHistory).filter(PredictionHistory.user_id == user.user_id)
    if ids:
        try:
            q = q.filter(PredictionHistory.prediction_id.in_([int(i) for i in ids.split(",") if i.strip()]))
        except ValueError:
            raise HTTPException(422, "ids must be a comma-separated list of numbers")
    preds = q.order_by(PredictionHistory.prediction_date.desc()).all()
    if not preds:
        raise HTTPException(404, "There are no predictions to export")
    return Response(predictions_csv(preds), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="prediction_history.csv"'})


@router.post("/api/predictions/delete")
def delete_many(body: DeletePredictionsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(PredictionHistory).filter(PredictionHistory.user_id == user.user_id,
                                              PredictionHistory.prediction_id.in_(body.ids)).all()
    for r in rows:
        db.delete(r)
    db.commit()
    return {"deleted": len(rows)}


@router.get("/api/predictions/{prediction_id}")
def get_prediction(prediction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return full_result(_own(db, user, prediction_id))


@router.delete("/api/predictions/{prediction_id}")
def delete_prediction(prediction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, prediction_id)); db.commit()
    return {"message": "Prediction deleted"}


@router.get("/api/predictions/{prediction_id}/export")
def export_one(prediction_id: int, format: str = Query("pdf", pattern="^(pdf|csv)$"),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, prediction_id)
    if format == "pdf":
        return Response(prediction_pdf(p), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="analysis_{p.prediction_id}.pdf"'})
    return Response(predictions_csv([p]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="analysis_{p.prediction_id}.csv"'})


@router.get("/api/explanations/{prediction_id}")
def explanations(prediction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, prediction_id)
    return {"prediction_id": p.prediction_id, "prediction": p.prediction_result, "confidence": p.confidence_score,
            **explanation_for(p)}
