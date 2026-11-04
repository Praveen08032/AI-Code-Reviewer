"""Real browser + API checks with a disposable DB and test-only mail transport.

Run from the repo with a Python that has Playwright. The backend uses its venv.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

BACKEND = Path(__file__).resolve().parents[1]
PYTHON = BACKEND / "venv" / "Scripts" / "python.exe"
FRONTEND = "http://localhost:5173"
TEST_API = "http://127.0.0.1:9066"


def main():
    with tempfile.TemporaryDirectory(prefix="codecheck-email-browser-") as temporary:
        environment = {**os.environ, "DATABASE_URL": "sqlite:///" + (Path(temporary) / "test.db").as_posix(),
                       "APP_ENV": "development", "ALLOWED_ORIGINS": FRONTEND, "OWNER_PROVIDER": "google",
                       "GOOGLE_CLIENT_ID": "", "GITHUB_CLIENT_ID": "", "MICROSOFT_CLIENT_ID": "",
                       "BROWSER_TEST_MAILBOX": str(Path(temporary) / "mailbox.json")}
        server_code = """import json, os
from pathlib import Path
import app.password_auth as passwords
import app.mailer as mailer
def capture_test_mail(recipient, code):
    Path(os.environ['BROWSER_TEST_MAILBOX']).write_text(json.dumps({'recipient': recipient, 'code': code}))
passwords.send_verification_email = capture_test_mail
passwords.mail_configured = lambda: True
mailer.mail_configured = lambda: True
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=9066)
"""
        server = subprocess.Popen([str(PYTHON), "-c", server_code],
                                  cwd=BACKEND, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for _ in range(150):
                if server.poll() is not None:
                    raise RuntimeError("Disposable backend did not start")
                try:
                    with urlopen(TEST_API + "/auth/config", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Disposable backend timed out")
            link_code = "from setup_owner import create_owner_link; from app.database import SessionLocal; db=SessionLocal(); print(create_owner_link('http://localhost:5173', db)); db.close()"
            owner_link = subprocess.check_output([str(PYTHON), "-c", link_code], cwd=BACKEND, env=environment, text=True).strip()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 960})
                failures = []
                context.on("page", lambda page: page.on("pageerror", lambda error: failures.append(str(error))))

                def real_api(route):
                    request = route.request
                    is_auth = request.url.startswith(FRONTEND + "/auth/")
                    path = request.url.split("/", 3)[3]
                    response = route.fetch(url=TEST_API + "/" + path)
                    headers = {**response.headers, "access-control-allow-origin": FRONTEND, "access-control-allow-credentials": "true"}
                    if not is_auth:
                        headers["access-control-allow-headers"] = "authorization,content-type"
                    route.fulfill(response=response, headers=headers)

                context.route(FRONTEND + "/auth/**", real_api)
                context.route("http://localhost:9055/**", real_api)
                page = context.new_page()

                def verify_inbox(recipient):
                    expect(page.get_by_role("heading", name="Verify your email")).to_be_visible(timeout=20000)
                    expect(page.get_by_role("heading", name="Dashboard")).to_have_count(0)
                    message = json.loads(Path(environment["BROWSER_TEST_MAILBOX"]).read_text())
                    assert message["recipient"] == recipient
                    wrong = "000001" if message["code"] != "000001" else "000002"
                    page.get_by_label("Verification code").fill(wrong)
                    page.get_by_role("button", name="Verify email & continue").click()
                    expect(page.get_by_role("alert")).to_have_text("That code is incorrect. Check your email and try again.")
                    page.get_by_label("Verification code").fill(message["code"])
                    page.get_by_role("button", name="Verify email & continue").click()
                    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=20000)

                page.goto(FRONTEND)
                expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
                expect(page.get_by_role("button", name="Continue with", exact=False)).to_have_count(0)
                expect(page.get_by_text("Setup required", exact=True)).to_have_count(0)
                page.get_by_role("button", name="Create account", exact=True).first.click()
                page.get_by_label("Email address").fill("browser-user@example.com")
                page.get_by_label("Password", exact=True).fill("a" * 20)
                page.get_by_role("button", name="Create account", exact=True).last.click()
                expect(page.get_by_role("alert")).to_have_text("Avoid repeated characters or repeated password patterns.")
                page.get_by_label("Password", exact=True).fill("Browser testing password!")
                page.get_by_role("button", name="Show password").click()
                expect(page.get_by_label("Password", exact=True)).to_have_attribute("type", "text")
                page.get_by_role("button", name="Hide password").click()
                page.get_by_role("button", name="Create account", exact=True).last.click()
                verify_inbox("browser-user@example.com")
                page.reload()
                expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=20000)
                page.goto(FRONTEND + "/access")
                expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
                page.get_by_role("button", name="Account: browser-user", exact=True).click()
                page.get_by_role("button", name="Sign out", exact=True).click()
                expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
                page.get_by_label("Email address").fill("browser-user@example.com")
                page.get_by_label("Password", exact=True).fill("Wrong password!")
                page.get_by_role("button", name="Sign in", exact=True).last.click()
                expect(page.get_by_role("alert")).to_have_text("Email or password is incorrect.")
                page.get_by_label("Password", exact=True).fill("Browser testing password!")
                page.get_by_role("button", name="Sign in", exact=True).last.click()
                expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=20000)
                page.get_by_role("button", name="Account: browser-user", exact=True).click()
                page.get_by_role("button", name="Sign out", exact=True).click()
                expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()

                page.goto(owner_link)
                expect(page.get_by_role("heading", name="Your owner account")).to_be_visible()
                expect(page).to_have_url(FRONTEND + "/")
                page.get_by_label("Email address").fill("browser-owner@example.com")
                page.get_by_label("Password", exact=True).fill("Owner browser password!")
                page.get_by_role("button", name="Create account", exact=True).last.click()
                verify_inbox("browser-owner@example.com")
                page.goto(FRONTEND + "/access")
                expect(page.get_by_role("heading", name="User access")).to_be_visible()
                expect(page.get_by_role("cell", name="browser-user@example.com Verified", exact=True)).to_be_visible()
                expect(page.get_by_role("cell", name="browser-owner@example.com Verified", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Block browser-owner@example.com", exact=True)).to_have_count(0)
                visitor_context = browser.new_context(viewport={"width": 1280, "height": 900})
                visitor_context.route(FRONTEND + "/auth/**", real_api)
                visitor_context.route("http://localhost:9055/**", real_api)
                visitor_page = visitor_context.new_page()
                visitor_page.on("pageerror", lambda error: failures.append(str(error)))
                visitor_page.goto(FRONTEND)
                visitor_page.get_by_label("Email address").fill("browser-user@example.com")
                visitor_page.get_by_label("Password", exact=True).fill("Browser testing password!")
                visitor_page.get_by_role("button", name="Sign in", exact=True).last.click()
                expect(visitor_page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=20000)
                row = page.get_by_role("row").filter(has=page.get_by_role("cell", name="browser-user@example.com Verified", exact=True))
                page.get_by_role("button", name="Block browser-user@example.com", exact=True).click()
                expect(row.locator(".access-status")).to_have_text("Blocked")
                expect(page.get_by_role("button", name="Unblock browser-user@example.com", exact=True)).to_be_visible()
                visitor_page.reload()
                expect(visitor_page.get_by_role("heading", name="Welcome back")).to_be_visible()
                visitor_page.get_by_label("Email address").fill("browser-user@example.com")
                visitor_page.get_by_label("Password", exact=True).fill("Browser testing password!")
                visitor_page.get_by_role("button", name="Sign in", exact=True).last.click()
                expect(visitor_page.get_by_role("alert")).to_have_text("Your account has been blocked by the site owner.")
                page.get_by_role("button", name="Unblock browser-user@example.com", exact=True).click()
                expect(row.locator(".access-status")).to_have_text("Active")
                visitor_page.get_by_role("button", name="Sign in", exact=True).last.click()
                expect(visitor_page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=20000)
                visitor_context.close()
                for path, title in [("/", "Dashboard"), ("/sample-questions", "Sample Library"), ("/add-sample", "Add Sample"),
                                    ("/history-submissions", "History"), ("/submit", "Code Review Agent"), ("/access", "User access")]:
                    page.goto(FRONTEND + path)
                    expect(page.get_by_role("heading", name=title)).to_be_visible()
                    expect(page.get_by_role("switch", name="Night mode")).to_have_count(1)
                    before = page.get_by_role("switch", name="Night mode").get_attribute("aria-checked")
                    page.get_by_role("switch", name="Night mode").click()
                    expect(page.locator("html")).to_have_attribute("data-theme", "light" if before == "true" else "dark")
                page.get_by_role("button", name="Account: browser-owner", exact=True).click()
                page.get_by_role("button", name="Sign out", exact=True).click()
                expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
                page.goto(FRONTEND)
                for width in [1440, 390, 360]:
                    page.set_viewport_size({"width": width, "height": 900})
                    for theme in [False, True]:
                        switch = page.get_by_role("switch", name="Night mode")
                        if (switch.get_attribute("aria-checked") == "true") != theme:
                            switch.click()
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, theme)
                        expect(page.get_by_label("Email address")).to_be_visible()
                        expect(page.get_by_role("button", name="Sign in", exact=True).last).to_be_visible()
                if failures:
                    raise AssertionError(failures)
                print(json.dumps({"registration_and_required_inbox_code": "passed", "login_wrong_and_correct": "passed", "reload_and_logout": "passed",
                                  "owner_invite_and_access_gate": "passed", "owner_block_unblock_and_visitor_lockout": "passed", "theme_toggle_all_six_pages": "passed", "day_night_desktop_mobile": "passed", "page_errors": failures}))
                browser.close()
        finally:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
