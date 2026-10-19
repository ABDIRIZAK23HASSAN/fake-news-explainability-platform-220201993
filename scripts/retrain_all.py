#!/usr/bin/env python3
"""Retrain every existing model in place on the current dataset (keeps ids and the active model)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.database import SessionLocal
from app.models import MLModel
from app.services import model_mgmt

db = SessionLocal()
for m in db.query(MLModel).order_by(MLModel.model_id).all():
    before = m.accuracy
    model_mgmt.start_training(db, m, None, wait=True); db.refresh(m)
    print(f"model {m.model_id} {m.algorithm}: status={m.status} accuracy {before:.4f} -> {m.accuracy:.4f}", flush=True)
