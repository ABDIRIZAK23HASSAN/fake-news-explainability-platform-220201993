"""Administrator endpoints - every route requires the Administrator role (RBAC)."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import settings as cfg
from ..database import get_db
from ..deps import require_admin
from ..models import (DatasetImport, KeywordDictionaryEntry, MLModel, NewsArticle, PredictionHistory, SystemLog,
                      TrainingRun, User, UserSetting)
from ..schemas import (AdminCreateUser, AdminResetPasswordIn, AdminUserUpdate, KeywordEntryIn, NewsUpdate,
                       SettingsUpdate, StopwordsIn, SubjectRename, TrainBatchIn, TrainIn)
from ..security import hash_password, validate_password_strength
from ..services import analytics, app_settings, dataset as dsvc, model_mgmt
from ..services.dataset import DatasetValidationError, content_hash
from ..services.keywords import METHODS as KEYWORD_METHODS
from ..services.logging_service import log_event
from ..services.preprocessing import stopwords
from ..services.report import analytics_csv, analytics_pdf
from ..services.similar import index as similarity_index
from ..services.training import ALGORITHMS
from .auth import user_payload

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _page(q, page: int, page_size: int):
    total = q.count()
    return total, q.offset((page - 1) * page_size).limit(page_size).all(), (total + page_size - 1) // page_size


# =========================================================== users (7.2.2 / 8.2)
@router.get("/users")
def list_users(search: str | None = None, role: str | None = None, is_active: bool | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    q = db.query(User)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(User.email.ilike(like), User.first_name.ilike(like), User.last_name.ilike(like)))
    if role: q = q.filter(User.role == role)
    if is_active is not None: q = q.filter(User.is_active.is_(is_active))
    total, rows, pages = _page(q.order_by(User.user_id), page, page_size)
    counts = dict(db.query(PredictionHistory.user_id, func.count()).group_by(PredictionHistory.user_id).all())
    return {"items": [{**user_payload(u), "predictions": counts.get(u.user_id, 0)} for u in rows],
            "total": total, "page": page, "pages": pages}


@router.post("/users", status_code=201)
def create_user(body: AdminCreateUser, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    err = validate_password_strength(body.password)
    if err: raise HTTPException(422, err)
    if db.query(User).filter(func.lower(User.email) == body.email.lower()).first():
        raise HTTPException(409, "Email already exists")
    u = User(first_name=body.first_name, last_name=body.last_name, email=body.email.lower(),
             password=hash_password(body.password), role=body.role); u.settings = UserSetting()
    db.add(u); db.commit(); db.refresh(u)
    log_event(db, "Admin", f"Admin {admin.email} created user {u.email} ({u.role})", admin.user_id, request)
    return user_payload(u)


def _get_user(db: Session, uid: int) -> User:
    u = db.get(User, uid)
    if not u: raise HTTPException(404, "User not found")
    return u


def _would_leave_no_admin(db: Session, u: User) -> bool:
    return u.role == "Administrator" and db.query(User).filter(
        User.role == "Administrator", User.is_active.is_(True), User.user_id != u.user_id).count() == 0


@router.get("/users/{uid}")
def get_user(uid: int, db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    n = db.query(func.count(PredictionHistory.prediction_id)).filter_by(user_id=uid).scalar()
    return {**user_payload(u), "predictions": n}


@router.put("/users/{uid}")
def update_user(uid: int, body: AdminUserUpdate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    data = body.model_dump(exclude_none=True)
    if uid == admin.user_id and (data.get("role", "Administrator") != "Administrator" or data.get("is_active") is False):
        raise HTTPException(400, "You cannot demote or deactivate your own account.")
    if (data.get("role") == "User" or data.get("is_active") is False) and _would_leave_no_admin(db, u):
        raise HTTPException(400, "At least one active administrator must remain.")
    if "email" in data:
        data["email"] = data["email"].lower()
        if db.query(User).filter(func.lower(User.email) == data["email"], User.user_id != uid).first():
            raise HTTPException(409, "Email already exists")
    for k, v in data.items(): setattr(u, k, v)
    db.commit()
    log_event(db, "Admin", f"Admin {admin.email} updated user {u.email}: {sorted(data)}", admin.user_id, request)
    return user_payload(u)


def _set_active(uid: int, activate: bool, request: Request, admin: User, db: Session):
    u = _get_user(db, uid)
    if not activate:
        if uid == admin.user_id: raise HTTPException(400, "You cannot deactivate your own account.")
        if _would_leave_no_admin(db, u): raise HTTPException(400, "At least one active administrator must remain.")
    u.is_active = activate
    db.commit()
    log_event(db, "Admin", f"Admin {admin.email} {'activated' if activate else 'deactivated'} user {u.email}", admin.user_id, request)
    return user_payload(u)


@router.post("/users/{uid}/activate")
def activate_user(uid: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_active(uid, True, request, admin, db)


@router.post("/users/{uid}/deactivate")
def deactivate_user(uid: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_active(uid, False, request, admin, db)


@router.delete("/users/{uid}")
def delete_user(uid: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    if uid == admin.user_id: raise HTTPException(400, "You cannot delete your own account here.")
    if _would_leave_no_admin(db, u): raise HTTPException(400, "At least one active administrator must remain.")
    email = u.email
    db.delete(u); db.commit()
    log_event(db, "Admin", f"Admin {admin.email} deleted user {email}", admin.user_id, request)
    return {"message": "User deleted"}


@router.post("/users/{uid}/reset-password")
def admin_reset_password(uid: int, body: AdminResetPasswordIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    err = validate_password_strength(body.new_password)
    if err: raise HTTPException(422, err)
    u = _get_user(db, uid)
    u.password = hash_password(body.new_password); db.commit()
    log_event(db, "Admin", f"Admin {admin.email} reset password of {u.email}", admin.user_id, request)
    return {"message": "Password reset"}


# ======================================================= datasets (7.2.3 / FR-2 / 8.3)
def _ds_payload(d: DatasetImport) -> dict:
    return {"dataset_id": d.dataset_id, "name": d.dataset_name, "uploaded_by": d.uploaded_by,
            "upload_date": d.upload_date.isoformat() + "Z", "total_records": d.total_records,
            "imported_records": d.imported_records, "rejected_records": d.rejected_records,
            "duplicate_records": d.duplicate_records, "status": d.status, "progress": d.progress, "message": d.message}


async def _read_csv_upload(file: UploadFile):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(415, "Invalid file format. Only .csv datasets are accepted.")
    raw = await file.read(cfg.max_dataset_mb * 1024 * 1024 + 1)
    if len(raw) > cfg.max_dataset_mb * 1024 * 1024:
        raise HTTPException(413, f"The file is too large (maximum {cfg.max_dataset_mb} MB).")
    try:
        return dsvc.read_csv_bytes(raw)
    except DatasetValidationError as e:
        raise HTTPException(422, str(e))


@router.post("/datasets/preview")
async def preview_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    df = await _read_csv_upload(file)
    try:
        return dsvc.preview(df, db)
    except DatasetValidationError as e:
        raise HTTPException(422, str(e))


@router.post("/datasets/upload", status_code=202)
async def upload_dataset(request: Request, file: UploadFile = File(...), wait: bool = False,
                         admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    df = await _read_csv_upload(file)
    try:
        rec = dsvc.start_import(db, df, file.filename, admin.user_id, wait=wait)
    except DatasetValidationError as e:
        log_event(db, "Import", f"Dataset validation failed for '{file.filename}': {e}", admin.user_id, request)
        raise HTTPException(422, str(e))
    return {**_ds_payload(rec), "message": "Dataset upload accepted; import is running" if rec.status == "Processing" else rec.message}


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    return {"items": [_ds_payload(d) for d in db.query(DatasetImport).order_by(DatasetImport.dataset_id.desc())],
            "total_articles": db.query(func.count(NewsArticle.news_id)).scalar()}


@router.get("/datasets/{dataset_id}")
def dataset_status(dataset_id: int, db: Session = Depends(get_db)):
    d = db.get(DatasetImport, dataset_id)
    if not d: raise HTTPException(404, "Dataset not found")
    return _ds_payload(d)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(DatasetImport, dataset_id)
    if not d: raise HTTPException(404, "Dataset not found")
    if d.status == "Processing": raise HTTPException(409, "This dataset is still being imported.")
    name = d.dataset_name
    if app_settings.get(db, "active_dataset") == str(dataset_id):
        app_settings.set_value(db, "active_dataset", "all")        # never leave the setting pointing at a deleted dataset
    db.query(NewsArticle).filter(NewsArticle.dataset_id == dataset_id).delete(synchronize_session=False)
    db.delete(d); db.commit()
    similarity_index.mark_dirty()
    log_event(db, "Import", f"Dataset {dataset_id} '{name}' deleted", admin.user_id, request)
    return {"message": "Dataset deleted"}


# ========================================================= news articles (7.2.4)
def _article(a: NewsArticle, full: bool = False) -> dict:
    d = {"news_id": a.news_id, "title": a.title, "subject": a.subject, "label": a.label,
         "publication_date": a.publication_date, "dataset_id": a.dataset_id, "source_file": a.source_file}
    d["content" if full else "snippet"] = a.content if full else a.content[:200]
    return d


@router.get("/news")
def list_news(search: str | None = None, label: str | None = Query(None, pattern="^(Fake|Real)$"), subject: str | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    q = db.query(NewsArticle)
    if search:
        like = f"%{search.strip()}%"; q = q.filter(or_(NewsArticle.title.ilike(like), NewsArticle.content.ilike(like)))
    if label: q = q.filter(NewsArticle.label == label)
    if subject: q = q.filter(NewsArticle.subject == subject)
    total, rows, pages = _page(q.order_by(NewsArticle.news_id), page, page_size)
    return {"items": [_article(a) for a in rows], "total": total, "page": page, "pages": pages}


@router.get("/news/{news_id}")
def get_news(news_id: int, db: Session = Depends(get_db)):
    a = db.get(NewsArticle, news_id)
    if not a: raise HTTPException(404, "Article not found")
    return _article(a, full=True)


@router.put("/news/{news_id}")
def edit_news(news_id: int, body: NewsUpdate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.get(NewsArticle, news_id)
    if not a: raise HTTPException(404, "Article not found")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(a, k, v)
    new_hash = content_hash(a.title, a.content)
    if new_hash != a.content_hash:
        if db.query(NewsArticle).filter(NewsArticle.content_hash == new_hash, NewsArticle.news_id != news_id).first():
            db.rollback(); raise HTTPException(409, "Another article with identical content already exists.")
        a.content_hash, a.processed_text, a.prep_signature = new_hash, None, None
    db.commit(); similarity_index.mark_dirty()
    log_event(db, "Admin", f"Article {news_id} edited", admin.user_id, request)
    return _article(a, full=True)


@router.delete("/news/{news_id}")
def delete_news(news_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.get(NewsArticle, news_id)
    if not a: raise HTTPException(404, "Article not found")
    db.delete(a); db.commit(); similarity_index.mark_dirty()
    log_event(db, "Admin", f"Article {news_id} deleted", admin.user_id, request)
    return {"message": "Article deleted"}


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db)):
    rows = db.query(NewsArticle.subject, NewsArticle.label, func.count()).group_by(NewsArticle.subject, NewsArticle.label).all()
    out: dict[str, dict] = {}
    for s, l, n in rows:
        out.setdefault(s, {"subject": s, "Fake": 0, "Real": 0, "total": 0}); out[s][l] = n; out[s]["total"] += n
    return {"items": sorted(out.values(), key=lambda r: -r["total"])}


@router.put("/subjects/{name}")
def rename_subject(name: str, body: SubjectRename, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Rename a category; renaming onto an existing name merges the two."""
    n = db.query(NewsArticle).filter(NewsArticle.subject == name).update({"subject": body.new_name.strip()})
    if n == 0: raise HTTPException(404, "Subject not found")
    db.commit()
    log_event(db, "Admin", f"Subject '{name}' renamed to '{body.new_name}' ({n} articles)", admin.user_id, request)
    return {"updated": n}


# ================================================================ models (7.2.5 / FR-10)
def _run_payload(r: TrainingRun) -> dict:
    return {"run_id": r.run_id, "model_id": r.model_id, "started_at": r.started_at.isoformat() + "Z", "duration": r.duration,
            "dataset_version": r.dataset_version, "n_train": r.n_train, "n_test": r.n_test, "status": r.status}


@router.get("/models/options")
def model_options():
    return {"algorithms": ALGORITHMS, "vectorizers": list(model_mgmt.VECTORIZERS)}


@router.get("/models")
def list_models(db: Session = Depends(get_db)):
    return {"items": [analytics.model_dict(m) for m in db.query(MLModel).order_by(MLModel.model_id.desc())]}


@router.get("/models/runs")
def training_history(db: Session = Depends(get_db)):
    return {"items": [_run_payload(r) for r in db.query(TrainingRun).order_by(TrainingRun.run_id.desc()).limit(100)]}


@router.post("/models/train", status_code=202)
def train_model(body: TrainIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        m = model_mgmt.create_model_record(db, body.algorithm, body.vectorizer, body.name)
        run = model_mgmt.start_training(db, m, admin.user_id, wait=body.wait)
    except model_mgmt.ModelError as e:
        if "m" in locals(): db.delete(m); db.commit()
        raise HTTPException(409 if "already running" in str(e) else 422, str(e))
    return {**analytics.model_dict(db.get(MLModel, m.model_id)), "run_id": run.run_id}


@router.post("/models/train-batch", status_code=202)
def train_batch(body: TrainBatchIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        models = model_mgmt.start_batch_training(db, body.algorithms, body.vectorizer, admin.user_id)
    except model_mgmt.ModelError as e:
        raise HTTPException(409 if "already running" in str(e) else 422, str(e))
    return {"items": [{"model_id": m.model_id, "algorithm": m.algorithm} for m in models]}


@router.post("/models/{model_id}/retrain", status_code=202)
def retrain(model_id: int, wait: bool = False, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.get(MLModel, model_id)
    if not m: raise HTTPException(404, "Model not found")
    try:
        run = model_mgmt.start_training(db, m, admin.user_id, wait=wait)
    except model_mgmt.ModelError as e:
        raise HTTPException(409, str(e))
    return {**analytics.model_dict(db.get(MLModel, model_id)), "run_id": run.run_id}


@router.get("/models/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(MLModel, model_id)
    if not m: raise HTTPException(404, "Model not found")
    runs = db.query(TrainingRun).filter_by(model_id=model_id).order_by(TrainingRun.run_id.desc()).all()
    done = next((r for r in runs if r.status == "Completed" and r.metrics_json), None)
    roc = json.loads(done.metrics_json).get("roc_curve") if done else None      # None for models trained before ROC was stored
    return {**analytics.model_dict(m), "roc_curve": roc, "runs": [{**_run_payload(r), "log": r.log} for r in runs]}


@router.put("/models/{model_id}/activate")
def activate_model(model_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return analytics.model_dict(model_mgmt.activate(db, model_id, admin.user_id))
    except model_mgmt.ModelError as e:
        raise HTTPException(404 if "not found" in str(e) else 409, str(e))


@router.delete("/models/{model_id}")
def remove_model(model_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        model_mgmt.delete_model(db, model_id, admin.user_id)
    except model_mgmt.ModelError as e:
        raise HTTPException(404 if "not found" in str(e) else 409, str(e))
    return {"message": "Model deleted"}


# =========================================================== analytics (7.2.1 / 7.2.6 / 7.2.7)
@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    return {**analytics.dashboard(db), "content": analytics.content_analytics(db)}


@router.get("/explainability")
def explainability(db: Session = Depends(get_db)):
    return analytics.explainability_stats(db)


@router.get("/reports/analytics")
def analytics_report(format: str = Query("pdf", pattern="^(pdf|csv)$"), db: Session = Depends(get_db)):
    dash, content = analytics.dashboard(db), analytics.content_analytics(db)
    if format == "pdf":
        return Response(analytics_pdf(dash, content), media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="system_analytics.pdf"'})
    return Response(analytics_csv(dash, content), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="system_analytics.csv"'})


# ============================================ keyword dictionary, stop-words, settings (7.2.8)
@router.get("/keyword-dictionary")
def list_keyword_dict(db: Session = Depends(get_db)):
    return {"items": [{"id": e.entry_id, "term": e.term, "list_type": e.list_type}
                      for e in db.query(KeywordDictionaryEntry).order_by(KeywordDictionaryEntry.term)]}


@router.post("/keyword-dictionary", status_code=201)
def add_keyword_entry(body: KeywordEntryIn, db: Session = Depends(get_db)):
    term = body.term.strip().lower()
    if db.query(KeywordDictionaryEntry).filter_by(term=term, list_type=body.list_type).first():
        raise HTTPException(409, "This entry already exists")
    e = KeywordDictionaryEntry(term=term, list_type=body.list_type); db.add(e); db.commit()
    return {"id": e.entry_id, "term": e.term, "list_type": e.list_type}


@router.delete("/keyword-dictionary/{entry_id}")
def delete_keyword_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.get(KeywordDictionaryEntry, entry_id)
    if not e: raise HTTPException(404, "Entry not found")
    db.delete(e); db.commit()
    return {"message": "Entry deleted"}


@router.get("/stopwords")
def get_stopwords():
    return {"words": sorted(stopwords.words), "count": len(stopwords.words)}


@router.put("/stopwords")
def put_stopwords(body: StopwordsIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    words = {w.strip().lower() for w in body.words if w.strip()}
    if not words: raise HTTPException(422, "The stop-word list cannot be empty.")
    stopwords.save(words)
    similarity_index.mark_dirty()
    log_event(db, "Admin", f"Stop-word list updated ({len(words)} words). Retrain models to apply it to training data.", admin.user_id, request)
    return {"count": len(words), "message": "Stop-word list saved. Retrain a model for the change to affect predictions."}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    active = db.query(MLModel).filter(MLModel.is_active.is_(True)).first()
    return {"values": app_settings.get_all(db), "keyword_methods": list(KEYWORD_METHODS),
            "default_nlp_model": active.model_id if active else None,
            "datasets": [{"dataset_id": d.dataset_id, "name": d.dataset_name} for d in db.query(DatasetImport).filter_by(status="Success")]}


@router.put("/settings")
def put_settings(body: SettingsUpdate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    v = body.values
    checks = {"keyword_method": lambda x: x in KEYWORD_METHODS, "max_upload_mb": lambda x: x.isdigit() and 1 <= int(x) <= 100,
              "keywords_top_n": lambda x: x.isdigit() and 1 <= int(x) <= 30,
              "supported_file_types": lambda x: bool(x) and set(t.strip() for t in x.split(",")) <= {"txt", "pdf"},
              "theme": lambda x: x in ("light", "dark"), "active_dataset": lambda x: x == "all" or x.isdigit()}
    for k, val in v.items():
        if k not in checks: raise HTTPException(422, f"Unknown setting '{k}'")
        if not checks[k](str(val)): raise HTTPException(422, f"Invalid value for '{k}': {val}")
    ds = v.get("active_dataset", "all")
    if ds != "all" and not db.query(DatasetImport).filter_by(dataset_id=int(ds), status="Success").first():
        raise HTTPException(422, f"Dataset {ds} does not exist or was not imported successfully.")
    for k, val in v.items(): app_settings.set_value(db, k, str(val))
    log_event(db, "Admin", f"Settings updated: {sorted(v)}", admin.user_id, request)
    return {"values": app_settings.get_all(db)}


# ================================================================== logs / activity
@router.get("/logs")
def system_logs(event_type: str | None = None, search: str | None = None, user_id: int | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), db: Session = Depends(get_db)):
    q = db.query(SystemLog, User.email).outerjoin(User, User.user_id == SystemLog.user_id)
    if event_type: q = q.filter(SystemLog.event_type == event_type)
    if user_id: q = q.filter(SystemLog.user_id == user_id)
    if search: q = q.filter(SystemLog.description.ilike(f"%{search.strip()}%"))
    total = q.count()
    rows = q.order_by(SystemLog.log_id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [{"log_id": l.log_id, "date": l.log_date.isoformat() + "Z", "event_type": l.event_type, "user": email,
                       "user_id": l.user_id, "description": l.description, "ip_address": l.ip_address} for l, email in rows],
            "total": total, "page": page, "pages": (total + page_size - 1) // page_size,
            "event_types": [t for (t,) in db.query(SystemLog.event_type).distinct()]}


@router.get("/activity")
def user_activity(db: Session = Depends(get_db)):
    preds = dict(db.query(PredictionHistory.user_id, func.count()).group_by(PredictionHistory.user_id).all())
    last_pred = dict(db.query(PredictionHistory.user_id, func.max(PredictionHistory.prediction_date)).group_by(PredictionHistory.user_id).all())
    return {"items": [{"user_id": u.user_id, "email": u.email, "role": u.role, "is_active": u.is_active,
                       "last_login": u.last_login.isoformat() + "Z" if u.last_login else None,
                       "predictions": preds.get(u.user_id, 0),
                       "last_prediction": last_pred[u.user_id].isoformat() + "Z" if u.user_id in last_pred else None}
                      for u in db.query(User).order_by(User.last_login.desc().nullslast())]}
