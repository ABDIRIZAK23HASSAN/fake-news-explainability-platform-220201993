"""Keyword Extraction Service (FR-7 / 8.9). Methods: tfidf (default) and rake.
Returns readable (un-stemmed) keywords with importance score and frequency."""
from __future__ import annotations

import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from ..models import KeywordDictionaryEntry
from .preprocessing import _stem, clean_text, stopwords

TOP_N = 10
METHODS = ("tfidf", "rake")


def _dictionary(db: Session | None):
    if db is None:
        return set(), set()
    rows = db.query(KeywordDictionaryEntry).all()
    return ({r.term.lower() for r in rows if r.list_type == "include"},
            {r.term.lower() for r in rows if r.list_type == "exclude"})


def _tfidf(text: str, idf_lookup: dict[str, float] | None) -> list[dict]:
    tokens = [t for t in clean_text(text).split() if t not in stopwords.words and len(t) > 2]
    if not tokens:
        return []
    stems = [_stem(t) for t in tokens]
    tf = Counter(stems)
    surface: dict[str, Counter] = {}
    for t, s in zip(tokens, stems):
        surface.setdefault(s, Counter())[t] += 1
    default_idf = max(idf_lookup.values()) if idf_lookup else 5.0
    scored = []
    for s, f in tf.items():
        idf = (idf_lookup or {}).get(s, default_idf)
        scored.append((s, float((1 + math.log(f)) * idf), int(f)))
    top = max((x[1] for x in scored), default=1.0) or 1.0
    scored.sort(key=lambda x: -x[1])
    return [{"keyword": surface[s].most_common(1)[0][0], "importance": round(v / top, 4), "frequency": f}
            for s, v, f in scored]


def _rake(text: str) -> list[dict]:
    sw = stopwords.words
    words = re.findall(r"[A-Za-z][A-Za-z'\u2019-]*", text.lower())
    phrases, cur = [], []
    for w in words:
        if w in sw or len(w) < 3:
            if cur:
                phrases.append(cur); cur = []
        else:
            cur.append(w)
    if cur:
        phrases.append(cur)
    freq, deg = Counter(), Counter()
    for p in phrases:
        for w in p:
            freq[w] += 1
            deg[w] += len(p) - 1
    score = {w: (deg[w] + freq[w]) / freq[w] for w in freq}
    cand = Counter(" ".join(p) for p in phrases if len(p) <= 3)
    ranked = sorted(((sum(score[w] for w in ph.split()), ph, c) for ph, c in cand.items()), reverse=True)
    top = ranked[0][0] if ranked else 1.0
    return [{"keyword": ph, "importance": round(s / top, 4), "frequency": c} for s, ph, c in ranked]


def extract_keywords(text: str, method: str = "tfidf", top_n: int = TOP_N, idf_lookup=None,
                     db: Session | None = None) -> list[dict]:
    include, exclude = _dictionary(db)
    kws = _rake(text) if method == "rake" else _tfidf(text, idf_lookup)
    kws = [k for k in kws if k["keyword"] not in exclude]
    chosen = kws[:top_n]
    # dictionary 'include' terms that really occur in the article are always surfaced
    present = {k["keyword"] for k in chosen}
    lowered = text.lower()
    for term in sorted(include):
        if term not in present and re.search(r"\b" + re.escape(term) + r"\b", lowered):
            chosen.append({"keyword": term, "importance": 1.0, "frequency": lowered.count(term)})
    return chosen
