#!/usr/bin/env python3
"""Pick demo articles for the defense from the HELD-OUT test split (articles the model never saw).

Reproduces the exact 80/20 split used by the admin training job (articles ordered by id,
stratified, seed 42), then runs the ACTIVE model on the test part and saves:
  2 correctly classified Fake, 2 correctly classified Real, and the most confident MISTAKE.
Output: docs/demo_articles/*.txt and docs/demo_articles/README.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import numpy as np
import pandas as pd

from app.database import SessionLocal
from app.models import NewsArticle
from app.services.prediction import get_active_model, registry
from app.services.training import split_dataset

OUT = ROOT / "docs" / "demo_articles"; OUT.mkdir(parents=True, exist_ok=True)
db = SessionLocal()
rows = db.query(NewsArticle.news_id, NewsArticle.label, NewsArticle.processed_text).order_by(NewsArticle.news_id).all()
df = pd.DataFrame(rows, columns=["news_id", "label", "text"]); df["y"] = (df.label == "Real").astype(int)
df = df[df.text.fillna("").str.len() > 0]
_, te = split_dataset(df)                       # identical call to model_mgmt._train_job
model = get_active_model(db); pipe = registry.get_pipeline(model)

arts = {a.news_id: a for a in db.query(NewsArticle).filter(NewsArticle.news_id.in_(te.news_id.tolist()))}
te = te[te.news_id.map(lambda i: 120 <= len(arts[i].content.split()) <= 450)].copy()      # readable length
te["p_real"] = pipe.predict_proba([f"{arts[i].title}. {arts[i].content}" for i in te.news_id])[:, 1]
te["pred"] = (te.p_real >= 0.5).astype(int); te["conf"] = np.where(te.pred == 1, te.p_real, 1 - te.p_real)
rng = np.random.RandomState(3)

def pick(mask, n=1, hard=False):
    sub = te[mask]
    if hard:    # prefer cases the model finds less obvious (more interesting to explain)
        sub = sub[(sub.conf > 0.6) & (sub.conf < 0.97)] if ((sub.conf > 0.6) & (sub.conf < 0.97)).any() else sub
    return sub.iloc[rng.permutation(len(sub))[:n]]

sel = [("fake_1", pick((te.y == 0) & (te.pred == 0), 1)), ("fake_2", pick((te.y == 0) & (te.pred == 0), 1, True)),
       ("real_1", pick((te.y == 1) & (te.pred == 1), 1)), ("real_2", pick((te.y == 1) & (te.pred == 1), 1, True))]
wrong = te[te.y != te.pred].sort_values("conf", ascending=False)
if len(wrong): sel.append(("mistake", wrong.head(1)))

lines = [f"# Demo articles (held-out test split)\n\nActive model when generated: **{model.model_name}**. "
         "None of these articles was used to train it. Paste the text (or upload the .txt) into the Analyze page.\n",
         "| file | true label (dataset) | model says | confidence | note |", "|---|---|---|---|---|"]
for name, d in sel:
    for r in d.itertuples():
        a = arts[r.news_id]
        (OUT / f"{name}.txt").write_text(f"{a.title}\n\n{a.content}\n", encoding="utf-8")
        note = "model is WRONG - good for discussing limits" if r.y != r.pred else "correct"
        lines.append(f"| {name}.txt | {a.label} | {'Real' if r.pred else 'Fake'} | {r.conf:.1%} | {note} |")
lines.append(f"\nTest-set size: {len(te)} articles considered here; test accuracy on them: {(te.y == te.pred).mean():.2%}.")
(OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
