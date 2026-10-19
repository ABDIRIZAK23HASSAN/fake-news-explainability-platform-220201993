"""Fake News Prediction Service (spec 8.6).

Loads the single ACTIVE model, runs inference and returns label, confidence,
probability distribution, processing time and model info.  The service is a
decision-support tool: low-confidence results are flagged as uncertain.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import joblib
from sqlalchemy.orm import Session

from ..models import MLModel
from .training import LABELS

UNCERTAIN_BELOW = 0.70          # confidence under which the UI warns the user
MIN_WORDS = 20                  # shorter inputs cannot be classified meaningfully


class NoActiveModelError(RuntimeError):
    pass


class TextTooShortError(ValueError):
    pass


class ModelRegistry:
    """Caches loaded pipelines; invalidated whenever a model is activated/deleted/retrained."""

    def __init__(self):
        self._cache: dict[int, object] = {}
        self._lock = threading.Lock()

    def get_pipeline(self, model: MLModel):
        with self._lock:
            if model.model_id not in self._cache:
                path = Path(model.artifact_path or "")
                if not path.exists():
                    raise NoActiveModelError(f"Model file for '{model.model_name}' is missing on disk.")
                bundle = joblib.load(path)
                self._cache[model.model_id] = bundle["pipeline"]
            return self._cache[model.model_id]

    def invalidate(self, model_id: int | None = None):
        with self._lock:
            if model_id is None:
                self._cache.clear()
            else:
                self._cache.pop(model_id, None)


registry = ModelRegistry()


def get_active_model(db: Session) -> MLModel:
    model = db.query(MLModel).filter(MLModel.is_active.is_(True), MLModel.status == "Ready").first()
    if model is None:
        raise NoActiveModelError("No active model. An administrator must train and activate a model first.")
    return model


def check_min_words(text: str) -> None:
    if len(text.split()) < MIN_WORDS:
        raise TextTooShortError(f"Text is too short to analyse (minimum {MIN_WORDS} words).")


def predict(db: Session, text: str) -> dict:
    check_min_words(text)
    model = get_active_model(db)
    pipe = registry.get_pipeline(model)
    t0 = time.perf_counter()
    proba = pipe.predict_proba([text])[0]            # [P(Fake), P(Real)]
    elapsed = time.perf_counter() - t0
    idx = int(proba.argmax())
    return {
        "label": LABELS[idx],
        "label_index": idx,
        "confidence": float(proba[idx]),
        "probabilities": {"Fake": float(proba[0]), "Real": float(proba[1])},
        "processing_time": round(elapsed, 4),
        "uncertain": bool(proba[idx] < UNCERTAIN_BELOW),
        "model": {"id": model.model_id, "name": model.model_name, "algorithm": model.algorithm},
    }
