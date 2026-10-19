"""Keeps the stored, preprocessed copy of every article in sync with the current
preprocessing configuration (stop-word list etc.).  Shared by training and similarity."""
import hashlib

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import NewsArticle
from .preprocessing import preprocess, stopwords

LEAKAGE_LEVEL = 2


def prep_signature() -> str:
    """Changes whenever the stop-word list or the pipeline version changes."""
    h = hashlib.sha1((f"L{LEAKAGE_LEVEL}|stem|" + "|".join(sorted(stopwords.words))).encode()).hexdigest()
    return h[:16]


def article_text(a: NewsArticle) -> str:
    return f"{a.title}. {a.content}"


def ensure_processed(db: Session, chunk: int = 2000, progress=None) -> int:
    """Re-preprocess every article whose stored text is missing/outdated. Returns #updated."""
    sig = prep_signature()
    q = db.query(NewsArticle).filter(or_(NewsArticle.prep_signature.is_(None), NewsArticle.prep_signature != sig))
    total = q.count()
    done = 0
    while True:
        rows = q.limit(chunk).all()
        if not rows:
            break
        for a in rows:
            a.processed_text = preprocess(article_text(a), leakage_level=LEAKAGE_LEVEL)
            a.prep_signature = sig
        db.commit()
        done += len(rows)
        if progress:
            progress(done, total)
    return done
