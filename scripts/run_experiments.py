#!/usr/bin/env python3
"""Reproducible experiments for the report.  Run stages one at a time:

    python scripts/run_experiments.py prep       # preprocess + cache (slow, 1x)
    python scripts/run_experiments.py baseline   # instructor's train/test as given
    python scripts/run_experiments.py exp_a      # leakage / preprocessing strategies
    python scripts/run_experiments.py exp_b      # feature extraction methods
    python scripts/run_experiments.py exp_c      # model comparison (5 algorithms)

Every stage appends to docs/experiments/results.json, so nothing is lost if a
later stage fails.  Nothing here is hand-typed: report numbers come from this file.
"""
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd
from app.services import training as T
from app.services.preprocessing import preprocess

DATA = Path(sys.argv[sys.argv.index("--data") + 1]) if "--data" in sys.argv else Path("/mnt/user-data/uploads")
CACHE = ROOT / "backend" / "storage" / "cache"
OUT = ROOT / "docs" / "experiments"
CACHE.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
RESULTS = OUT / "results.json"

# name -> preprocess kwargs
VARIANTS = {
    "L0_no_leakage_removal": dict(leakage_level=0),
    "L1_reuters_removed":    dict(leakage_level=1),
    "L2_full_removal":       dict(leakage_level=2),
    "L2_no_stemming":        dict(leakage_level=2, use_stemming=False),
    "L2_keep_stopwords":     dict(leakage_level=2, remove_stopwords=False),
}


def log_result(key, value):
    data = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    data[key] = value
    RESULTS.write_text(json.dumps(data, indent=2))
    print(f"[saved] {key}")


def load_split():
    f = pd.read_csv(DATA / "Fake.csv"); f["label"] = 0
    t = pd.read_csv(DATA / "True.csv"); t["label"] = 1
    raw = pd.concat([f, t], ignore_index=True)
    ds = T.build_dataset(raw)
    tr, te = T.split_dataset(ds)
    return raw, ds, tr.reset_index(drop=True), te.reset_index(drop=True)


def cached(name, tr, te):
    p = CACHE / f"prep_{name}.pkl"
    if p.exists():
        return pd.read_pickle(p)
    t0 = time.time()
    kw = VARIANTS[name]
    out = {"train": T.preprocess_parallel(tr["content"], processes=1, **kw),
           "test": T.preprocess_parallel(te["content"], processes=1, **kw)}
    pd.to_pickle(out, p)
    print(f"  prep {name}: {time.time()-t0:.0f}s")
    return out


def short(m):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}


def stage_prep(args):
    raw, ds, tr, te = load_split()
    log_result("dataset", {"raw_rows": len(raw), "after_cleaning": len(ds),
                           "train": len(tr), "test": len(te),
                           "fake": int((ds.label == 0).sum()), "real": int((ds.label == 1).sum())})
    for name in (args.variants or VARIANTS):
        cached(name, tr, te)


def stage_baseline(args):
    """Instructor's own train.csv/test.csv (already stemmed, still contains 'reuter')."""
    tr = pd.read_csv(DATA / "train.csv"); te = pd.read_csv(DATA / "test.csv")
    res = {}
    for label, drop in [("as_given", False), ("reuter_token_removed", True)]:
        a, b = tr.combined.fillna(""), te.combined.fillna("")
        if drop:
            a = a.str.replace(r"\breuter\b", " ", regex=True); b = b.str.replace(r"\breuter\b", " ", regex=True)
        _, m = T.train_and_evaluate("logistic_regression", a, tr.label, b, te.label, "tfidf")
        res[label] = short(m); print(label, res[label]["accuracy"], res[label]["f1"])
    # how many test rows also appear (exactly) in train
    res["train_test_exact_overlap"] = len(set(tr.combined) & set(te.combined))
    log_result("baseline_instructor_split", res)


def stage_exp_a(args):
    _, _, tr, te = load_split()
    res = {}
    for name in VARIANTS:
        c = cached(name, tr, te)
        _, m = T.train_and_evaluate("logistic_regression", c["train"], tr.label, c["test"], te.label, "tfidf")
        res[name] = short(m); print(name, res[name]["accuracy"], res[name]["f1"])
    log_result("exp_a_preprocessing_strategies", res)


def stage_exp_b(args):
    _, _, tr, te = load_split()
    c = cached("L2_full_removal", tr, te)
    res = {}
    for kind in ["bow", "tfidf", "tfidf_bigram"]:
        _, m = T.train_and_evaluate("logistic_regression", c["train"], tr.label, c["test"], te.label, kind)
        res[kind] = short(m); print(kind, res[kind]["accuracy"], res[kind]["f1"], res[kind]["training_seconds"])
    log_result("exp_b_feature_extraction", res)


def stage_exp_c(args):
    _, _, tr, te = load_split()
    c = cached("L2_full_removal", tr, te)
    res = {}
    for algo in (args.algos or T.ALGORITHMS):
        _, m = T.train_and_evaluate(algo, c["train"], tr.label, c["test"], te.label, args.vectorizer)
        res[algo] = short(m); print(algo, res[algo]["accuracy"], res[algo]["f1"], res[algo]["training_seconds"])
        log_result("exp_c_model_comparison", {**(json.loads(RESULTS.read_text()).get("exp_c_model_comparison", {})), algo: res[algo],
                                              "_vectorizer": args.vectorizer})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prep", "baseline", "exp_a", "exp_b", "exp_c"])
    ap.add_argument("--data")
    ap.add_argument("--vectorizer", default="tfidf_bigram")
    ap.add_argument("--algos", nargs="*")
    ap.add_argument("--variants", nargs="*")
    a = ap.parse_args()
    {"prep": stage_prep, "baseline": stage_baseline, "exp_a": stage_exp_a,
     "exp_b": stage_exp_b, "exp_c": stage_exp_c}[a.stage](a)
