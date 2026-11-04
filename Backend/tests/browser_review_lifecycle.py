"""Browser regression for late responses. Uses mocked API responses, never user data."""
import json
from playwright.sync_api import sync_playwright, expect, Error

FRONTEND = "http://localhost:5173"
API = "http://localhost:9055"


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        failures, pending = [], []
        page = context.new_page()
        page.on("pageerror", lambda error: failures.append(str(error)))
        user = dict(id="lifecycle-test", name="Browser Test", email="browser@example.com", is_owner=False, email_verified=True)
        context.route(FRONTEND + "/auth/me", lambda route: route.fulfill(json={"user": user, "access_token": "test-only"}))
        context.route(API + "/submission-history", lambda route: route.fulfill(json=[]))
        context.route(API + "/sample-questions", lambda route: route.fulfill(json=[dict(id=1, language="python", question_title="two sum", ideal_code="def two_sum(nums, target):\n    return []", description="Find two indices.")]))
        context.route(API + "/submit-code", lambda route: pending.append(route))
        page.goto(FRONTEND + "/submit?lang=python&q=two%20sum")
        expect(page.get_by_role("heading", name="Code Review Agent")).to_be_visible()
        expect(page.locator(".ed-foot")).to_contain_text("2 lines")
        page.get_by_role("button", name="Run review", exact=True).click()
        for _ in range(30):
            if pending:
                break
            page.wait_for_timeout(100)
        assert len(pending) == 1, "Review request was not captured"
        page.get_by_role("link", name="New review", exact=True).click()
        expect(page.locator("#q")).to_have_value("__custom__")
        expect(page.locator(".ed-foot")).to_contain_text("0 chars")
        review = dict(pass_status=True, is_perfect=True, review_complete=True, readability_score=10,
                      efficiency_score=10, similarity_score=100, errors=[], missing_items=[], suggestions=[],
                      corrected_code="def two_sum(nums, target): return []", correctness_reason="Old response")
        try:
            pending[0].fulfill(json=review)
        except Error:
            pass  # An aborted request can no longer be fulfilled, depending on browser version.
        page.wait_for_timeout(6000)  # Covers all workflow and score animations.
        expect(page.locator(".ed-foot")).to_contain_text("0 chars")
        expect(page.locator(".ph .tag")).to_have_count(0)
        expect(page.get_by_role("button", name="Run review", exact=True)).to_be_enabled()
        expect(page.get_by_text("Completed · saved to dashboard", exact=True)).to_have_count(0)
        page.get_by_role("tab", name="Results", exact=True).click()
        expect(page.get_by_text("No results yet", exact=True)).to_be_visible()
        assert not failures, failures
        print(json.dumps({"late_response_after_new_review": "passed", "blank_editor_has_no_old_scores": "passed", "page_errors": failures}))
        browser.close()


if __name__ == "__main__":
    main()
