"""Test fixtures. Uses an isolated temp database/storage and a small SAMPLE of the real dataset
(set FN_DATA_DIR to the folder containing Fake.csv and True.csv)."""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

TMP = tempfile.mkdtemp(prefix="fn_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TMP}/test.db")   # override to run the suite on PostgreSQL
os.environ.update({
    "STORAGE_DIR": TMP, "JWT_SECRET": "test-secret-not-for-production",
    "ADMIN_EMAIL": "admin@example.com", "ADMIN_PASSWORD": "AdminPass123", "EXPOSE_RESET_TOKEN": "true",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
Path(TMP, "models").mkdir(exist_ok=True); Path(TMP, "avatars").mkdir(exist_ok=True)

DATA_DIR = Path(os.environ.get("FN_DATA_DIR", "/mnt/user-data/uploads"))
N_PER_CLASS = int(os.environ.get("FN_TEST_SAMPLE", "700"))


@pytest.fixture(scope="session")
def sample_df():
    if not (DATA_DIR / "Fake.csv").exists():
        pytest.skip("Fake.csv / True.csv not found - set FN_DATA_DIR")
    f = pd.read_csv(DATA_DIR / "Fake.csv"); f["label"] = "Fake"
    t = pd.read_csv(DATA_DIR / "True.csv"); t["label"] = "Real"
    f = f[f.text.str.split().str.len() > 30].sample(N_PER_CLASS, random_state=0)
    t = t[t.text.str.split().str.len() > 30].sample(N_PER_CLASS, random_state=0)
    df = pd.concat([f, t], ignore_index=True).sample(frac=1, random_state=1)
    from app.services.dataset import content_hash          # the real data contains duplicates: drop them like the importer does
    h = [content_hash(a, b) for a, b in zip(df.title, df.text)]
    df = df.assign(_h=h)
    df = df[~df._h.duplicated(keep=False)].drop(columns="_h")   # also drops contradictory (same text, both labels) copies
    return df.reset_index(drop=True)


@pytest.fixture(scope="session")
def sample_csv(sample_df):
    p = Path(TMP) / "sample.csv"; sample_df.to_csv(p, index=False); return p


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _auth(token): return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_h(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "AdminPass123"})
    assert r.status_code == 200, r.text
    return _auth(r.json()["access_token"])


@pytest.fixture(scope="session")
def user_h(client):
    r = client.post("/api/auth/register", json={"first_name": "Ada", "last_name": "Lovelace",
                                                "email": "ada@example.com", "password": "Passw0rdOK"})
    assert r.status_code == 201, r.text
    return _auth(r.json()["access_token"])


@pytest.fixture(scope="session")
def user2_h(client):
    r = client.post("/api/auth/register", json={"first_name": "Bob", "last_name": "Other",
                                                "email": "bob@example.com", "password": "Passw0rdOK"})
    return _auth(r.json()["access_token"])


# Tests that need the real dataset are skipped when it is not available (e.g. on GitHub Actions),
# so CI stays green without the data files. Everything not in this list needs the dataset.
NO_DATA_NEEDED = {
    "test_register_validation", "test_register_duplicate_and_login", "test_password_is_hashed",
    "test_unauthenticated_and_rbac", "test_logout_revokes_token", "test_forgot_and_reset_password",
    "test_analyze_without_model_is_clear_error", "test_dataset_missing_columns_rejected", "test_public_default_theme",
}


def pytest_collection_modifyitems(config, items):
    if (DATA_DIR / "Fake.csv").exists():
        return
    skip = pytest.mark.skip(reason="dataset not found - set FN_DATA_DIR to run the data-dependent tests")
    for item in items:
        if item.name not in NO_DATA_NEEDED:
            item.add_marker(skip)
