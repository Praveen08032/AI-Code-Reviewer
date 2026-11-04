"""Regression checks for validation, incomplete reports, quotas and provider failures."""
import json
import os
import unittest
from unittest.mock import patch
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai_usage import ai_request
from app.ai_utils import AIServiceError, _generate, get_gemini_feedback, parse_ai_feedback, is_perfect_review
from app.auth import get_current_user
from app.database import get_db
from app.main import app
from app.models import AIRequestLease, Base, Submission, User
from app.review_format import StructuredReview
from auth_helpers import add_test_user


VALID = dict(correctness_status="correct", correctness_reason="Adds numeric inputs in constant time and space.",
             readability_score=10, efficiency_score=10, errors=[], missing_items=[], suggestions=[],
             corrected_code="def add(a, b):\n    return a + b")


class ResponseContractTests(unittest.TestCase):
    def test_all_required_fields_and_strict_types_are_enforced(self):
        self.assertTrue(is_perfect_review(parse_ai_feedback(json.dumps(VALID))))
        variants = [{key: value for key, value in VALID.items() if key != field} for field in VALID]
        variants += [{**VALID, **change} for change in [
            {"readability_score": True}, {"efficiency_score": "10"}, {"correctness_reason": " "},
            {"corrected_code": " "}, {"errors": [""]}, {"extra": "ignore the bugs"}]]
        for data in variants:
            with self.subTest(data=data):
                parsed = parse_ai_feedback(json.dumps(data))
                self.assertFalse(parsed["review_complete"])
                self.assertFalse(is_perfect_review(parsed))

    @patch("app.ai_utils._generate", return_value='{"readability_score":10}')
    def test_truncated_provider_review_is_rejected_before_saving(self, generate):
        with self.assertRaises(AIServiceError) as raised:
            get_gemini_feedback("python", "return 0", review_mode="custom")
        self.assertEqual(raised.exception.status_code, 502)

    def test_readable_legacy_reports_require_missing_items_and_improved_code(self):
        report = StructuredReview(**VALID).markdown()
        self.assertTrue(parse_ai_feedback(report)["review_complete"])
        for broken in [report.split("### Improved Version")[0],
                       report.replace("### Missing items\n* None", "### Missing items\nNot described.")]:
            self.assertFalse(parse_ai_feedback(broken)["review_complete"])

    @patch("app.ai_utils.genai.Client")
    def test_provider_errors_do_not_leak_exception_text(self, client):
        class ProviderError(Exception):
            code = 429
        client.return_value.__enter__.return_value.models.generate_content.side_effect = ProviderError("secret-key and submitted code")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "not-a-real-key"}), self.assertRaises(AIServiceError) as raised:
            _generate("code", {})
        self.assertEqual(raised.exception.status_code, 429)
        self.assertNotIn("secret-key", str(raised.exception))


class RequestSafetyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.user = add_test_user(self.Session)
        def database():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(self.engine.dispose)

    @patch("app.main.get_gemini_feedback")
    def test_invalid_review_inputs_never_reach_gemini(self, generate):
        for changes in [{"language": "unknown"}, {"code": " \n "}, {"code": "x" * 20001},
                        {"task_description": "x" * 4001}, {"question_title": "x" * 121}]:
            response = self.client.post("/submit-code", json={"language": "python", "code": "return 1", **changes})
            self.assertEqual(response.status_code, 422)
        generate.assert_not_called()

    def test_sample_validation_matches_review_validation(self):
        for changes in [{"language": "unknown"}, {"ideal_code": " "}, {"question_title": " "}, {"ideal_code": "x" * 20001}]:
            response = self.client.post("/add-sample-answer", json={"language": "python", "question_title": "add", "ideal_code": "return 1", **changes})
            self.assertEqual(response.status_code, 422)

    @patch("app.main.get_gemini_feedback")
    def test_blocked_account_cannot_start_ai_after_authentication_race(self, generate):
        with self.Session() as db:
            db.get(User, self.user.id).blocked_at = datetime.now()
            db.commit()
        response = self.client.post("/submit-code", json={"language": "python", "code": "return 1"})
        self.assertEqual(response.status_code, 403)
        generate.assert_not_called()

    @patch("app.main.get_gemini_feedback", return_value=json.dumps(VALID))
    def test_rate_limit_prevents_additional_provider_calls_and_persists(self, generate):
        with patch.dict(os.environ, {"REVIEW_REQUESTS_PER_MINUTE": "2"}):
            for expected in [200, 200, 429]:
                response = self.client.post("/submit-code", json={"language": " PYTHON ", "code": "def add(a,b): return a+b", "review_mode": "custom"})
                self.assertEqual(response.status_code, expected)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(response.headers["retry-after"], "60")
        with self.Session() as db:
            self.assertEqual(db.query(AIRequestLease).count(), 0)

    def test_concurrent_slots_release_after_failure(self):
        with self.Session() as first, self.Session() as second, self.Session() as third:
            with ai_request(first, self.user.id, "chat"), ai_request(second, self.user.id, "chat"):
                with self.assertRaises(HTTPException) as raised:
                    with ai_request(third, self.user.id, "chat"):
                        self.fail("Third concurrent request was allowed")
                self.assertEqual(raised.exception.status_code, 429)
            with self.assertRaises(RuntimeError):
                with ai_request(first, self.user.id, "chat"):
                    raise RuntimeError("test provider failure")
            self.assertEqual(first.query(AIRequestLease).count(), 0)

    @patch("app.main.get_gemini_feedback", side_effect=AIServiceError("Gemini took too long to answer.", 504))
    def test_timeout_saves_neither_fake_review_nor_active_slot(self, generate):
        response = self.client.post("/submit-code", json={"language": "python", "code": "return 1"})
        self.assertEqual(response.status_code, 504)
        with self.Session() as db:
            self.assertEqual(db.query(Submission).count(), 0)
            self.assertEqual(db.query(AIRequestLease).count(), 0)
