"""Report Generation Service (FR-11 / 8.12): PDF and CSV exports."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import PredictionHistory

styles = getSampleStyleSheet()
_RED, _GREEN = colors.HexColor("#c0392b"), colors.HexColor("#1e8449")


def _table(data, widths=None, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(st))
    return t


def _p(text, style="BodyText"):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])


def prediction_pdf(p: PredictionHistory) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Prediction report #{p.prediction_id}")
    colour = _RED if p.prediction_result == "Fake" else _GREEN
    s = [_p("Fake News Explainability Platform - Analysis Report", "Title"),
         _p(f"Report for prediction #{p.prediction_id}", "Heading3"), Spacer(1, 6)]
    s.append(_table([["Prediction", p.prediction_result.upper() + " NEWS"],
                     ["Confidence", f"{p.confidence_score * 100:.2f}%"],
                     ["P(Fake) / P(Real)", f"{p.prob_fake * 100:.2f}% / {p.prob_real * 100:.2f}%"],
                     ["Date and time of analysis", p.prediction_date.strftime("%Y-%m-%d %H:%M:%S UTC")],
                     ["Processing time", f"{p.processing_time:.3f} s"],
                     ["Model", f"{p.model.model_name} ({p.model.algorithm})" if p.model else "(model deleted)"]],
                    [5 * cm, 11 * cm], header=False))
    s += [Spacer(1, 8), _p("Decision-support notice: this result is a statistical estimate, not a verdict of truth. "
                           "Always verify important claims against trusted sources.", "Italic"), Spacer(1, 8)]
    s += [_p("Submitted article", "Heading2")]
    if p.submitted_title:
        s.append(_p(p.submitted_title, "Heading4"))
    s.append(_p(p.submitted_content[:20000] + (" ..." if len(p.submitted_content) > 20000 else "")))
    s += [Spacer(1, 8), _p("Explainability analysis", "Heading2")]
    for method in sorted({e.method for e in p.explanations}):
        rows = sorted([e for e in p.explanations if e.method == method], key=lambda e: -abs(e.contribution_value))[:20]
        s.append(_p(f"Method: {method.upper()} (positive = pushes towards '{p.prediction_result}', negative = against)", "Heading4"))
        s.append(_table([["Word", "Contribution", "Type"]] + [[e.word, f"{e.contribution_value:+.4f}", e.contribution_type] for e in rows],
                        [7 * cm, 4 * cm, 4 * cm]))
        s.append(Spacer(1, 6))
    s.append(_p("Keywords", "Heading2"))
    s.append(_table([["Keyword", "Importance", "Frequency"]] + [[k.keyword, f"{k.importance_score:.3f}", k.frequency or ""]
                                                               for k in sorted(p.keywords, key=lambda k: -k.importance_score)],
                    [7 * cm, 4 * cm, 4 * cm]))
    s.append(_p("Similar articles", "Heading2"))
    s.append(_table([["#", "Title", "Subject", "Label", "Similarity"]] +
                    [[x.rank, (x.news.title[:70] if x.news else "(deleted)"), x.news.subject if x.news else "", x.news.label if x.news else "",
                      f"{x.similarity_score * 100:.1f}%"] for x in sorted(p.similar, key=lambda x: x.rank)],
                    [1 * cm, 8 * cm, 3 * cm, 2 * cm, 2.5 * cm]))
    doc.build(s)
    return buf.getvalue()


def _csv(rows: list[list]) -> bytes:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return ("\ufeff" + out.getvalue()).encode("utf-8")          # BOM so Excel opens UTF-8 correctly


def predictions_csv(preds: list[PredictionHistory]) -> bytes:
    rows = [["prediction_id", "date", "title", "result", "confidence", "prob_fake", "prob_real", "processing_time_s",
             "model", "top_explanation_words", "keywords", "similar_articles", "article"]]
    for p in preds:
        top = ", ".join(f"{e.word}({e.contribution_value:+.3f})" for e in
                        sorted(p.explanations, key=lambda e: -abs(e.contribution_value))[:10])
        rows.append([p.prediction_id, p.prediction_date.isoformat(), p.submitted_title or "", p.prediction_result,
                     f"{p.confidence_score:.4f}", f"{p.prob_fake:.4f}", f"{p.prob_real:.4f}", f"{p.processing_time:.4f}",
                     p.model.model_name if p.model else "", top, ", ".join(k.keyword for k in p.keywords),
                     " | ".join(f"{x.news.title[:60]} ({x.similarity_score:.2f})" for x in p.similar if x.news),
                     p.submitted_content])
    return _csv(rows)


def analytics_pdf(dash: dict, content: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title="System analytics report")
    s = [_p("System-wide Analytics Report", "Title"), _p(f"Generated {datetime.utcnow():%Y-%m-%d %H:%M UTC}", "Italic"), Spacer(1, 8)]
    am = dash["active_model"]
    s.append(_table([["Metric", "Value"], ["Total users", dash["total_users"]],
                     [f"Active users (last {dash['active_users_window_days']} days)", dash["active_users"]],
                     ["Total predictions", dash["total_predictions"]], ["Fake predictions", dash["fake_predictions"]],
                     ["Real predictions", dash["real_predictions"]], ["Articles in dataset", dash["dataset_size"]["total"]],
                     ["Average confidence", f"{dash['average_confidence']:.3f}" if dash["average_confidence"] is not None else "-"],
                     ["Average processing time (s)", f"{dash['average_processing_time']:.3f}" if dash["average_processing_time"] is not None else "-"],
                     ["Active model", am["name"] if am else "none"]], [9 * cm, 7 * cm]))
    s += [Spacer(1, 10), _p("Model performance (held-out test set)", "Heading2")]
    s.append(_table([["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "Train (s)"]] +
                    [[m["name"][:34], *(f"{m[k]:.4f}" if m[k] is not None else "-" for k in ("accuracy", "precision", "recall", "f1", "roc_auc")),
                      m["training_seconds"] or "-"] for m in dash["model_comparison"]],
                    [6 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.6 * cm]))
    s += [Spacer(1, 10), _p("Most frequent keywords", "Heading2"),
          _table([["Keyword", "Count"]] + [[k["keyword"], k["count"]] for k in content["frequent_keywords"]], [9 * cm, 4 * cm])]
    s += [Spacer(1, 10), _p("Daily predictions (last 30 days)", "Heading2"),
          _table([["Date", "Fake", "Real"]] + [[d["date"], d["Fake"], d["Real"]] for d in dash["daily_predictions"]], [6 * cm, 3 * cm, 3 * cm])]
    doc.build(s)
    return buf.getvalue()


def analytics_csv(dash: dict, content: dict) -> bytes:
    rows = [["section", "key", "value", "extra"]]
    for k in ("total_users", "active_users", "total_predictions", "fake_predictions", "real_predictions",
              "total_news_articles", "average_confidence", "average_processing_time"):
        rows.append(["summary", k, dash[k], ""])
    for d in dash["daily_predictions"]:
        rows.append(["daily", d["date"], d["Fake"], d["Real"]])
    for d in dash["monthly_predictions"]:
        rows.append(["monthly", d["month"], d["Fake"], d["Real"]])
    for m in dash["model_comparison"]:
        rows.append(["model", m["name"], m["accuracy"], f"p={m['precision']} r={m['recall']} f1={m['f1']}"])
    for k in content["frequent_keywords"]:
        rows.append(["keyword", k["keyword"], k["count"], k["avg_importance"]])
    for s_ in content["news_subjects"]:
        rows.append(["subject", s_["subject"], s_["count"], ""])
    return _csv(rows)
