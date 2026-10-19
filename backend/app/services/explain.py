"""Explainability Service (spec FR-5 / 6.5 / 8.7): LIME (any model) and SHAP (linear / XGBoost).

Sign convention (matches the spec's examples): a POSITIVE weight pushes the
prediction TOWARDS the predicted class, a NEGATIVE weight pushes AGAINST it.
"""
from __future__ import annotations

import re

import numpy as np
from lime.lime_text import LimeTextExplainer

from .preprocessing import clean_text, _stem, stopwords
from .training import LABELS

MAX_WORDS_EXPLAINED = 3000
LIME_SAMPLES = 400
TOP_K = 15
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\u2019]+")


def _truncate(text: str) -> str:
    words = text.split()
    return text if len(words) <= MAX_WORDS_EXPLAINED else " ".join(words[:MAX_WORDS_EXPLAINED])


def _package(method: str, pred_idx: int, confidence: float, pairs: list[tuple[str, float]]) -> dict:
    pairs = [(w, float(v)) for w, v in pairs if abs(v) > 1e-6]
    pairs.sort(key=lambda p: -abs(p[1]))
    pairs = pairs[:TOP_K * 2]
    items = [{"word": w, "weight": round(v, 5), "type": "Positive" if v > 0 else "Negative"} for w, v in pairs]
    return {
        "method": method,
        "predicted_label": LABELS[pred_idx],
        "confidence": confidence,
        "positive_words": [i for i in items if i["type"] == "Positive"][:TOP_K],
        "negative_words": [i for i in items if i["type"] == "Negative"][:TOP_K],
        "feature_importance": items,
    }


# ------------------------------------------------------------------ LIME
def explain_lime(pipeline, text: str, pred_idx: int, confidence: float,
                 num_samples: int = LIME_SAMPLES, seed: int = 42) -> dict:
    text = _truncate(text)
    explainer = LimeTextExplainer(class_names=[LABELS[0], LABELS[1]], bow=True,
                                  split_expression=r"\W+", random_state=seed)
    exp = explainer.explain_instance(text, pipeline.predict_proba, labels=(pred_idx,),
                                     num_features=TOP_K * 2, num_samples=num_samples)
    # Words that preprocessing removes (stop-words, 1-2 letter fragments, numbers) can NOT influence the
    # model; LIME's surrogate still gives them small noise weights, so they are dropped here.
    sw = stopwords.words
    pairs = [(w.lower(), v) for w, v in exp.as_list(label=pred_idx)
             if len(w) > 2 and not w.isdigit() and w.lower() not in sw]
    out = _package("lime", pred_idx, confidence, pairs)
    out["local_fit_r2"] = round(float(exp.score), 4)       # how faithful the local surrogate is
    return out


# ------------------------------------------------------------------ SHAP
SHAP_ALGORITHMS = {"logistic_regression", "xgboost"}


def shap_supported(algorithm: str) -> bool:
    return algorithm in SHAP_ALGORITHMS


def _stem_to_surface(text: str) -> dict[str, str]:
    """stem -> most frequent readable surface word in the article."""
    counts: dict[str, dict[str, int]] = {}
    for tok in clean_text(text).split():
        counts.setdefault(_stem(tok), {}).setdefault(tok, 0)
        counts[_stem(tok)][tok] += 1
    return {s: max(c, key=c.get) for s, c in counts.items()}


def explain_shap(pipeline, algorithm: str, text: str, pred_idx: int, confidence: float) -> dict:
    """SHAP values for the (stemmed) TF-IDF features, mapped back to readable words.
    Linear model: exact interventional SHAP (shap.LinearExplainer).  XGBoost: TreeExplainer."""
    import shap
    text = _truncate(text)
    cleaned = pipeline.named_steps["prep"].transform([text])
    X = pipeline.named_steps["tfidf"].transform(cleaned)
    clf = pipeline.named_steps["clf"]
    names = pipeline.named_steps["tfidf"].get_feature_names_out()
    if algorithm == "logistic_regression":
        mean = np.asarray(pipeline.named_steps["tfidf"].feature_mean_).reshape(1, -1)
        explainer = shap.LinearExplainer(clf, shap.maskers.Independent(mean))
        values = np.asarray(explainer.shap_values(X.toarray())).reshape(-1)
    elif algorithm == "xgboost":
        explainer = shap.TreeExplainer(clf)
        values = np.asarray(explainer.shap_values(X)).reshape(-1)
    else:
        raise ValueError(f"SHAP is not supported for {algorithm}")
    # SHAP values are for class 1 (Real); flip so that positive = supports the PREDICTED class
    if pred_idx == 0:
        values = -values
    surface = _stem_to_surface(text)
    pairs = []
    for i in np.flatnonzero(values):
        feat = names[i]
        label = " ".join(surface.get(p, p) for p in feat.split())
        pairs.append((label, values[i]))
    return _package("shap", pred_idx, confidence, pairs)


# ------------------------------------------------------- highlighting
def highlight_segments(text: str, weights: dict[str, float]) -> list[dict]:
    """Split the ORIGINAL article into segments; words with a known contribution carry a weight.
    `weights` maps lowercase words (and phrase words) to signed contributions."""
    by_word: dict[str, float] = {}
    by_stem: dict[str, float] = {}
    for phrase, w in weights.items():
        for part in phrase.lower().split():
            if abs(w) > abs(by_word.get(part, 0.0)):
                by_word[part] = w
                by_stem[_stem(part)] = w
    segments = []
    for piece in re.split(r"(\W+)", text):
        if not piece:
            continue
        key = piece.lower()
        w = by_word.get(key)
        if w is None and _TOKEN.fullmatch(piece):
            w = by_stem.get(_stem(key.replace("'", "")))
        segments.append({"text": piece, "weight": round(w, 5) if w is not None else None})
    return segments
