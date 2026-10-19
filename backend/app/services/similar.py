"""Similar News Retrieval Service (FR-6 / 8.8): TF-IDF + cosine similarity.
Document similarity over the whole imported corpus - NOT keyword matching."""
from __future__ import annotations

import threading
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy.orm import Session

from ..config import settings
from ..models import NewsArticle
from .corpus import ensure_processed
from .preprocessing import preprocess

INDEX_PATH = Path(settings.storage_dir) / "similarity_index.joblib"
TOP_K = 5


class SimilarityIndex:
    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self.news_ids: np.ndarray = np.array([], dtype=int)
        self.dirty = True
        self._lock = threading.Lock()

    @property
    def idf_map(self) -> dict[str, float]:
        if self.vectorizer is None:
            return {}
        if not hasattr(self, '_idf') or self._idf_for is not self.vectorizer:
            self._idf = dict(zip(self.vectorizer.get_feature_names_out(), self.vectorizer.idf_))
            self._idf_for = self.vectorizer
        return self._idf

    def mark_dirty(self):
        self.dirty = True

    def build(self, db: Session):
        with self._lock:
            ensure_processed(db)
            rows = db.query(NewsArticle.news_id, NewsArticle.processed_text).all()
            ids = [r[0] for r in rows if r[1]]
            docs = [r[1] for r in rows if r[1]]
            if not docs:
                self.vectorizer, self.matrix, self.news_ids, self.dirty = None, None, np.array([], dtype=int), False
                return
            vec = TfidfVectorizer(max_features=60_000, min_df=2, max_df=0.9, sublinear_tf=True)
            self.matrix = vec.fit_transform(docs)                 # rows are L2-normalised
            self.vectorizer, self.news_ids, self.dirty = vec, np.array(ids), False
            joblib.dump({"vec": vec, "matrix": self.matrix, "ids": self.news_ids}, INDEX_PATH)

    def ensure_ready(self, db: Session):
        if self.dirty:
            if INDEX_PATH.exists() and self.vectorizer is None:
                try:
                    d = joblib.load(INDEX_PATH)
                    n_db = db.query(NewsArticle.news_id).count()
                    if len(d["ids"]) == n_db:                    # cheap staleness check
                        self.vectorizer, self.matrix, self.news_ids, self.dirty = d["vec"], d["matrix"], d["ids"], False
                        return
                except Exception:
                    pass
            self.build(db)

    def search(self, db: Session, text: str, k: int = TOP_K) -> list[tuple[int, float]]:
        self.ensure_ready(db)
        if self.vectorizer is None:
            return []
        q = self.vectorizer.transform([preprocess(text)])
        if q.nnz == 0:
            return []
        scores = (self.matrix @ q.T).toarray().ravel()
        top = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(self.news_ids[i]), float(scores[i])) for i in top if scores[i] > 0]


index = SimilarityIndex()
