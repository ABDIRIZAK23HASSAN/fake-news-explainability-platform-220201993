"""Analytics Service (FR-9 / 8.11) and explainability monitoring (7.2.7)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (ExplainabilityResult, Keyword, MLModel, NewsArticle, PredictionHistory, User)

ACTIVE_WINDOW_DAYS = 30


def _model_dict(m: MLModel) -> dict:
    return {"id": m.model_id, "name": m.model_name, "algorithm": m.algorithm, "vectorizer": m.vectorizer,
            "accuracy": m.accuracy, "precision": m.precision, "recall": m.recall, "f1": m.f1_score,
            "roc_auc": m.roc_auc, "training_seconds": m.training_duration, "is_active": m.is_active,
            "status": m.status, "dataset_version": m.dataset_version,
            "training_date": m.training_date.isoformat() if m.training_date else None,
            "confusion_matrix": json.loads(m.confusion_matrix) if m.confusion_matrix else None}


def model_dict(m: MLModel) -> dict:
    return _model_dict(m)


def dashboard(db: Session) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(days=ACTIVE_WINDOW_DAYS)
    total_pred = db.query(func.count(PredictionHistory.prediction_id)).scalar() or 0
    by_label = dict(db.query(PredictionHistory.prediction_result, func.count()).group_by(PredictionHistory.prediction_result).all())
    avg_conf, avg_time = db.query(func.avg(PredictionHistory.confidence_score), func.avg(PredictionHistory.processing_time)).one()

    # daily (last 30 days) + monthly (last 12 months) - aggregated in Python for DB portability
    rows = db.query(PredictionHistory.prediction_date, PredictionHistory.prediction_result,
                    PredictionHistory.processing_time, PredictionHistory.user_id).filter(
        PredictionHistory.prediction_date >= now - timedelta(days=366)).all()
    daily, monthly = defaultdict(lambda: {"Fake": 0, "Real": 0}), defaultdict(lambda: {"Fake": 0, "Real": 0})
    buckets = Counter()
    for d, label, pt, _ in rows:
        if d >= now - timedelta(days=30):
            daily[d.strftime("%Y-%m-%d")][label] += 1
        monthly[d.strftime("%Y-%m")][label] += 1
        buckets["<0.1s" if pt < 0.1 else "0.1-0.5s" if pt < 0.5 else "0.5-1s" if pt < 1 else "1-2s" if pt < 2 else ">2s"] += 1
    order = ["<0.1s", "0.1-0.5s", "0.5-1s", "1-2s", ">2s"]

    active_users = db.query(func.count(User.user_id)).filter(User.is_active.is_(True), User.last_login >= since).scalar() or 0
    active_model = db.query(MLModel).filter(MLModel.is_active.is_(True)).first()
    top_users = (db.query(User.email, func.count(PredictionHistory.prediction_id))
                 .join(PredictionHistory).group_by(User.email)
                 .order_by(func.count(PredictionHistory.prediction_id).desc()).limit(10).all())
    return {
        "total_users": db.query(func.count(User.user_id)).scalar() or 0,
        "active_users": active_users, "active_users_window_days": ACTIVE_WINDOW_DAYS,
        "total_predictions": total_pred,
        "fake_predictions": by_label.get("Fake", 0), "real_predictions": by_label.get("Real", 0),
        "total_news_articles": db.query(func.count(NewsArticle.news_id)).scalar() or 0,
        "dataset_size": {"total": db.query(func.count(NewsArticle.news_id)).scalar() or 0,
                         **{k.lower(): v for k, v in db.query(NewsArticle.label, func.count()).group_by(NewsArticle.label).all()}},
        "average_confidence": float(avg_conf) if avg_conf is not None else None,
        "average_processing_time": float(avg_time) if avg_time is not None else None,
        "active_model": _model_dict(active_model) if active_model else None,
        "daily_predictions": [{"date": k, **v} for k, v in sorted(daily.items())],
        "monthly_predictions": [{"month": k, **v} for k, v in sorted(monthly.items())],
        "processing_time_distribution": [{"bucket": b, "count": buckets.get(b, 0)} for b in order],
        "user_activity": [{"email": e, "predictions": n} for e, n in top_users],
        "model_comparison": [_model_dict(m) for m in db.query(MLModel).filter(MLModel.status == "Ready").order_by(MLModel.model_id)],
    }


def content_analytics(db: Session) -> dict:
    kw = (db.query(Keyword.keyword, func.count().label("n"), func.avg(Keyword.importance_score))
          .group_by(Keyword.keyword).order_by(func.count().desc()).limit(20).all())
    subjects = db.query(NewsArticle.subject, func.count()).group_by(NewsArticle.subject).order_by(func.count().desc()).all()
    fake_topics = (db.query(NewsArticle.subject, func.count()).filter(NewsArticle.label == "Fake")
                   .group_by(NewsArticle.subject).order_by(func.count().desc()).all())
    return {"frequent_keywords": [{"keyword": k, "count": n, "avg_importance": round(float(a or 0), 3)} for k, n, a in kw],
            "news_subjects": [{"subject": s, "count": n} for s, n in subjects],
            "fake_news_topics": [{"subject": s, "count": n} for s, n in fake_topics]}


def explainability_stats(db: Session, top: int = 15) -> dict:
    """Which words drive predictions across the whole system (helps detect model bias)."""
    q = (db.query(ExplainabilityResult.word, ExplainabilityResult.method, PredictionHistory.prediction_result,
                  func.count().label("n"), func.avg(ExplainabilityResult.contribution_value).label("avg"))
         .join(PredictionHistory, PredictionHistory.prediction_id == ExplainabilityResult.prediction_id)
         .filter(ExplainabilityResult.contribution_type == "Positive")
         .group_by(ExplainabilityResult.word, ExplainabilityResult.method, PredictionHistory.prediction_result))
    rows = q.all()
    by_label: dict[str, list] = {"Fake": [], "Real": []}
    for w, method, label, n, avg in rows:
        by_label[label].append({"word": w, "method": method, "occurrences": n, "avg_contribution": round(float(avg), 4),
                                "total_weight": round(float(avg) * n, 4)})
    for k in by_label:
        by_label[k].sort(key=lambda r: -r["total_weight"])
    overall = Counter()
    for label in by_label.values():
        for r in label:
            overall[r["word"]] += r["total_weight"]
    shap_rows = [r for r in by_label["Fake"] + by_label["Real"] if r["method"] == "shap"]
    return {"most_influential_words": [{"word": w, "total_weight": round(v, 4)} for w, v in overall.most_common(top)],
            "fake_indicators": by_label["Fake"][:top], "real_indicators": by_label["Real"][:top],
            "average_shap_values": sorted(shap_rows, key=lambda r: -abs(r["avg_contribution"]))[:top],
            "note": "Weights are summed over explanations; a word that dominates one class may reveal dataset bias."}
