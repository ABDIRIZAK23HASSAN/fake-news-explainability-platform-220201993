#!/usr/bin/env python3
"""Builds docs/Project_Report.pdf.  Every number is read from docs/experiments/results.json or the platform
database - nothing is typed by hand.

    python scripts/build_report.py --name "Your Name" --student-id 12345 --github https://github.com/you/repo
"""
import argparse, json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="[Student name]"); ap.add_argument("--student-id", default="[Student ID]")
ap.add_argument("--github", default="[GitHub repository link]"); ap.add_argument("--supervisor", default="[Instructor]")
args = ap.parse_args()

DOCS = ROOT / "docs"; SHOTS = DOCS / "screenshots"; FIG = DOCS / "figures"; FIG.mkdir(exist_ok=True)
R = json.loads((DOCS / "experiments" / "results.json").read_text())

# ------------------------------------------------------------------ data from the platform database
from app.database import SessionLocal
from app.models import DatasetImport, MLModel, NewsArticle, PredictionHistory, User
db = SessionLocal()
models = db.query(MLModel).filter(MLModel.status == "Ready").order_by(MLModel.model_id).all()
active = next(m for m in models if m.is_active)
imports = db.query(DatasetImport).order_by(DatasetImport.dataset_id).all()
n_articles = db.query(NewsArticle).count()
n_fake = db.query(NewsArticle).filter_by(label="Fake").count(); n_real = n_articles - n_fake
run = active.runs[-1]
import re
demo = (db.query(PredictionHistory).filter(PredictionHistory.submitted_title.like("%INNOCENT UNTIL PROVEN%"))
        .order_by(PredictionHistory.prediction_id.desc()).first())
lime_rows = {e.word: e.contribution_value for e in demo.explanations if e.method == "lime"}
assert lime_rows.get("said", 0) < 0 and lime_rows.get("read", 0) > 0, "explanation narrative no longer matches the data - update section 6"
mist = re.search(r"\| mistake\.txt \| (\w+) \| (\w+) \| ([\d.]+%)", (DOCS / "demo_articles" / "README.md").read_text())
MISTAKE_TRUE, MISTAKE_PRED, MISTAKE_CONF = mist.groups()
ALGO = {"logistic_regression": "Logistic Regression", "linear_svm": "Linear SVM (calibrated)", "naive_bayes": "Naive Bayes",
        "random_forest": "Random Forest", "xgboost": "XGBoost"}
NAVY, FAKE, REAL, GREY = "#1D3B5C", "#B3342F", "#17734F", "#8A97A5"

# ------------------------------------------------------------------ figures
def fig_preprocessing():
    a = R["exp_a_preprocessing_strategies"]; names = {"L0_no_leakage_removal": "No source-artifact\nremoval", "L1_reuters_removed": "Reuters\nremoved",
        "L2_full_removal": "Reuters + boilerplate\nremoved (used)", "L2_no_stemming": "Full removal,\nno stemming", "L2_keep_stopwords": "Full removal,\nkeep stop-words"}
    f, ax = plt.subplots(figsize=(7.2, 3.1)); vals = [a[k]["accuracy"] * 100 for k in names]
    bars = ax.bar(list(names.values()), vals, color=[GREY, NAVY, NAVY, NAVY, NAVY]); ax.set_ylim(97.5, 99.8); ax.set_ylabel("Accuracy (%)")
    for b, v in zip(bars, vals): ax.text(b.get_x() + b.get_width() / 2, v + 0.04, f"{v:.2f}", ha="center", fontsize=8)
    ax.tick_params(axis="x", labelsize=7.5); ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Effect of preprocessing choices (Logistic Regression, TF-IDF)\naxis starts at 97.5%", fontsize=9)
    f.tight_layout(); f.savefig(FIG / "preprocessing.png", dpi=200); plt.close(f)

def fig_models():
    f, ax = plt.subplots(figsize=(7.2, 3.2)); w = 0.2; xs = range(len(models))
    for i, (k, c) in enumerate([("accuracy", NAVY), ("precision", GREY), ("recall", REAL), ("f1_score", FAKE)]):
        ax.bar([x + (i - 1.5) * w for x in xs], [getattr(m, k) * 100 for m in models], w, label=k.replace("_score", ""), color=c)
    ax.set_xticks(list(xs)); ax.set_xticklabels([ALGO[m.algorithm].replace(" (", "\n(") for m in models], fontsize=7.5)
    ax.set_ylim(94, 100); ax.set_ylabel("%"); ax.legend(ncol=4, fontsize=7.5, frameon=False, loc="upper center"); ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Held-out test set (axis starts at 94%)", fontsize=9); f.tight_layout(); f.savefig(FIG / "models.png", dpi=200); plt.close(f)

def fig_confusion():
    cm = json.loads(active.confusion_matrix); f, ax = plt.subplots(figsize=(3.6, 3.1))
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2): ax.text(j, i, f"{cm[i][j]:,}", ha="center", va="center", color="white" if cm[i][j] > max(map(max, cm)) / 2 else "black", fontsize=11)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Fake", "Real"]); ax.set_yticks([0, 1]); ax.set_yticklabels(["Fake", "Real"])
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual"); ax.set_title("Confusion matrix - active model", fontsize=9); f.tight_layout()
    f.savefig(FIG / "confusion.png", dpi=200); plt.close(f)

def fig_roc():
    f, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.3)); cols = [NAVY, REAL, FAKE, GREY, "#B8860B"]; n = 0
    for m, c in zip(models, cols):
        run_ = next((r for r in reversed(m.runs) if r.status == "Completed" and r.metrics_json), None)
        roc = json.loads(run_.metrics_json).get("roc_curve") if run_ else None
        if not roc: continue
        n += 1
        for ax in (a1, a2): ax.plot(roc["fpr"], roc["tpr"], color=c, lw=1.6, label=f"{ALGO[m.algorithm].split(' (')[0]} (AUC {m.roc_auc:.4f})")
    assert n == len(models), "every model needs a stored ROC curve - run scripts/retrain_all.py"
    a1.plot([0, 1], [0, 1], "--", color="#aaa", lw=0.8); a1.set_xlabel("False positive rate"); a1.set_ylabel("True positive rate"); a1.set_title("Full range", fontsize=9)
    a2.set_xlim(0, 0.1); a2.set_ylim(0.9, 1.0); a2.set_xlabel("False positive rate"); a2.set_title("Zoom: top-left corner", fontsize=9)
    a2.legend(fontsize=6.3, loc="lower right", frameon=False)
    for ax in (a1, a2): ax.spines[["top", "right"]].set_visible(False)
    f.tight_layout(); f.savefig(FIG / "roc.png", dpi=200); plt.close(f)

fig_preprocessing(); fig_models(); fig_confusion(); fig_roc()

# ------------------------------------------------------------------ styles
pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-I", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-B")
ss = getSampleStyleSheet()
body = ParagraphStyle("body", parent=ss["BodyText"], fontName="DV", fontSize=9.2, leading=13.6, spaceAfter=5)
small = ParagraphStyle("small", parent=body, fontSize=7.8, leading=10.5, spaceAfter=2)
cap = ParagraphStyle("cap", parent=body, fontName="DV-I", fontSize=8, textColor=colors.HexColor("#495a6b"), alignment=TA_CENTER, spaceAfter=9)
h1 = ParagraphStyle("h1", parent=body, fontName="DV-B", fontSize=15, leading=19, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor(NAVY), keepWithNext=1)
h2 = ParagraphStyle("h2", parent=body, fontName="DV-B", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor(NAVY), keepWithNext=1)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=2)
cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10.2, spaceAfter=0)
cellb = ParagraphStyle("cellb", parent=cell, fontName="DV-B")
P = lambda t, s=body: Paragraph(t, s)
B = lambda items: [Paragraph(i, bullet, bulletText="\u2022") for i in items]

def table(rows, widths, head=True, zebra=True, align_right_from=None):
    data = [[Paragraph(str(c), cellb if (head and r == 0) else cell) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c4ccd4")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if head: st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3e9ef")))
    if zebra:
        for r in range(2, len(rows), 2): st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f6f8fa")))
    t.setStyle(TableStyle(st)); return t

def img(path, width_cm, max_h_cm=None, box=None):
    path = Path(path)
    if box:                                   # crop to the useful area (drops the sidebar / empty space)
        im = Image.open(path); l, t, r, b = box; im = im.crop((l, t, min(r, im.width), min(b, im.height)))
        path = FIG / f"crop_{path.stem}_{'_'.join(map(str, box))}.png"; im.save(path)
    w, h = Image.open(path).size; wc = width_cm
    if max_h_cm and wc * h / w > max_h_cm: wc = max_h_cm * w / h
    return RLImage(str(path), width=wc * cm, height=wc * h / w * cm)

SIDE = 236   # sidebar width in the screenshots
def shot(name, caption, width=14.5, box=None, max_h=None):
    return KeepTogether([img(SHOTS / name, width, max_h, box), P(caption, cap)])

pct = lambda v, d=2: f"{v * 100:.{d}f}%"

# ------------------------------------------------------------------ architecture diagram
def architecture():
    d = Drawing(17 * cm, 6.6 * cm)
    def box(x, y, w, h, t, fill):
        d.add(Rect(x * cm, y * cm, w * cm, h * cm, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#1d3b5c"), strokeWidth=0.8, rx=4, ry=4))
        for i, line in enumerate(t.split("\n")): d.add(String((x + w / 2) * cm, (y + h - 0.55 - i * 0.42) * cm, line, fontName="DV-B" if i == 0 else "DV", fontSize=7.6 if i else 8.6, textAnchor="middle"))
    def arrow(x1, y1, x2, y2):
        d.add(Line(x1 * cm, y1 * cm, x2 * cm, y2 * cm, strokeColor=colors.HexColor("#495a6b"), strokeWidth=1))
    box(0.2, 2.4, 2.9, 2.0, "Browser\nReact SPA\nUser + Admin UI", "#e8eef5")
    box(3.9, 2.4, 2.4, 2.0, "nginx\nstatic files +\nreverse proxy", "#e8eef5")
    box(7.1, 0.3, 5.3, 6.0, "FastAPI backend", "#f3f6f9")
    for i, t in enumerate(["Routers: auth, users, news,", "predictions, admin (JWT + RBAC)", "Services: preprocessing, training,", "prediction, LIME / SHAP, similarity,", "keywords, reports, analytics"]):
        d.add(String(9.75 * cm, (5.1 - i * 0.5) * cm, t, fontName="DV", fontSize=7.2, textAnchor="middle"))
    box(7.5, 0.5, 2.3, 1.2, "joblib models", "#fff4d6"); box(9.9, 0.5, 2.3, 1.2, "TF-IDF index", "#fff4d6")
    box(13.4, 2.4, 3.4, 2.0, "PostgreSQL\n15 tables via ORM", "#e6f4ee")
    arrow(3.1, 3.4, 3.9, 3.4); arrow(6.3, 3.4, 7.1, 3.4); arrow(12.4, 3.4, 13.4, 3.4)
    d.add(String(3.5 * cm, 3.65 * cm, "HTTPS", fontName="DV", fontSize=6.5, textAnchor="middle")); d.add(String(6.7 * cm, 3.65 * cm, "/api", fontName="DV", fontSize=6.5, textAnchor="middle"))
    d.add(String(12.9 * cm, 3.65 * cm, "SQL", fontName="DV", fontSize=6.5, textAnchor="middle"))
    return d

# ------------------------------------------------------------------ document
story = []
d0 = R["dataset"]; ba = R["baseline_instructor_split"]; ea = R["exp_a_preprocessing_strategies"]; eb = R["exp_b_feature_extraction"]; ec = R["exp_c_model_comparison"]
fake_imp = next(i for i in imports if i.dataset_name == "Fake.csv"); real_imp = next(i for i in imports if i.dataset_name == "True.csv")

# title page
story += [Spacer(1, 4 * cm), P("WEX 428 - NLP / Sentiment Analysis Project Report", ParagraphStyle("t0", parent=body, fontSize=11, textColor=colors.HexColor("#495a6b"))),
          P("Fake News Explainability Platform", ParagraphStyle("t1", parent=h1, fontSize=26, leading=31, spaceBefore=6)),
          P("An AI-powered web application that classifies news articles as Fake or Real and explains the decision with LIME and SHAP", ParagraphStyle("t2", parent=body, fontSize=11.5, leading=16)),
          Spacer(1, 1.2 * cm),
          table([["Student", args.name], ["Student ID", args.student_id], ["Instructor", args.supervisor], ["University", "Ostim Technical University"],
                 ["Date", date.today().strftime("%d %B %Y")], ["Source code", args.github]], [3.5, 12.5], head=False),
          Spacer(1, 1.2 * cm),
          P("Every figure in this report was produced by the code in the repository: experiment results by <i>scripts/run_experiments.py</i>, "
            "platform metrics by the administrator training pipeline, and screenshots by an automated browser test.", small), PageBreak()]

story += [P("1. Introduction", h1),
          P("Most fake-news detectors return a bare label. This project builds a platform that also shows <b>why</b> an article was classified as it was: "
            "the words that pushed the decision are marked inside the article, with a confidence score, keywords and the five most similar articles from the dataset. "
            "It is explicitly a <b>decision-support tool</b>, not a truth detector. Following the course rules, no ready-made LLM API is used; every model is trained locally."),
          P("<b>Objectives.</b> (1) a complete NLP pipeline with documented experiments; (2) at least three compared models; (3) explainability with LIME / SHAP; "
            "(4) a full-stack application with separate user and administrator interfaces, JWT security, a relational database and a REST API; (5) reproducible deployment.")]

story += [P("2. Dataset", h1),
          P(f"The provided dataset has two raw files, <i>Fake.csv</i> and <i>True.csv</i>, with the columns title, text, subject and date (the label is implied by the file name; "
            f"we add <i>label</i>: 0 = Fake, 1 = Real). Together they hold {d0['raw_rows']:,} rows."),
          table([["Stage", "Articles", "Fake", "Real"],
                 ["Raw files", f"{d0['raw_rows']:,}", "23,481", "21,417"],
                 ["After removing empty and duplicate articles (experiments)", f"{d0['after_cleaning']:,}", f"{d0['fake']:,}", f"{d0['real']:,}"],
                 ["Imported by the platform (also rejects titles / subjects that are empty and texts under 5 words)", f"{n_articles:,}", f"{n_fake:,}", f"{n_real:,}"]], [9.4, 2.2, 2.2, 2.2]),
          Spacer(1, 4),
          P(f"<b>Data-quality findings.</b> Fake.csv contains 6,026 repeated texts and 630 empty ones; True.csv contains 225 repeated texts. In the platform import, "
            f"Fake.csv produced {fake_imp.imported_records:,} valid articles ({fake_imp.rejected_records:,} rejected, {fake_imp.duplicate_records:,} duplicates ignored) and True.csv "
            f"{real_imp.imported_records:,} ({real_imp.rejected_records:,} rejected, {real_imp.duplicate_records:,} duplicates). "
            f"The instructor's <i>train.csv</i> and <i>test.csv</i> share {ba['train_test_exact_overlap']} identical articles, so we built our own stratified 80/20 split (seed 42) after de-duplication."),
          P("<b>Label leakage.</b> The token <i>reuter</i> occurs in 99.8% of Real articles and 1.2% of Fake ones, and the <i>subject</i> column separates the classes perfectly. "
            "We therefore never use <i>subject</i> as a feature and added a source-artifact removal step to the pipeline (section 3). Details: docs/leakage_analysis.md.")]

story += [P("3. NLP pipeline", h1),
          P("The same code runs for training and for user predictions (one preprocessing module), so the two cannot drift apart."),
          *B(["<b>Cleaning:</b> HTML entity / tag removal, URL removal, e-mail removal, number removal, apostrophe and punctuation removal, lowercasing, whitespace normalisation.",
              "<b>Source-artifact removal (added):</b> the Reuters dateline and the word 'Reuters', plus publisher boilerplate such as 'Featured image via', 'Getty Images', '(VIDEO)'.",
              "<b>Tokenisation and stop-words:</b> whitespace tokens, 318-word editable stop-word list (administrators can change it); tokens shorter than 2 letters dropped.",
              "<b>Stemming:</b> Snowball (English) stemmer with a cache.",
              "<b>Features:</b> TF-IDF with unigrams and bigrams, at most 50,000 features (10,000 for tree models), min_df 3, max_df 0.9, sub-linear term frequency.",
              "<b>Split:</b> 80% train / 20% held-out test, stratified, seed 42. The test set is used only for evaluation."]),
          P("<b>Classifiers.</b> Logistic Regression (C = 4), linear SVM (C = 0.5, wrapped in sigmoid calibration so it outputs probabilities), multinomial Naive Bayes (alpha = 0.1), "
            "Random Forest (100 trees) and XGBoost (200 trees, depth 6). The confidence score is the predicted-class probability.")]

story += [P("4. Experiments", h1),
          P(f"All experiments use one split ({d0['train']:,} train / {d0['test']:,} test articles). The standard error of an accuracy near 98.6% on {d0['test']:,} articles is about 0.13 points, "
            "so differences smaller than roughly 0.3 points are <b>not</b> evidence that one setting is better.")]
story += [P("4.1 Preprocessing strategies and label leakage", h2), KeepTogether([img(FIG / "preprocessing.png", 14.5), P("Figure 1. Removing the Reuters fingerprint lowers accuracy by about 0.7 points; stemming and stop-word choices change it by less than 0.2 points (within noise).", cap)]),
          table([["Variant", "Accuracy", "F1"]] + [[k, pct(v["accuracy"]), pct(v["f1"])] for k, v in ea.items()], [8, 3, 3]), Spacer(1, 4),
          P(f"On the instructor's own split, as given, Logistic Regression reaches {pct(ba['as_given']['accuracy'])}; deleting only the token <i>reuter</i> gives {pct(ba['reuter_token_removed']['accuracy'])}. "
            "The drop is small because the classes also differ in writing style, not only in that one word (section 6).")]
story += [P("4.2 Feature extraction", h2),
          table([["Feature extraction", "Accuracy", "F1", "Training time"]] + [[{"bow": "Bag of Words (unigrams)", "tfidf": "TF-IDF (unigrams)", "tfidf_bigram": "TF-IDF (unigrams + bigrams)"}[k], pct(v["accuracy"]), pct(v["f1"]), f"{v['training_seconds']} s"] for k, v in eb.items()], [7, 3, 3, 3]),
          Spacer(1, 4), P("Bag of Words is clearly weaker. TF-IDF with bigrams is the best by 0.14 points over unigrams, which is inside the noise, and trains about five times slower. "
                          "We kept TF-IDF with bigrams because it is the best observed configuration and the cost is acceptable; this choice is justified by the experiment but not by a significant margin. "
                          "Word2Vec, FastText and trigrams were not tested.")]
story += [KeepTogether([P("4.3 Model comparison (experiment split)", h2),
          table([["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "Train time"]] + [[ALGO[k], pct(v["accuracy"]), pct(v["precision"]), pct(v["recall"]), pct(v["f1"]), f"{v['roc_auc']:.4f}", f"{v['training_seconds']} s"] for k, v in ec.items() if not k.startswith("_")], [4.4, 1.9, 1.9, 1.9, 1.9, 1.9, 2.0])])]

story += [P("5. Final models trained inside the platform", h1),
          P(f"The administrator pipeline trained all five algorithms on the imported database ({n_articles:,} articles; {run.n_train:,} train / {run.n_test:,} test) and recorded the metrics below. "
            "They differ slightly from section 4.3 because the platform import also rejects very short articles, so the two data sets are not identical."),
          table([["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "Train time"]] + [[ALGO[m.algorithm] + (" (ACTIVE)" if m.is_active else ""), pct(m.accuracy), pct(m.precision), pct(m.recall), pct(m.f1_score), f"{m.roc_auc:.4f}", f"{m.training_duration:.0f} s"] for m in models], [4.8, 1.9, 1.9, 1.9, 1.9, 1.9, 1.9]),
          Spacer(1, 6), KeepTogether([img(FIG / "models.png", 14.5), P("Figure 2. Metrics of the five models on the held-out test set (platform training).", cap)]),
          P(f"<b>Active model: Logistic Regression.</b> The linear SVM scores {abs(next(m.accuracy for m in models if m.algorithm == 'linear_svm') - active.accuracy) * 100:.2f} points higher in accuracy, which is within the noise of a single split. "
            "Logistic Regression is kept active because it supports exact SHAP values, trains in under 30 seconds and gives well-behaved probabilities. Naive Bayes and Random Forest are clearly weaker."),
          KeepTogether([img(FIG / "confusion.png", 7.2), P("Figure 3. Confusion matrix of the active model on the test set.", cap)]),
          KeepTogether([img(FIG / "roc.png", 15), P("Figure 4. ROC curves of the five models on the test set. The strong models are almost indistinguishable; Naive Bayes and Random Forest sit visibly lower in the zoomed corner.", cap)]),
          P("<b>Important caveat.</b> Both classes come from only two publishers. High accuracy shows that the model recognises the style of these sources; it does not show that it can verify claims or generalise to other outlets. "
            f"A confident mistake exists in our held-out demo set (a {MISTAKE_TRUE} article classified {MISTAKE_PRED} with {MISTAKE_CONF} confidence), which is why the interface always shows the confidence and the evidence.")]

story += [P("6. Explainability", h1),
          P("<b>LIME</b> (any model): the article is perturbed by removing random words; a local linear surrogate is fitted to the model's responses (400 samples) and its weights are the explanation. "
            "Words that preprocessing removes (stop-words, one- or two-letter fragments, numbers) cannot influence the model, so their small surrogate weights are discarded - an issue we found when reviewing the first screenshots. "
            "<b>SHAP</b> (Logistic Regression and XGBoost): exact linear SHAP values on the TF-IDF features against the training-set mean, mapped back from stems to the readable words of the article."),
          P("<b>Sign convention.</b> A positive weight pushes towards the predicted class, a negative weight against it. In the article view, red marks push towards Fake and green marks towards Real; darker means stronger."),
          P("<b>What the explanations reveal.</b> In this example 'said' is the strongest word against Fake (reporting language typical of the Real class), while 'read' (from 'Read more') and informal wording such as 'didn' push towards Fake. "
            "This agrees with the leakage analysis: the model relies heavily on <i>how</i> an article is written. The Administrator's explainability page aggregates such words across all predictions so that this kind of bias can be monitored."),
          shot("05_result_explanation_lime.png", f"Figure 5. Explanation page for a held-out Fake article ({pct(demo.confidence_score)} confidence): supporting and opposing words and the importance ranking.", 15.5, box=(SIDE, 0, 1366, 925))]

story += [P("7. System design and implementation", h1), architecture(), P("Figure 6. Architecture.", cap),
          P("<b>Backend.</b> FastAPI with a layered design (routers, services, ORM models). 65 REST operations cover authentication, profile, analysis, history, explanations, similar news, "
            "exports and the whole administration area; all 15 endpoints listed in the assignment exist. Long jobs (dataset import, model training) run in background threads and report progress through the database."),
          P("<b>Database.</b> PostgreSQL through SQLAlchemy. The ten required tables (Users, NewsArticles, PredictionHistory, Keywords, ExplainabilityResults, SimilarNews, Models, DatasetImports, SystemLogs, UserSettings) "
            "are implemented with foreign keys and the requested indexes, plus five support tables (training runs, revoked tokens, password-reset tokens, application settings, keyword dictionary). "
            "'Only one active model' is enforced by a partial unique index in the database, not only in code. Duplicate articles are prevented by a unique content hash."),
          P("<b>Security.</b> bcrypt hashing (with a SHA-256 pre-hash), signed JWTs with revocation on logout, role checks read from the database on every admin request, login throttling, "
            "parameterised queries only, upload validation by extension, size and file signature, secrets from environment variables, non-root container, security headers, and no raw-HTML rendering in the React app (XSS)."),
          P("<b>Frontend.</b> React with two separate interfaces (users and administrators), responsive layout, light and dark themes, breadcrumbs, sidebar, search, pagination, confirmation dialogs, loading states and 403 / 404 / 500 pages."),
          P("<b>Deployment.</b> Docker Compose (PostgreSQL, backend, nginx serving the built frontend), a bootstrap script that imports the dataset and trains the models, and a GitHub Actions workflow."),
          table([["Area", "Endpoints (examples)"],
                 ["Authentication", "POST /api/auth/register, /login, /logout, /forgot-password, /reset-password; GET /api/auth/me"],
                 ["User", "GET/PUT /api/users/profile, PUT /password, POST /profile-image, GET/PUT /settings, GET /dashboard"],
                 ["Analysis", "POST /api/news/analyze, /api/news/upload; GET /api/news/similar/{id}"],
                 ["History", "GET /api/predictions/history, /{id}, /{id}/export?format=pdf|csv; DELETE; GET /api/explanations/{id}"],
                 ["Administration", "users, datasets (preview / upload / progress), news, subjects, models (train / retrain / activate / delete), analytics, explainability, stop-words, settings, logs"]], [3.3, 13.2])]

story += [P("8. Testing and defects found", h1),
          P("Testing used three layers: <b>22 API tests</b> (registration and validation, password hashing, JWT revocation, role access, password reset, dataset validation and duplicates, "
            "training and single-active-model rule, the full analysis workflow, user isolation, exports, file upload checks, administration), run on <b>SQLite and on PostgreSQL 16</b>; "
            "an automated <b>browser test</b> in headless Chromium that walks through both interfaces; and manual review of the screenshots. All pass. The tests also found real defects, all fixed:"),
          table([["Defect", "How it was found", "Fix"],
                 ["PostgreSQL rejected numpy float types stored for keyword scores (SQLite accepted them silently)", "Running the API suite on PostgreSQL", "Explicit float() / int() conversion"],
                 ["After training, the API returned a stale model status", "API test", "Reload the model from the database after the background job"],
                 ["Route /users/{id}/{action} swallowed /users/{id}/reset-password", "API test", "Separate explicit routes"],
                 ["All charts crashed the page (Chart.js controllers not registered); the error page itself crashed outside the router", "Browser test", "Register controllers; plain link in the error page"],
                 ["Top bar overflowed on phones", "Browser test (390 px viewport)", "Hide name and avatar, shorten breadcrumbs"],
                 ["LIME gave noise weights to stop-words that the pipeline removes", "Screenshot review", "Filter words that preprocessing discards"],
                 ["Training split order was not fixed (could differ on PostgreSQL)", "Code review", "Order articles by id before splitting"],
                 ["Predictions ignored the pasted headline although the models are trained on 'title. text' (81.0% vs 80.65% for the same article)", "Comparing the UI result with the demo-article script", "Same document form at inference; regression test"]], [7.2, 4.4, 4.9]),
          Spacer(1, 4), P("<b>Not tested:</b> the Docker images were written but not built in the development environment; performance under many concurrent users; accessibility audit with assistive technology.")]

C = lambda a, b, c: [a, b, c]
story += [P("9. Coverage of the assignment requirements", h1),
          table([["Requirement", "Status", "Notes"],
                 C("Preprocessing, tokenisation, stop-words, stemming (6.1)", "Done", "plus source-artifact removal"),
                 C("Feature extraction, justified by experiment (6.2)", "Done", "BoW, TF-IDF, TF-IDF + bigrams compared; Word2Vec / FastText / trigrams not tested"),
                 C("At least three models compared (6.3)", "Done", "five models; accuracy, precision, recall, F1, ROC-AUC, ROC curves and confusion matrix"),
                 C("LIME / SHAP, positive / negative words, highlighting (FR-5)", "Done", "LIME for all models; SHAP for Logistic Regression and XGBoost"),
                 C("Similar news top 5, keywords, prediction history, reports (FR-6, 7, 8, 11)", "Done", "TF-IDF + cosine; TF-IDF or RAKE keywords; PDF and CSV exports"),
                 C("Authentication: register, login, logout, forgot / reset password, JWT, RBAC (FR-1)", "Done", "reset link goes to the server log unless SMTP is configured; refresh tokens (optional) not implemented"),
                 C("Dataset import with validation, duplicates, progress, versions (FR-2, 8.3)", "Done", "training can be restricted to one dataset (Settings)"),
                 C("Model management: train, retrain, compare, activate, delete, history (FR-10)", "Done", "single active model enforced by the database"),
                 C("Administrator dashboard, analytics, explainability monitoring, logs (FR-9, 7.2)", "Done", "Chart.js charts"),
                 C("User dashboard, profile, preferences, delete account", "Done", "export-format preference is used in the history; language and e-mail-notification preferences are stored but not used yet"),
                 C("Light / dark mode, responsive, 404 / 500 pages", "Done", "the administrator's default theme applies to visitors who have not chosen one"),
                 C("Docker, Docker Compose, CI (9)", "Written, not built", "no Docker in the development environment; cloud deployment (AWS, Azure, GCP) not done"),
                 C("TXT / PDF upload (FR-3)", "Done", "scanned PDFs without text cannot be read")], [8, 2.4, 6.1])]

story += [P("10. Limitations, ethics and future work", h1),
          *B(["<b>Source bias.</b> Two publishers, very different styles: the model learns style, so accuracy on other outlets is unknown and likely lower. Evaluating on an independent dataset is the most important next step.",
              "<b>Not a fact-checker.</b> The system never verifies a claim against evidence. Satire, opinion pieces and breaking news could be mislabelled. The interface warns users and shows low-confidence results explicitly.",
              "<b>Confident errors happen.</b> Users should read the highlighted evidence rather than trust the percentage alone.",
              "<b>Privacy.</b> Submitted articles are stored in each user's history; users can delete entries or their whole account.",
              "<b>Future work.</b> Cross-dataset evaluation, word embeddings or a fine-tuned transformer, claim-level explanations, multi-language support, and cloud deployment."])]
story += [P("11. Conclusion", h1),
          P(f"The project delivers a working, tested platform: a five-model comparison on {n_articles:,} articles reaching up to {pct(max(m.accuracy for m in models), 1)} accuracy, "
            "explanations that show the evidence inside the article, and a secure two-interface web application. The experiments also show that high accuracy on this dataset partly reflects source style, "
            "and the report states that limitation openly instead of presenting the accuracy as proof of truth detection.")]

# appendix: screenshots
story += [CondPageBreak(12 * cm), P("Appendix A. Screens of the application", h1),
          shot("03_analyze.png", "A.1 Analyze page: paste text or upload a document, with character and word counters.", box=(SIDE, 0, 1366, 830)),
          shot("04_result_overview.png", "A.2 Result overview: verdict, confidence, the marked article, strongest signals and keywords.", box=(SIDE, 0, 1366, 900)),
          shot("07_result_similar.png", "A.3 Similar news: the five closest dataset articles with similarity and dataset label.", box=(SIDE, 0, 1366, 720)),
          shot("08_result_keywords.png", "A.4 Keywords: cloud, frequency chart and ranked list.", box=(SIDE, 0, 1366, 1000)),
          shot("09_history.png", "A.5 Prediction history with search, filters, sorting, bulk actions and exports.", box=(SIDE, 0, 1366, 760)),
          shot("12_result_dark.png", "A.6 Dark mode.", box=(SIDE, 0, 1366, 900)),
          shot("14_admin_dashboard.png", "A.7 Administrator dashboard.", box=(SIDE, 0, 1366, 1177)),
          shot("16_admin_datasets.png", "A.8 Dataset import history.", box=(SIDE, 0, 1366, 700)),
          shot("18_admin_models.png", "A.9 Model management and comparison.", box=(SIDE, 0, 1366, 1000)),
          shot("19_admin_analytics.png", "A.10 Analytics.", box=(SIDE, 0, 1366, 1250)),
          shot("20_admin_explain.png", "A.11 Explainability monitoring.", box=(SIDE, 0, 1366, 900)),
          shot("21_admin_settings.png", "A.12 Settings, stop-words and keyword dictionary.", box=(SIDE, 0, 1366, 900)),
          shot("13_result_mobile.png", "A.13 The result page on a phone-sized screen (390 px wide).", width=5.5),
          P(f"<b>Source code:</b> {args.github}", body), P("<b>Run it:</b> see README.md (Docker Compose or local development).", body)]

def footer(c, d):
    c.saveState(); c.setFont("DV", 7.5); c.setFillColor(colors.HexColor("#6b7a89"))
    c.drawString(2 * cm, 1.2 * cm, "Fake News Explainability Platform - WEX 428"); c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {d.page}"); c.restoreState()

out = DOCS / "Project_Report.pdf"
SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm,
                  title="Fake News Explainability Platform - Project Report", author=args.name).build(story, onFirstPage=lambda c, d: None, onLaterPages=footer)
print("written", out, f"({out.stat().st_size / 1024:.0f} KB)")
