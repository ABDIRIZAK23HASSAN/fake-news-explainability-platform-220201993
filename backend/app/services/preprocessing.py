"""NLP Preprocessing Service (spec 6.1 / 8.4).

The SAME code path is used for model training and for user predictions, so the
two can never drift apart.  Pipeline order:

    strip_source_artifacts -> lowercase -> HTML removal -> URL removal ->
    e-mail removal -> number normalisation -> punctuation removal ->
    whitespace normalisation -> tokenisation -> stop-word removal -> stemming

`strip_source_artifacts` is NOT in the assignment list.  It exists because the
dataset leaks its label through publisher boilerplate (e.g. the word "Reuters"
appears in ~99.8% of REAL articles and ~1% of FAKE ones).  Without removing it
a model scores ~99% by memorising one word.  See docs/leakage_analysis.md.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from nltk.stem.snowball import SnowballStemmer

STOPWORDS_FILE = Path(__file__).resolve().parents[2] / "data" / "stopwords.txt"

_stemmer = SnowballStemmer("english")

# ---------------------------------------------------------------- regexes
_HTML_TAG = re.compile(r"<[^>]+>")
_URL = re.compile(r"(?:https?://|www\.)\S+|pic\.twitter\.com/\S+", re.I)
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_NON_ALPHA = re.compile(r"[^a-z\s]")
_WS = re.compile(r"\s+")

# Dateline such as "WASHINGTON (Reuters) - " or "BERLIN, Dec 12 (Reuters) -"
_REUTERS_DATELINE = re.compile(r"^[^()]{0,120}?\(\s*reuters\s*\)\s*[-\u2013\u2014:]*\s*", re.I)
_REUTERS_WORD = re.compile(r"\breuters?\b", re.I)
# publisher boilerplate that only one of the two classes carries
_BOILERPLATE = [
    re.compile(r"21st\s+century\s+wire\s+says", re.I),
    re.compile(r"\b21wire\b", re.I),
    re.compile(r"featured\s+image(?:\s+via)?", re.I),
    re.compile(r"\bgetty\s+images?\b", re.I),
    re.compile(r"\bimage\s+via\b", re.I),
    re.compile(r"\(\s*video\s*\)", re.I),
    re.compile(r"\bphoto\s+by\b", re.I),
    re.compile(r"\bscreenshot\b", re.I),
]


# ------------------------------------------------------------ stop-words
class StopwordManager:
    """Admin-editable stop-word list persisted in data/stopwords.txt."""

    def __init__(self, path: Path = STOPWORDS_FILE):
        self.path = path
        self._words: set[str] = set()
        self.reload()

    def reload(self) -> None:
        self._words = (
            {w.strip().lower() for w in self.path.read_text(encoding="utf-8").splitlines() if w.strip()}
            if self.path.exists() else set()
        )

    @property
    def words(self) -> set[str]:
        return self._words

    def save(self, words: Iterable[str]) -> None:
        self._words = {w.strip().lower() for w in words if w.strip()}
        self.path.write_text("\n".join(sorted(self._words)) + "\n", encoding="utf-8")


stopwords = StopwordManager()


@lru_cache(maxsize=200_000)
def _stem(token: str) -> str:
    return _stemmer.stem(token)


# --------------------------------------------------------------- steps
def strip_source_artifacts(text: str, level: int = 2) -> str:
    """level 0: nothing | 1: Reuters dateline + word | 2: also publisher boilerplate."""
    if level <= 0:
        return text
    text = _REUTERS_DATELINE.sub("", text, count=1)
    text = _REUTERS_WORD.sub(" ", text)
    if level >= 2:
        for pat in _BOILERPLATE:
            text = pat.sub(" ", text)
    return text


def clean_text(text: str, leakage_level: int = 2) -> str:
    """Everything except stop-words / stemming; returns a normalised string."""
    if not isinstance(text, str):
        return ""
    text = html.unescape(text)
    text = strip_source_artifacts(text, leakage_level)
    text = text.lower()
    text = _HTML_TAG.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _NUMBER.sub(" ", text)          # number normalisation: drop numerals
    text = text.replace("'", "").replace("\u2019", "")   # don't -> dont
    text = _NON_ALPHA.sub(" ", text)       # punctuation removal
    return _WS.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    return text.split()


def preprocess(text: str, leakage_level: int = 2, use_stemming: bool = True,
               remove_stopwords: bool = True) -> str:
    """Full pipeline: raw string -> space-joined processed tokens."""
    tokens = tokenize(clean_text(text, leakage_level))
    if remove_stopwords:
        sw = stopwords.words
        tokens = [t for t in tokens if t not in sw and len(t) > 1]
    else:
        tokens = [t for t in tokens if len(t) > 1]
    if use_stemming:
        tokens = [_stem(t) for t in tokens]
    return " ".join(tokens)


def preprocess_batch(texts: Iterable[str], **kw) -> list[str]:
    """Vectorised entry point used inside the sklearn Pipeline."""
    return [preprocess(t, **kw) for t in texts]
