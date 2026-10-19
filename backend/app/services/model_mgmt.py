"""Model Management Service (FR-10 / 8.10): train, retrain, compare, activate, delete."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import DatasetImport, MLModel, NewsArticle, TrainingRun
from . import app_settings
from .corpus import LEAKAGE_LEVEL, ensure_processed
from .logging_service import log_event
from .prediction import registry
from .training import ALGORITHMS, split_dataset, train_and_evaluate

VECTORIZERS = ("bow", "tfidf", "tfidf_bigram")
MIN_ARTICLES, MIN_PER_CLASS = 200, 50


class ModelError(ValueError):
    pass


def training_scope(db: Session) -> int | None:
    """None = all imported datasets, otherwise the id chosen in Settings > 'Dataset used for training'."""
    v = app_settings.get(db, "active_dataset")
    return int(v) if v.isdigit() else None


def dataset_version_label(db: Session) -> str:
    scope = training_scope(db)
    if scope is not None:
        return f"dataset {scope} ({db.query(NewsArticle).filter(NewsArticle.dataset_id == scope).count()} articles)"[:100]
    ids = [i for (i,) in db.query(DatasetImport.dataset_id).filter(DatasetImport.status == "Success").all()]
    return f"datasets {','.join(map(str, ids)) or '-'} ({db.query(NewsArticle).count()} articles)"[:100]


def create_model_record(db: Session, algorithm: str, vectorizer: str, name: str | None) -> MLModel:
    if algorithm not in ALGORITHMS:
        raise ModelError(f"Unknown algorithm '{algorithm}'. Choose one of: {', '.join(ALGORITHMS)}")
    if vectorizer not in VECTORIZERS:
        raise ModelError(f"Unknown feature extraction '{vectorizer}'. Choose one of: {', '.join(VECTORIZERS)}")
    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    m = MLModel(model_name=name or f"{ALGORITHMS[algorithm].split(' (')[0]} / {vectorizer} / {stamp}",
                algorithm=algorithm, vectorizer=vectorizer, status="Training", is_active=False)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _train_job(model_id: int, run_id: int, user_id: int | None) -> None:
    db = SessionLocal()
    lines: list[str] = []

    def log(msg: str):
        lines.append(f"[{datetime.utcnow():%H:%M:%S}] {msg}")
        run = db.get(TrainingRun, run_id)
        run.log = "\n".join(lines)
        db.commit()

    t0 = time.perf_counter()
    try:
        model, run = db.get(MLModel, model_id), db.get(TrainingRun, run_id)
        log(f"Training {model.algorithm} with {model.vectorizer} features")
        n_stale = ensure_processed(db)
        log(f"Preprocessing up to date ({n_stale} articles re-processed)")
        q = db.query(NewsArticle.label, NewsArticle.processed_text)
        scope = training_scope(db)
        if scope is not None:
            q = q.filter(NewsArticle.dataset_id == scope)
            log(f"Training restricted to dataset {scope} (Settings)")
        rows = q.order_by(NewsArticle.news_id).all()   # fixed order => reproducible split
        df = pd.DataFrame(rows, columns=["label", "text"])
        df["y"] = (df["label"] == "Real").astype(int)
        df = df[df["text"].fillna("").str.len() > 0]
        counts = df["y"].value_counts()
        if len(df) < MIN_ARTICLES or counts.get(0, 0) < MIN_PER_CLASS or counts.get(1, 0) < MIN_PER_CLASS:
            raise ModelError(f"Not enough data to train: need >= {MIN_ARTICLES} articles and >= {MIN_PER_CLASS} "
                             f"of each class (have Fake={counts.get(0, 0)}, Real={counts.get(1, 0)}).")
        tr, te = split_dataset(df)
        log(f"Split 80/20: train={len(tr)}, test={len(te)} (stratified, seed 42)")
        pipe, metrics = train_and_evaluate(model.algorithm, tr["text"], tr["y"], te["text"], te["y"],
                                           vectorizer=model.vectorizer,
                                           preprocess_kwargs={"leakage_level": LEAKAGE_LEVEL})
        path = Path(settings.storage_dir) / "models" / f"model_{model_id}.joblib"
        joblib.dump({"pipeline": pipe}, path)
        duration = time.perf_counter() - t0
        model.artifact_path, model.status = str(path), "Ready"
        model.training_date, model.training_duration = datetime.utcnow(), round(duration, 2)
        model.dataset_version = dataset_version_label(db)
        model.accuracy, model.precision, model.recall = metrics["accuracy"], metrics["precision"], metrics["recall"]
        model.f1_score, model.roc_auc = metrics["f1"], metrics["roc_auc"]
        model.confusion_matrix = json.dumps(metrics["confusion_matrix"])
        run.status, run.duration, run.n_train, run.n_test = "Completed", round(duration, 2), len(tr), len(te)
        run.dataset_version, run.metrics_json = model.dataset_version, json.dumps(metrics)
        db.commit()
        registry.invalidate(model_id)
        log(f"Done in {duration:.1f}s - accuracy={metrics['accuracy']:.4f} f1={metrics['f1']:.4f}")
        log_event(db, "Training", f"Model {model_id} ({model.algorithm}) trained: acc={metrics['accuracy']:.4f}", user_id)
    except Exception as e:                       # noqa: BLE001
        db.rollback()
        m, r = db.get(MLModel, model_id), db.get(TrainingRun, run_id)
        if m: m.status = "Failed"
        if r: r.status = "Failed"
        db.commit()
        log(f"FAILED: {e}")
        log_event(db, "Error", f"Training of model {model_id} failed: {e}", user_id)
    finally:
        db.close()


def start_training(db: Session, model: MLModel, user_id: int | None, wait: bool = False) -> TrainingRun:
    if db.query(TrainingRun).filter(TrainingRun.status == "Running").count():
        raise ModelError("Another training job is already running. Please wait for it to finish.")
    model.status = "Training"
    run = TrainingRun(model_id=model.model_id, status="Running", dataset_version=dataset_version_label(db))
    db.add(run); db.commit(); db.refresh(run)
    t = threading.Thread(target=_train_job, args=(model.model_id, run.run_id, user_id), daemon=True)
    t.start()
    if wait:
        t.join()
        db.refresh(run)
        db.refresh(model)          # the worker thread used its own session: reload the fresh state
    return run


def activate(db: Session, model_id: int, user_id: int | None) -> MLModel:
    model = db.get(MLModel, model_id)
    if model is None:
        raise ModelError("Model not found.")
    if model.status != "Ready":
        raise ModelError(f"Only trained models can be activated (status: {model.status}).")
    db.query(MLModel).filter(MLModel.is_active.is_(True)).update({"is_active": False})
    db.flush()                                    # deactivate first -> unique index never violated
    model.is_active = True
    db.commit()
    registry.invalidate()
    log_event(db, "Activation", f"Model {model_id} ({model.model_name}) activated", user_id)
    return model


def delete_model(db: Session, model_id: int, user_id: int | None) -> None:
    model = db.get(MLModel, model_id)
    if model is None:
        raise ModelError("Model not found.")
    if model.is_active:
        raise ModelError("The active model cannot be deleted. Activate another model first.")
    if model.status == "Training":
        raise ModelError("This model is still training.")
    if model.artifact_path:
        Path(model.artifact_path).unlink(missing_ok=True)
    db.delete(model); db.commit()
    registry.invalidate(model_id)
    log_event(db, "Admin", f"Model {model_id} deleted", user_id)


def start_batch_training(db: Session, algorithms: list[str], vectorizer: str, user_id: int | None) -> list[MLModel]:
    """Train several algorithms one after another in ONE background thread (single-CPU friendly)."""
    if db.query(TrainingRun).filter(TrainingRun.status == "Running").count():
        raise ModelError("Another training job is already running. Please wait for it to finish.")
    models = [create_model_record(db, a, vectorizer, None) for a in algorithms]
    runs = []
    for m in models:
        r = TrainingRun(model_id=m.model_id, status="Running", dataset_version=dataset_version_label(db))
        db.add(r); db.commit(); db.refresh(r); runs.append(r.run_id)
    ids = [(m.model_id, rid) for m, rid in zip(models, runs)]

    def sequence():
        for mid, rid in ids:
            _train_job(mid, rid, user_id)
    threading.Thread(target=sequence, daemon=True).start()
    return models
