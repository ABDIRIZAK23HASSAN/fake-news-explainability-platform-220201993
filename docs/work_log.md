# Work log

**Read this first.** The course asks for a log covering the 70 working days. This file records only what was
actually done in the working session(s) that produced this code, so it is short. Do not pad it. Add your own real
entries for the days you actually worked (reading the assignment, studying the dataset, testing, rehearsing)
using the template at the bottom, with your own dates. If the log must cover 70 days, ask your instructor whether
a shorter log is acceptable, and state the real working period at the top.

## Session 1 - building the platform (October 2026)

### Data understanding
- Read the assignment (platform, 12 functional requirements, 10 database tables, NLP requirements, 15 REST endpoints).
- Inspected the provided files: raw `Fake.csv` (23,481 rows) and `True.csv` (21,417 rows) have no label column;
  `merged_data.csv`, `cleaned_data.csv`, `train.csv`, `test.csv` are the processed versions (label 1 = Real, 0 = Fake).
- **Finding:** `reuter` appears in 99.8% of Real and 1.2% of Fake articles; `subject` separates the classes perfectly;
  6,026 duplicated texts and 630 empty texts in Fake.csv; 82 articles shared by `train.csv` and `test.csv`.
- **Decision:** never use `subject`; remove duplicates; add a source-artifact removal step; own stratified 80/20 split.

### NLP and experiments
- Wrote the preprocessing service (one code path for training and prediction) and the training/evaluation service.
- Ran experiments A (preprocessing / leakage), B (feature extraction) and C (five models); results in
  `docs/experiments/results.json`. Reuters removal lowers accuracy from 99.38% to 98.65%.
- **Problem:** the machine had 1 CPU core and 3 GB RAM; XGBoost and Random Forest were too slow/heavy at first.
  **Decision:** 10,000 features and fewer trees for tree models; run long jobs detached and save results step by step.
- Imported the full dataset through the platform (38,559 articles) and trained the five models through the admin pipeline.

### Backend
- Built FastAPI app: authentication (JWT, bcrypt, logout revocation, password reset), user and admin endpoints,
  dataset import with validation and progress, model management (single active model enforced by a DB index),
  LIME / SHAP explanations, TF-IDF similarity and keyword extraction, PDF / CSV reports, analytics, logs.
- Wrote 20 API tests. **Defects found and fixed:** stale model status after training; route
  `/users/{id}/{action}` shadowing `/reset-password`; PostgreSQL rejecting numpy numbers (found only after
  installing PostgreSQL and running the suite on it); non-deterministic training order; inference ignoring the
  headline although models are trained on "title. text".

### Frontend
- Built the React interface (user and admin), then tested it in headless Chromium.
- **Defects found and fixed:** Chart.js controllers not registered (charts crashed the page); error page used a router
  link outside the router; keyword cloud could not wrap; top bar overflowed on phones; LIME gave noise weights to
  stop-words that preprocessing removes.

### Deliverables
- Docker Compose / Dockerfiles / nginx / CI written (**Docker images were not built in the development environment**).
- Bootstrap script, demo-article generator (held-out test articles, including one confident model mistake),
  browser end-to-end test, project report (PDF) and defense slides (7 slides).

### Completing the gaps listed in the report (same period)
- Training now really honours Settings > "Dataset used for training"; the setting is validated and reset if that dataset is deleted.
- ROC curves are computed for every model, stored with the training run and drawn in the model-details dialog;
  all five models were retrained in place and reproduced their earlier accuracy exactly (98.76 / 98.95 / 95.44 / 97.63 / 98.70).
- The administrator's default theme now applies to visitors without a saved choice; the default export format is used in the history page.
- Added 2 API tests (22 in total, passing on SQLite and PostgreSQL) and a browser check for the ROC chart.
- Deliberately NOT done: refresh tokens (optional), Word2Vec / FastText / BM25, a translated interface, e-mail notifications, cloud deployment.

### Still to do by the student
- Put your name, ID and the GitHub link in the report (`python scripts/build_report.py --name ... --student-id ... --github ...`)
  and in the slides; create the GitHub repository and push.
- Build and run `docker compose up` on your machine and fix anything that fails; rerun the tests there.
- Read the code and the report until you can explain every part; rehearse the 15-minute defense with the live demo.
- Add your own real log entries below.

## Template for your own entries

| Date | What I did | Problems / decisions |
|---|---|---|
| | | |
