"""End-to-end API tests, executed in file order (later tests build on earlier state)."""
import io

import pytest

# ------------------------------------------------------------------ auth / RBAC
def test_register_validation(client):
    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": "not-an-email", "password": "Passw0rdOK"})
    assert r.status_code == 422 and "email" in r.json()["detail"].lower()
    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": "x@example.com", "password": "short1"})
    assert r.status_code == 422 and "too short" in r.json()["detail"].lower()
    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": "x@example.com", "password": "onlyletters"})
    assert r.status_code == 422


def test_register_duplicate_and_login(client, user_h):
    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": "ADA@example.com", "password": "Passw0rdOK"})
    assert r.status_code == 409 and "already exists" in r.json()["detail"]
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrongpass1"}).status_code == 401
    assert client.get("/api/auth/me", headers=user_h).json()["email"] == "ada@example.com"


def test_password_is_hashed(client, user_h):
    from app.database import SessionLocal
    from app.models import User
    db = SessionLocal(); u = db.query(User).filter_by(email="ada@example.com").one(); db.close()
    assert u.password.startswith("$2") and "Passw0rdOK" not in u.password


def test_unauthenticated_and_rbac(client, user_h):
    assert client.get("/api/predictions/history").status_code == 401
    assert client.get("/api/admin/models").status_code == 401
    assert client.get("/api/admin/models", headers=user_h).status_code == 403
    assert client.get("/api/admin/logs", headers=user_h).status_code == 403


def test_logout_revokes_token(client):
    r = client.post("/api/auth/register", json={"first_name": "T", "last_name": "T", "email": "t@example.com", "password": "Passw0rdOK"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_forgot_and_reset_password(client):
    client.post("/api/auth/register", json={"first_name": "F", "last_name": "P", "email": "fp@example.com", "password": "Passw0rdOK"})
    r = client.post("/api/auth/forgot-password", json={"email": "fp@example.com"})
    token = r.json()["dev_reset_token"]
    assert "dev_reset_token" not in client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).json()
    assert client.post("/api/auth/reset-password", json={"token": "bad", "new_password": "NewPassw0rd"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "NewPassw0rd"}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "Another1234"}).status_code == 400   # single use
    assert client.post("/api/auth/login", json={"email": "fp@example.com", "password": "NewPassw0rd"}).status_code == 200


# ------------------------------------------------------------------ before any model exists
def test_analyze_without_model_is_clear_error(client, user_h):
    r = client.post("/api/news/analyze", headers=user_h, json={"text": "word " * 60})
    assert r.status_code == 503 and "model" in r.json()["detail"].lower()


# ------------------------------------------------------------------ datasets
def test_dataset_missing_columns_rejected(client, admin_h):
    bad = b"title,text\nHello,World text here\n"
    r = client.post("/api/admin/datasets/upload", headers=admin_h, files={"file": ("bad.csv", bad, "text/csv")})
    assert r.status_code == 422 and "missing required column" in r.json()["detail"] and "subject" in r.json()["detail"]
    r = client.post("/api/admin/datasets/upload", headers=admin_h, files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 415


def test_dataset_import_validation_and_duplicates(client, admin_h, sample_df, sample_csv):
    import pandas as pd
    df = sample_df.copy()
    extra = pd.DataFrame([{"title": "t", "text": "short", "subject": "s", "date": "d", "label": "Fake"},          # too short
                          {"title": "t2", "text": "word " * 30, "subject": "s", "date": "d", "label": "maybe"}])   # bad label
    df = pd.concat([df, extra, df.iloc[:5]], ignore_index=True)                                                    # + 5 duplicates
    buf = io.BytesIO(); df.to_csv(buf, index=False)
    r = client.post("/api/admin/datasets/preview", headers=admin_h, files={"file": ("s.csv", buf.getvalue(), "text/csv")})
    assert r.status_code == 200 and r.json()["rejected"] == 2 and r.json()["duplicates"] == 5
    r = client.post("/api/admin/datasets/upload?wait=true", headers=admin_h, files={"file": ("s.csv", buf.getvalue(), "text/csv")})
    d = r.json()
    assert d["status"] == "Success", d
    assert d["imported_records"] == len(sample_df) and d["rejected_records"] == 2 and d["duplicate_records"] == 5
    # importing the same data again: everything is a duplicate, nothing new is stored
    r = client.post("/api/admin/datasets/upload?wait=true", headers=admin_h, files={"file": ("again.csv", buf.getvalue(), "text/csv")})
    assert r.json()["imported_records"] == 0 and r.json()["duplicate_records"] >= len(sample_df)
    assert client.get("/api/admin/datasets", headers=admin_h).json()["total_articles"] == len(sample_df)


# ------------------------------------------------------------------ models
def test_train_compare_activate_single_active(client, admin_h):
    ids = {}
    for algo in ("logistic_regression", "naive_bayes"):
        r = client.post("/api/admin/models/train", headers=admin_h, json={"algorithm": algo, "vectorizer": "tfidf", "wait": True})
        assert r.status_code == 202, r.text
        m = r.json(); ids[algo] = m["id"]
        assert m["status"] == "Ready" and m["accuracy"] > 0.8 and len(m["confusion_matrix"]) == 2
    assert client.post("/api/admin/models/train", headers=admin_h, json={"algorithm": "nope"}).status_code == 422
    assert client.put(f"/api/admin/models/{ids['naive_bayes']}/activate", headers=admin_h).status_code == 200
    assert client.put(f"/api/admin/models/{ids['logistic_regression']}/activate", headers=admin_h).status_code == 200
    items = client.get("/api/admin/models", headers=admin_h).json()["items"]
    assert [m["is_active"] for m in items].count(True) == 1 and next(m for m in items if m["is_active"])["id"] == ids["logistic_regression"]
    assert client.delete(f"/api/admin/models/{ids['logistic_regression']}", headers=admin_h).status_code == 409   # active
    assert client.delete(f"/api/admin/models/{ids['naive_bayes']}", headers=admin_h).status_code == 200


# ------------------------------------------------------------------ analysis workflow
@pytest.fixture(scope="module")
def sample_text(sample_df):
    row = sample_df[sample_df.label == "Real"].iloc[3]
    return row.title, row.text


def test_analyze_full_pipeline(client, user_h, sample_text):
    title, text = sample_text
    r = client.post("/api/news/analyze", headers=user_h, json={"title": title, "text": text})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["result"] in ("Fake", "Real") and 0.5 <= d["confidence"] <= 1 and abs(sum(d["probabilities"].values()) - 1) < 1e-6
    assert d["processing_time"] > 0 and d["date"] and d["model_info"]["algorithm"] == "logistic_regression"
    lime = d["explanation"]["lime"]
    assert lime["positive_words"] and lime["feature_importance"] and lime["highlight"]
    assert d["explanation"]["shap"] and d["explanation"]["shap"]["positive_words"]      # LR supports SHAP
    assert len(d["keywords"]) >= 3 and all("importance" in k for k in d["keywords"])
    assert 1 <= len(d["similar"]) <= 5 and {"title", "subject", "similarity", "label", "rank"} <= set(d["similar"][0])
    assert any(seg["weight"] is not None for seg in lime["highlight"])                  # words highlighted inside the article
    assert "".join(s["text"] for s in lime["highlight"]) == text.strip()                # highlight keeps the original text intact
    pytest.pred_id = d["prediction_id"]


def test_prediction_uses_title_like_training(client, user_h, sample_text):
    """Regression: models are trained on 'title. text', so inference must use the same document."""
    from app.database import SessionLocal
    from app.services.prediction import get_active_model, registry
    title, text = sample_text
    r = client.post("/api/news/analyze", headers=user_h, json={"title": title, "text": text}).json()
    db = SessionLocal(); pipe = registry.get_pipeline(get_active_model(db)); db.close()
    expected = pipe.predict_proba([f"{title}. {text.strip()}"])[0][1]
    assert abs(r["probabilities"]["Real"] - expected) < 1e-9
    client.delete(f"/api/predictions/{r['prediction_id']}", headers=user_h)      # leave history as other tests expect


def test_short_text_rejected(client, user_h):
    r = client.post("/api/news/analyze", headers=user_h, json={"text": "too short"})
    assert r.status_code == 422 and "too short" in r.json()["detail"].lower()


def test_history_search_detail_isolation(client, user_h, user2_h):
    pid = pytest.pred_id
    h = client.get("/api/predictions/history", headers=user_h).json()
    assert h["total"] >= 1 and h["items"][0]["prediction_id"] == pid
    assert client.get("/api/predictions/history?search=zzzzqqqq", headers=user_h).json()["total"] == 0
    assert client.get(f"/api/predictions/{pid}", headers=user_h).status_code == 200
    assert client.get(f"/api/explanations/{pid}", headers=user_h).json()["lime"]
    assert client.get(f"/api/news/similar/{pid}", headers=user_h).json()["similar"]
    # another user must not see it
    assert client.get(f"/api/predictions/{pid}", headers=user2_h).status_code == 404
    assert client.get(f"/api/explanations/{pid}", headers=user2_h).status_code == 404
    assert client.delete(f"/api/predictions/{pid}", headers=user2_h).status_code == 404
    assert client.get("/api/predictions/history", headers=user2_h).json()["total"] == 0


def test_exports(client, user_h):
    pid = pytest.pred_id
    r = client.get(f"/api/predictions/{pid}/export?format=pdf", headers=user_h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and len(r.content) > 2000
    r = client.get(f"/api/predictions/{pid}/export?format=csv", headers=user_h)
    assert r.status_code == 200 and b"prediction_id" in r.content and b"Real" in r.content or b"Fake" in r.content
    assert client.get("/api/predictions/export", headers=user_h).status_code == 200


def test_file_uploads(client, user_h, sample_text):
    _, text = sample_text
    r = client.post("/api/news/upload", headers=user_h, files={"file": ("story.txt", text.encode(), "text/plain")})
    assert r.status_code == 200 and r.json()["title"] == "story"
    assert client.post("/api/news/upload", headers=user_h, files={"file": ("virus.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert client.post("/api/news/upload", headers=user_h, files={"file": ("e.txt", b"", "text/plain")}).status_code == 422
    assert client.post("/api/news/upload", headers=user_h, files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}).status_code == 422
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); y = 800
    for line in [" ".join(text.split()[i:i + 12]) for i in range(0, 120, 12)]:
        c.drawString(40, y, line); y -= 16
    c.save()
    r = client.post("/api/news/upload", headers=user_h, files={"file": ("doc.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200, r.text


def test_delete_prediction(client, user_h):
    pid = pytest.pred_id
    assert client.delete(f"/api/predictions/{pid}", headers=user_h).status_code == 200
    assert client.get(f"/api/predictions/{pid}", headers=user_h).status_code == 404


# ------------------------------------------------------------------ admin
def test_admin_user_management(client, admin_h, user_h):
    users = client.get("/api/admin/users?search=ada", headers=admin_h).json()
    uid = users["items"][0]["id"]
    admin_id = client.get("/api/admin/users?search=admin@", headers=admin_h).json()["items"][0]["id"]
    assert client.post(f"/api/admin/users/{admin_id}/deactivate", headers=admin_h).status_code == 400     # self
    assert client.put(f"/api/admin/users/{admin_id}", headers=admin_h, json={"role": "User"}).status_code == 400
    assert client.post(f"/api/admin/users/{uid}/deactivate", headers=admin_h).status_code == 200
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "Passw0rdOK"}).status_code == 403
    assert client.get("/api/auth/me", headers=user_h).status_code == 403                                  # existing token stops working
    assert client.post(f"/api/admin/users/{uid}/activate", headers=admin_h).status_code == 200
    assert client.post(f"/api/admin/users/{uid}/reset-password", headers=admin_h, json={"new_password": "ResetPass99"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "ResetPass99"}).status_code == 200


def test_admin_dashboard_analytics_logs(client, admin_h):
    a = client.get("/api/admin/analytics", headers=admin_h).json()
    assert a["total_users"] >= 3 and a["total_predictions"] >= 1 and a["real_predictions"] + a["fake_predictions"] == a["total_predictions"]
    assert a["active_model"]["algorithm"] == "logistic_regression" and a["dataset_size"]["total"] > 0
    assert a["daily_predictions"] and a["model_comparison"] and a["content"]["frequent_keywords"]
    ex = client.get("/api/admin/explainability", headers=admin_h).json()
    assert ex["most_influential_words"]
    types = client.get("/api/admin/logs", headers=admin_h).json()["event_types"]
    assert {"Login", "Prediction", "Training", "Import", "Unauthorized"} <= set(types)
    assert client.get("/api/admin/reports/analytics?format=pdf", headers=admin_h).content.startswith(b"%PDF")
    assert b"summary" in client.get("/api/admin/reports/analytics?format=csv", headers=admin_h).content


def test_admin_news_stopwords_settings(client, admin_h):
    items = client.get("/api/admin/news?label=Fake&page_size=5", headers=admin_h).json()["items"]
    assert items and all(i["label"] == "Fake" for i in items)
    nid = items[0]["news_id"]
    assert client.put(f"/api/admin/news/{nid}", headers=admin_h, json={"subject": "edited-subject"}).json()["subject"] == "edited-subject"
    assert any(s["subject"] == "edited-subject" for s in client.get("/api/admin/subjects", headers=admin_h).json()["items"])
    assert client.delete(f"/api/admin/news/{nid}", headers=admin_h).status_code == 200
    sw = client.get("/api/admin/stopwords", headers=admin_h).json()
    assert client.put("/api/admin/stopwords", headers=admin_h, json={"words": sw["words"]}).status_code == 200   # unchanged list
    assert client.put("/api/admin/settings", headers=admin_h, json={"values": {"keyword_method": "rake"}}).status_code == 200
    assert client.put("/api/admin/settings", headers=admin_h, json={"values": {"keyword_method": "bogus"}}).status_code == 422
    assert client.post("/api/admin/keyword-dictionary", headers=admin_h, json={"term": "senate", "list_type": "include"}).status_code == 201


# ------------------------------------------------------------------ ROC, dataset-scoped training, default theme
def test_roc_curve_and_dataset_scoped_training(client, admin_h):
    train = lambda: client.post("/api/admin/models/train", headers=admin_h,
                                json={"algorithm": "naive_bayes", "vectorizer": "tfidf", "wait": True}).json()
    m = train()
    roc = client.get(f"/api/admin/models/{m['id']}", headers=admin_h).json()["roc_curve"]
    assert roc["fpr"][0] == 0 and roc["tpr"][-1] == 1 and len(roc["fpr"]) == len(roc["tpr"]) > 5

    put = lambda v: client.put("/api/admin/settings", headers=admin_h, json={"values": {"active_dataset": str(v)}})
    assert put(999).status_code == 422                                        # unknown dataset is rejected
    items = client.get("/api/admin/datasets", headers=admin_h).json()["items"]
    empty = next(d for d in items if d["imported_records"] == 0 and d["status"] == "Success")
    full = next(d for d in items if d["imported_records"] > 0)
    assert put(empty["dataset_id"]).status_code == 200
    bad = train()                                                             # that dataset has no articles -> clear failure
    assert bad["status"] == "Failed"
    log = client.get(f"/api/admin/models/{bad['id']}", headers=admin_h).json()["runs"][0]["log"]
    assert "Not enough data" in log and "restricted to dataset" in log
    assert put(full["dataset_id"]).status_code == 200
    good = train()
    assert good["status"] == "Ready" and f"dataset {full['dataset_id']}" in good["dataset_version"]
    assert put("all").status_code == 200


def test_public_default_theme(client, admin_h):
    assert client.get("/api/settings/public").json()["default_theme"] == "light"           # no login needed
    client.put("/api/admin/settings", headers=admin_h, json={"values": {"theme": "dark"}})
    assert client.get("/api/settings/public").json()["default_theme"] == "dark"
    client.put("/api/admin/settings", headers=admin_h, json={"values": {"theme": "light"}})
