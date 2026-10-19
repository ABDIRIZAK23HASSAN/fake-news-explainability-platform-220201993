"""Dataset Management Service (FR-2 / 8.3): validation, duplicate detection, versioned import."""
from __future__ import annotations

import hashlib
import io
import re
import threading

import pandas as pd
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import DatasetImport, NewsArticle
from .corpus import ensure_processed
from .logging_service import log_event
from .similar import index as similarity_index
from .training import REQUIRED_COLUMNS, normalise_label

MIN_ARTICLE_WORDS = 5
INSERT_CHUNK = 1000


class DatasetValidationError(ValueError):
    pass


def read_csv_bytes(raw: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=enc, dtype=str, keep_default_na=False)
            break
        except UnicodeDecodeError:
            continue
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            raise DatasetValidationError(f"The file is not a valid CSV: {e}")
    else:
        raise DatasetValidationError("Could not decode the file. Please save it as UTF-8.")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def check_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        hint = ""
        if missing == ["label"]:
            hint = " (raw True.csv / Fake.csv have no label column - add label=Real / label=Fake)"
        raise DatasetValidationError(
            f"Dataset validation failed: missing required column(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}.{hint}")
    if df.empty:
        raise DatasetValidationError("Dataset validation failed: the file contains no rows.")


def content_hash(title: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", f"{title}. {text}".strip().lower())
    return hashlib.sha256(norm.encode()).hexdigest()


def analyse(df: pd.DataFrame, existing_hashes: set[str]) -> dict:
    """Splits rows into valid / invalid / duplicate. Returns the valid frame + counters."""
    check_columns(df)
    df = df[REQUIRED_COLUMNS].copy()
    for c in ("title", "text", "subject", "date"):
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["label_int"] = df["label"].map(normalise_label)
    reasons: dict[str, int] = {}

    def bad(mask, reason):
        n = int(mask.sum())
        if n:
            reasons[reason] = reasons.get(reason, 0) + n
        return mask

    invalid = (bad(df["label_int"].isna(), "invalid label (use Fake/Real or 0/1)")
               | bad(df["text"].str.split().str.len().fillna(0) < MIN_ARTICLE_WORDS,
                     f"text shorter than {MIN_ARTICLE_WORDS} words / empty")
               | bad(df["title"] == "", "empty title")
               | bad(df["subject"] == "", "empty subject"))
    good = df[~invalid].copy()
    good["hash"] = [content_hash(t, x) for t, x in zip(good["title"], good["text"])]
    # same content under two different labels = contradictory -> reject all copies
    conflict_hashes = set(good.groupby("hash")["label_int"].nunique().loc[lambda s: s > 1].index)
    conflict = good["hash"].isin(conflict_hashes)
    if conflict.sum():
        reasons["same article labelled both Fake and Real"] = int(conflict.sum())
    good = good[~conflict]
    dup_in_file = good.duplicated("hash")
    dup_in_db = good["hash"].isin(existing_hashes)
    dups = dup_in_file | dup_in_db
    return {
        "total": len(df),
        "rejected": int(invalid.sum() + conflict.sum()),
        "reject_reasons": reasons,
        "duplicates": int(dups.sum()),
        "duplicates_in_file": int(dup_in_file.sum()),
        "duplicates_in_database": int((dup_in_db & ~dup_in_file).sum()),
        "valid_df": good[~dups],
    }


def preview(df: pd.DataFrame, db: Session, n: int = 10) -> dict:
    existing = {h for (h,) in db.query(NewsArticle.content_hash).all()}
    a = analyse(df, existing)
    sample = df.head(n).copy()
    sample["text"] = sample["text"].str.slice(0, 200)
    return {"columns": list(df.columns), "sample_rows": sample.to_dict("records"),
            **{k: v for k, v in a.items() if k != "valid_df"}, "would_import": len(a["valid_df"])}


def run_import(dataset_id: int, df: pd.DataFrame, source_name: str, user_id: int | None) -> None:
    """Executed in a background thread; progress is written to the DatasetImports row."""
    db = SessionLocal()
    try:
        rec = db.get(DatasetImport, dataset_id)
        existing = {h for (h,) in db.query(NewsArticle.content_hash).all()}
        a = analyse(df, existing)
        valid = a["valid_df"]
        rec.total_records, rec.rejected_records, rec.duplicate_records = a["total"], a["rejected"], a["duplicates"]
        rec.message = ("; ".join(f"{v} rows: {k}" for k, v in a["reject_reasons"].items()) or None)
        db.commit()
        rows = [{"title": r.title, "content": r.text, "subject": r.subject, "publication_date": r.date,
                 "label": "Real" if r.label_int == 1 else "Fake", "source_file": source_name,
                 "dataset_id": dataset_id, "content_hash": r.hash}
                for r in valid.itertuples()]
        for i in range(0, len(rows), INSERT_CHUNK):
            db.bulk_insert_mappings(NewsArticle, rows[i:i + INSERT_CHUNK])
            db.commit()
            rec.imported_records = min(i + INSERT_CHUNK, len(rows))
            rec.progress = int(55 * rec.imported_records / max(len(rows), 1))
            db.commit()

        def prog(done, total):
            rec.progress = 55 + int(44 * done / max(total, 1))
            db.commit()
        ensure_processed(db, progress=prog)        # makes the data immediately usable for training
        similarity_index.mark_dirty()
        rec.imported_records, rec.progress, rec.status = len(rows), 100, "Success"
        db.commit()
        log_event(db, "Import", f"Dataset '{source_name}' imported: {len(rows)} imported, "
                  f"{a['rejected']} rejected, {a['duplicates']} duplicates", user_id)
    except Exception as e:                           # noqa: BLE001
        db.rollback()
        rec = db.get(DatasetImport, dataset_id)
        if rec:
            rec.status, rec.message = "Failed", f"Import failed: {e}"[:1000]
            db.commit()
        log_event(db, "Error", f"Dataset import failed for '{source_name}': {e}", user_id)
    finally:
        db.close()


def start_import(db: Session, df: pd.DataFrame, source_name: str, user_id: int | None,
                 wait: bool = False) -> DatasetImport:
    check_columns(df)                                # structure errors reject the upload immediately
    rec = DatasetImport(dataset_name=source_name, uploaded_by=user_id, status="Processing",
                        total_records=len(df))
    db.add(rec); db.commit(); db.refresh(rec)
    t = threading.Thread(target=run_import, args=(rec.dataset_id, df, source_name, user_id), daemon=True)
    t.start()
    if wait:
        t.join()
        db.refresh(rec)
    return rec
