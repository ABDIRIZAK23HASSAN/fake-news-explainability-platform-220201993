"""Browser end-to-end check (Playwright/Chromium). Needs the backend on :8000 and the frontend on :5173."""
import sys, json, re, pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5173"
SHOTS = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
DATA = Path(sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads")

DEMO = Path(__file__).resolve().parents[1] / "docs" / "demo_articles"
def pick(name, n_words=(180, 420)):
    demo = DEMO / ("fake_2.txt" if name == "Fake.csv" else "real_1.txt")     # held-out articles (never trained on)
    if demo.exists():
        t, _, body = demo.read_text(encoding="utf-8").partition("\n\n"); return t, body.strip()
    df = pd.read_csv(DATA / name)
    df = df[df.text.str.split().str.len().between(*n_words)]
    r = df.sample(1, random_state=7).iloc[0]
    return r.title, r.text

problems, console_errors = [], []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: problems.append(msg)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
    page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
    bad_responses = []
    page.on("response", lambda r: r.status >= 500 and bad_responses.append(f"{r.status} {r.url}"))

    # ---- login page + client-side validation
    page.goto(BASE + "/login"); page.wait_for_selector("text=Log in")
    page.click("button:has-text('Log in')")
    check(page.locator("text=Invalid email format").count() == 1, "login: client-side email validation message")
    page.screenshot(path=SHOTS / "01_login.png")
    page.fill("#f-email", "demo@example.com"); page.fill("#f-password", "wrong-password1")
    page.click("button:has-text('Log in')"); page.wait_for_selector("text=Incorrect email or password")
    check(True, "login: wrong password shows server error")
    page.fill("#f-password", "Demo12345"); page.click("button:has-text('Log in')")
    page.wait_for_url("**/dashboard"); page.wait_for_selector("text=Welcome back, Demo")
    check(True, "login: demo user reaches the dashboard")
    page.screenshot(path=SHOTS / "02_user_dashboard_empty.png")

    # ---- role separation
    page.goto(BASE + "/admin"); page.wait_for_selector("text=Administrators only")
    check(page.locator("text=Welcome back").count() == 0 and page.locator("text=Administrator dashboard").count() == 0, "RBAC: a normal user sees the 403 page on /admin")

    # ---- analyze a FAKE article by pasting
    title, text = pick("Fake.csv")
    page.goto(BASE + "/analyze")
    page.fill("input >> nth=0", title); page.fill("#article-text", text)
    check(page.locator("text=/\\d+ words/").count() >= 1, "analyze: word/character counter visible")
    page.screenshot(path=SHOTS / "03_analyze.png")
    page.click("button:has-text('Analyze')")
    page.wait_for_url(re.compile(r".*/results/\d+$"), timeout=90000)
    page.wait_for_selector(".verdict"); rid = page.url.rsplit("/", 1)[1]
    verdict = page.locator(".verdict .label").first.inner_text()
    print("   verdict:", verdict, "| confidence:", page.locator(".verdict .label").nth(1).inner_text())
    check(verdict in ("Fake news", "Real news"), "result: verdict shown")
    n_marks = page.locator("mark.ev").count()
    check(n_marks >= 5, f"result: influential words highlighted inside the article ({n_marks} marks)")
    page.screenshot(path=SHOTS / "04_result_overview.png", full_page=True)

    page.click("a:has-text('Explanation')"); page.wait_for_selector("text=Feature importance ranking")
    check(page.locator("button:has-text('SHAP')").count() == 1, "explain: SHAP and LIME both available for Logistic Regression")
    page.screenshot(path=SHOTS / "05_result_explanation_lime.png", full_page=True)
    page.click("button:has-text('SHAP')"); page.wait_for_timeout(300)
    page.screenshot(path=SHOTS / "06_result_explanation_shap.png", full_page=True)
    page.click("a:has-text('Similar news')"); page.wait_for_selector("th:has-text('Similarity')")
    check(page.locator("tbody tr").count() == 5, "similar: exactly 5 articles listed")
    page.screenshot(path=SHOTS / "07_result_similar.png")
    page.click("tbody tr a >> nth=0"); page.wait_for_selector("text=reference dataset"); page.go_back()
    page.click("a:has-text('Keywords')"); page.wait_for_selector("text=Top keywords")
    page.screenshot(path=SHOTS / "08_result_keywords.png", full_page=True)

    # ---- exports (PDF / CSV downloads through the authenticated API)
    page.click("a:has-text('Overview')")
    with page.expect_download() as d: page.click("button:has-text('Export PDF')")
    pdf = Path("/tmp/ui_report.pdf"); d.value.save_as(pdf)
    check(pdf.read_bytes()[:4] == b"%PDF", "export: PDF downloaded and valid")

    # ---- analyze a REAL article via file upload (.txt)
    t2, x2 = pick("True.csv"); Path("/tmp/real_story.txt").write_text(x2, encoding="utf-8")
    page.goto(BASE + "/analyze"); page.click("a:has-text('Upload document')")
    page.set_input_files("input[type=file]", "/tmp/real_story.txt")
    page.click("button:has-text('Analyze')"); page.wait_for_url(re.compile(r".*/results/\d+$"), timeout=90000)
    page.wait_for_selector(".verdict")
    print("   uploaded real article ->", page.locator(".verdict .label").first.inner_text())
    # bad file type is rejected client-side
    page.goto(BASE + "/analyze"); page.click("a:has-text('Upload document')")
    Path("/tmp/x.exe").write_bytes(b"MZ"); page.set_input_files("input[type=file]", "/tmp/x.exe")
    check(page.locator("text=Invalid file format").count() == 1, "upload: .exe rejected with a clear message")

    # ---- history
    page.goto(BASE + "/history"); page.wait_for_selector("tbody tr")
    check(page.locator("tbody tr").count() >= 2, "history: both analyses listed")
    page.fill("input[type=search]", "zzzzqq"); page.wait_for_selector("text=No analyses match your filters")
    check(True, "history: empty search state")
    page.fill("input[type=search]", ""); page.wait_for_selector("tbody tr")
    page.screenshot(path=SHOTS / "09_history.png")
    page.goto(BASE + "/profile"); page.wait_for_selector("text=Personal information"); page.screenshot(path=SHOTS / "10_profile.png")
    page.goto(BASE + "/dashboard"); page.wait_for_selector("text=Recent predictions"); page.screenshot(path=SHOTS / "11_user_dashboard.png")

    # ---- dark mode + mobile
    page.click("button:has-text('Dark mode')"); page.wait_for_timeout(300)
    check(page.evaluate("document.documentElement.dataset.theme") == "dark", "theme: dark mode switches")
    page.goto(BASE + f"/results/{rid}"); page.wait_for_selector("mark.ev"); page.screenshot(path=SHOTS / "12_result_dark.png", full_page=True)
    page.click("button:has-text('Light mode')")
    page.set_viewport_size({"width": 390, "height": 800}); page.goto(BASE + f"/results/{rid}"); page.wait_for_selector(".verdict")
    sw = page.evaluate("document.documentElement.scrollWidth"); check(sw <= 392, f"mobile: no horizontal scrolling (scrollWidth={sw})")
    page.screenshot(path=SHOTS / "13_result_mobile.png"); page.set_viewport_size({"width": 1366, "height": 900})

    # ---- logout; admin
    page.click("button:has-text('Log out')"); page.wait_for_url("**/login")
    page.fill("#f-email", "admin@example.com"); page.fill("#f-password", "Admin12345"); page.click("button:has-text('Log in')")
    page.wait_for_url("**/admin"); page.wait_for_selector("text=Administrator dashboard"); page.wait_for_timeout(1200)
    page.screenshot(path=SHOTS / "14_admin_dashboard.png", full_page=True)
    check(page.locator("canvas").count() >= 4, "admin dashboard: 4 charts rendered")
    for path, marker, shot in [("/admin/users", "Add user", "15_admin_users"), ("/admin/datasets", "Import history", "16_admin_datasets"),
                               ("/admin/news", "Subject categories", "17_admin_news"), ("/admin/models", "Trained models", "18_admin_models"),
                               ("/admin/analytics", "Prediction trend", "19_admin_analytics"), ("/admin/explainability", "Explainability monitoring", "20_admin_explain"),
                               ("/admin/settings", "Stop-word list", "21_admin_settings"), ("/admin/logs", "System logs", "22_admin_logs")]:
        page.goto(BASE + path); page.wait_for_selector(f"text={marker}", timeout=20000); page.wait_for_timeout(900)
        page.screenshot(path=SHOTS / f"{shot}.png", full_page=True); print("   admin page ok:", path)
    page.goto(BASE + "/admin/models"); page.wait_for_selector("text=Trained models")
    page.click("button:has-text('Details') >> nth=0"); page.wait_for_selector("text=ROC curve (test set)")
    page.wait_for_timeout(900); check(page.locator(".modal canvas").count() == 1, "models: ROC curve drawn in the details dialog")
    page.screenshot(path=SHOTS / "23_admin_model_details.png"); page.keyboard.press("Escape")
    page.goto(BASE + "/dashboard"); page.wait_for_url("**/admin"); check(True, "RBAC: admin is kept in the admin interface")
    page.goto(BASE + "/this-does-not-exist"); check(page.locator("text=This page does not exist").count() == 1, "404 page shown")
    b.close()

check(not bad_responses, f"no HTTP 5xx responses {bad_responses}")
real_errors = [e for e in console_errors if "favicon" not in e and "401" not in e and "403" not in e and "409" not in e and "422" not in e and "415" not in e]
check(not real_errors, f"no unexpected console errors {real_errors[:3]}")
print("\nFAILED:", problems if problems else "none"); sys.exit(1 if problems else 0)
