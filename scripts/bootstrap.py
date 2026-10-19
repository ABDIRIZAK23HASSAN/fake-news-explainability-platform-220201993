#!/usr/bin/env python3
"""One-command setup for a fresh installation.

    python scripts/bootstrap.py --data /path/to/folder-with-Fake.csv-and-True.csv

What it does (all through the same services the admin panel uses):
  1. creates the tables and the administrator (ADMIN_EMAIL / ADMIN_PASSWORD from .env)
  2. imports Fake.csv (label=Fake) and True.csv (label=Real) with validation + duplicate removal
  3. trains the requested algorithms, prints their metrics
  4. activates one model (default: logistic_regression - exact SHAP support, accuracy within
     noise of the best model) so the platform is ready to use
  5. optionally creates a demo user
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd

from app.database import Base, SessionLocal, engine
from app.main import seed_admin
from app.models import DatasetImport, MLModel, User, UserSetting
from app.security import hash_password
from app.services import dataset as dsvc
from app.services import model_mgmt
from app.services.training import ALGORITHMS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder containing Fake.csv and True.csv")
    ap.add_argument("--algorithms", nargs="*", default=["logistic_regression", "linear_svm", "naive_bayes",
                                                        "random_forest", "xgboost"])
    ap.add_argument("--vectorizer", default="tfidf_bigram")
    ap.add_argument("--activate", default="logistic_regression", help="algorithm to activate afterwards")
    ap.add_argument("--demo-user", action="store_true", help="create demo@example.com / Demo12345")
    a = ap.parse_args()

    Base.metadata.create_all(engine)
    seed_admin()
    db = SessionLocal()
    data = Path(a.data)

    if db.query(DatasetImport).filter_by(status="Success").count() == 0:
        for fname, label in (("Fake.csv", "Fake"), ("True.csv", "Real")):
            path = data / fname
            if not path.exists():
                sys.exit(f"{path} not found")
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            if "label" not in df.columns:
                df["label"] = label             # the raw files carry the label in their file name
            t0 = time.time()
            rec = dsvc.start_import(db, df, fname, None, wait=True)
            print(f"[import] {fname}: status={rec.status} imported={rec.imported_records} "
                  f"rejected={rec.rejected_records} duplicates={rec.duplicate_records} ({time.time() - t0:.0f}s)")
            if rec.status != "Success":
                sys.exit(f"import failed: {rec.message}")
    else:
        print("[import] dataset already present - skipping")

    for algo in a.algorithms:
        if algo not in ALGORITHMS:
            sys.exit(f"unknown algorithm {algo}")
        if db.query(MLModel).filter_by(algorithm=algo, vectorizer=a.vectorizer, status="Ready").count():
            print(f"[train] {algo}: already trained - skipping")
            continue
        m = model_mgmt.create_model_record(db, algo, a.vectorizer, None)
        model_mgmt.start_training(db, m, None, wait=True)
        db.refresh(m)
        if m.status == "Ready":
            print(f"[train] {algo}: acc={m.accuracy:.4f} prec={m.precision:.4f} rec={m.recall:.4f} "
                  f"f1={m.f1_score:.4f} auc={m.roc_auc:.4f} ({m.training_duration:.0f}s)")
        else:
            print(f"[train] {algo}: FAILED")

    target = db.query(MLModel).filter_by(algorithm=a.activate, status="Ready").order_by(MLModel.model_id.desc()).first()
    if target and not db.query(MLModel).filter_by(is_active=True).count():
        model_mgmt.activate(db, target.model_id, None)
        print(f"[activate] model {target.model_id} ({target.model_name})")

    if a.demo_user and not db.query(User).filter_by(email="demo@example.com").count():
        u = User(first_name="Demo", last_name="User", email="demo@example.com",
                 password=hash_password("Demo12345"), role="User")
        u.settings = UserSetting()
        db.add(u); db.commit()
        print("[demo] created demo@example.com / Demo12345")
    print("[done] platform is ready")


if __name__ == "__main__":
    main()
