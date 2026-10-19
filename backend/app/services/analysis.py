"""Orchestrates the user workflow of the spec: preprocess -> features -> classify ->
explain -> keywords -> similar news -> store in history."""
from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from ..models import ExplainabilityResult, Keyword, NewsArticle, PredictionHistory, SimilarNews
from . import app_settings
from .explain import explain_lime, explain_shap, highlight_segments, shap_supported
from .keywords import extract_keywords
from .prediction import check_min_words, get_active_model, predict, registry
from .similar import index as similarity_index

log = logging.getLogger("app")


def analysis_document(title: str | None, text: str) -> str:
    """The models were trained on 'title. text', so predictions must use the same form."""
    return f"{title.strip()}. {text}" if title and title.strip() else text


def analyze_article(db: Session, user_id: int, title: str | None, text_in: str) -> PredictionHistory:
    t0 = time.perf_counter()
    text = text_in
    check_min_words(text)                                     # the ARTICLE itself must be long enough
    doc = analysis_document(title, text)
    pred = predict(db, doc)                                   # may raise NoActiveModel
    model = get_active_model(db)
    pipe = registry.get_pipeline(model)
    idx, conf = pred["label_index"], pred["confidence"]

    explanations = [explain_lime(pipe, doc, idx, conf)]
    if shap_supported(model.algorithm):
        try:
            explanations.append(explain_shap(pipe, model.algorithm, doc, idx, conf))
        except Exception:                                      # SHAP is a bonus - never fail the analysis
            log.exception("SHAP explanation failed")

    kws = extract_keywords(doc, method=app_settings.get(db, "keyword_method"),
                           top_n=int(app_settings.get(db, "keywords_top_n")),
                           idf_lookup=similarity_index.idf_map or None, db=db)
    try:
        similar = similarity_index.search(db, doc)
    except Exception:
        log.exception("similar-news retrieval failed")
        similar = []

    total = time.perf_counter() - t0
    p = PredictionHistory(user_id=user_id, submitted_title=(title or None), submitted_content=text,
                          prediction_result=pred["label"], confidence_score=conf,
                          prob_fake=pred["probabilities"]["Fake"], prob_real=pred["probabilities"]["Real"],
                          processing_time=round(total, 4), model_id=model.model_id)
    for ex in explanations:
        for item in ex["feature_importance"]:
            p.explanations.append(ExplainabilityResult(word=item["word"][:200], contribution_value=float(item["weight"]),
                                                       contribution_type=item["type"], method=ex["method"]))
    for k in kws:
        # explicit float()/int(): PostgreSQL (unlike SQLite) rejects numpy scalar types
        p.keywords.append(Keyword(keyword=str(k["keyword"])[:200], importance_score=float(k["importance"]),
                                  frequency=int(k["frequency"]) if k.get("frequency") is not None else None))
    for rank, (news_id, score) in enumerate(similar, 1):
        p.similar.append(SimilarNews(news_id=int(news_id), similarity_score=float(score), rank=rank))
    db.add(p); db.commit(); db.refresh(p)
    p._inference_time = pred["processing_time"]
    p._uncertain = pred["uncertain"]
    return p


# ---------------------------------------------------------------- serialisation
def _explanation_payload(p: PredictionHistory, method: str) -> dict | None:
    rows = [e for e in p.explanations if e.method == method]
    if not rows:
        return None
    items = sorted(({"word": e.word, "weight": e.contribution_value, "type": e.contribution_type} for e in rows),
                   key=lambda i: -abs(i["weight"]))
    return {"method": method, "predicted_label": p.prediction_result, "confidence": p.confidence_score,
            "positive_words": [i for i in items if i["type"] == "Positive"],
            "negative_words": [i for i in items if i["type"] == "Negative"],
            "feature_importance": items,
            "highlight": highlight_segments(p.submitted_content, {i["word"]: i["weight"] for i in items})}


def explanation_for(p: PredictionHistory) -> dict:
    return {"lime": _explanation_payload(p, "lime"), "shap": _explanation_payload(p, "shap")}


def similar_payload(p: PredictionHistory) -> list[dict]:
    out = []
    for x in sorted(p.similar, key=lambda x: x.rank):
        n: NewsArticle | None = x.news
        if n:
            out.append({"rank": x.rank, "news_id": n.news_id, "title": n.title, "subject": n.subject,
                        "similarity": round(x.similarity_score, 4), "label": n.label,
                        "publication_date": n.publication_date})
    return out


def summary(p: PredictionHistory) -> dict:
    return {"prediction_id": p.prediction_id, "title": p.submitted_title,
            "snippet": p.submitted_content[:160], "result": p.prediction_result,
            "confidence": p.confidence_score, "processing_time": p.processing_time,
            "date": p.prediction_date.isoformat() + "Z",
            "model": p.model.model_name if p.model else None}


def full_result(p: PredictionHistory) -> dict:
    return {**summary(p), "text": p.submitted_content,
            "probabilities": {"Fake": p.prob_fake, "Real": p.prob_real},
            "uncertain": p.confidence_score < 0.70,
            "model_info": ({"id": p.model.model_id, "name": p.model.model_name, "algorithm": p.model.algorithm}
                           if p.model else None),
            "explanation": explanation_for(p),
            "keywords": [{"keyword": k.keyword, "importance": k.importance_score, "frequency": k.frequency}
                         for k in sorted(p.keywords, key=lambda k: -k.importance_score)],
            "similar": similar_payload(p)}
