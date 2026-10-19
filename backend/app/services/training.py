"""Training / evaluation service (spec 6.2, 6.3, 6.4, 8.5, 8.10).

Used by both the offline experiment scripts and the admin API, so a model
trained from the admin panel is built exactly like one from the experiments.
Label convention: 0 = Fake, 1 = Real.
"""
from __future__ import annotations

import time
from multiprocessing import Pool, cpu_count
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

from .preprocessing import preprocess, preprocess_batch

LABELS = {0: "Fake", 1: "Real"}
REQUIRED_COLUMNS = ["title", "text", "subject", "date", "label"]
SEED = 42


# ------------------------------------------------------------------ data
def normalise_label(v) -> int | None:
    """Accept 0/1, 'fake'/'real', 'true'/'false' (case-insensitive)."""
    s = str(v).strip().lower()
    if s in {"0", "fake", "false"}:
        return 0
    if s in {"1", "real", "true"}:
        return 1
    return None


def build_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Drop empty articles and duplicates (incl. same text under both labels)."""
    df = df.copy()
    df["title"] = df["title"].fillna("").astype(str)
    df["text"] = df["text"].fillna("").astype(str)
    df = df[df["text"].str.strip() != ""]
    df["content"] = (df["title"] + ". " + df["text"]).str.strip()
    key = df["content"].str.lower().str.replace(r"\s+", " ", regex=True)
    df = df.assign(_key=key)
    # an article that appears under BOTH labels is contradictory -> drop all copies
    conflict = df.groupby("_key")["label"].nunique()
    df = df[~df["_key"].isin(conflict[conflict > 1].index)]
    df = df.drop_duplicates("_key").drop(columns="_key")
    return df.reset_index(drop=True)


def split_dataset(df: pd.DataFrame, test_size: float = 0.2, seed: int = SEED):
    return train_test_split(df, test_size=test_size, stratify=df["label"], random_state=seed)


# -------------------------------------------------------- preprocessing
def _prep_worker(args):
    text, kw = args
    return preprocess(text, **kw)


def preprocess_parallel(texts, processes: int | None = None, **kw) -> list[str]:
    texts = list(texts)
    processes = processes or max(1, cpu_count())
    if processes == 1 or len(texts) < 500:
        return [preprocess(t, **kw) for t in texts]
    with Pool(processes) as pool:
        return pool.map(_prep_worker, [(t, kw) for t in texts], chunksize=200)


# -------------------------------------------------------------- features
def make_vectorizer(kind: str = "tfidf_bigram", max_features: int = 50_000):
    """Feature extraction methods compared in the experiments (spec 6.2)."""
    common = dict(max_features=max_features, min_df=3, max_df=0.9)
    if kind == "bow":
        return CountVectorizer(ngram_range=(1, 1), **common)
    if kind == "tfidf":
        return TfidfVectorizer(ngram_range=(1, 1), sublinear_tf=True, **common)
    if kind == "tfidf_bigram":
        return TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, **common)
    if kind == "tfidf_trigram":
        return TfidfVectorizer(ngram_range=(1, 3), sublinear_tf=True, **common)
    raise ValueError(f"unknown vectorizer: {kind}")


# ---------------------------------------------------------------- models
def make_classifier(name: str):
    if name == "logistic_regression":
        return LogisticRegression(max_iter=1000, C=4.0, solver="liblinear", random_state=SEED)
    if name == "linear_svm":   # calibrated so that predict_proba exists (confidence score)
        return CalibratedClassifierCV(LinearSVC(C=0.5, random_state=SEED), cv=3)
    if name == "naive_bayes":
        return MultinomialNB(alpha=0.1)
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=SEED)
    if name == "xgboost":
        return XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.2,
                             tree_method="hist", n_jobs=-1, random_state=SEED,
                             eval_metric="logloss")
    raise ValueError(f"unknown algorithm: {name}")


ALGORITHMS = {
    "logistic_regression": "Logistic Regression",
    "linear_svm": "Support Vector Machine (linear, calibrated)",
    "naive_bayes": "Naive Bayes (multinomial)",
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
}


# ------------------------------------------------------------ evaluation
def evaluate(y_true, y_pred, y_proba_real) -> dict:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    fpr, tpr, _ = roc_curve(y_true, y_proba_real)
    keep = np.unique(np.linspace(0, len(fpr) - 1, 120).astype(int))        # <=120 points is plenty to draw
    return {
        "roc_curve": {"fpr": [round(float(x), 5) for x in fpr[keep]], "tpr": [round(float(x), 5) for x in tpr[keep]]},
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred)),
        "recall": float(recall_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred)),
        "roc_auc": float(roc_auc_score(y_true, y_proba_real)),
        "confusion_matrix": cm.tolist(),   # rows = true [Fake, Real], cols = predicted
    }


def train_and_evaluate(algorithm: str, X_train_clean, y_train, X_test_clean, y_test,
                       vectorizer: str = "tfidf_bigram", preprocess_kwargs: dict | None = None,
                       max_features: int = 50_000):
    """Fit vectoriser + classifier on ALREADY-preprocessed text, evaluate on the
    test split, and return a deployable Pipeline (raw text in -> proba out)."""
    preprocess_kwargs = preprocess_kwargs or {}
    # tree models do not benefit from a huge sparse space and become very slow
    if algorithm in {"random_forest", "xgboost"}:
        max_features = min(max_features, 10_000)
    t0 = time.perf_counter()
    vec = make_vectorizer(vectorizer, max_features)
    Xtr = vec.fit_transform(X_train_clean)
    clf = make_classifier(algorithm).fit(Xtr, y_train)
    vec.feature_mean_ = np.asarray(Xtr.mean(axis=0)).ravel().astype(np.float32)   # SHAP baseline
    duration = time.perf_counter() - t0

    Xte = vec.transform(X_test_clean)
    proba = clf.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = evaluate(y_test, pred, proba)
    metrics["training_seconds"] = round(duration, 2)
    metrics["n_features"] = int(Xtr.shape[1])

    pipeline = Pipeline([
        ("prep", FunctionTransformer(preprocess_batch, kw_args=preprocess_kwargs, validate=False)),
        ("tfidf", vec),
        ("clf", clf),
    ])
    return pipeline, metrics
