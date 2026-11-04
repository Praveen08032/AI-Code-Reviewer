import os
import unittest
import json
from unittest.mock import patch

# Keep all tests independent of the local database and external Gemini service.
os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.ai_utils import parse_ai_feedback, is_perfect_review
from app.default_answers import DEFAULT_ANSWERS, DEFAULT_SAMPLES, TWO_SUM_DESCRIPTION, seed_default_answers
from app.main import app, get_db
from app.models import Base, SampleAnswer, Submission
from app.similarity import calculate_similarity
from app.auth import get_current_user
from auth_helpers import add_test_user


FEEDBACK = '''### Correctness
Status: correct
Reason: The solution checks complements before inserting each index, handles duplicates and uses O(n) expected time and O(n) space.
### Bugs
* None
### Missing items
* None
### Suggestions
* None
### Scores
Readability: 10/10
Efficiency: 10/10
### Improved Version
```python
def add(a, b):
    return a + b
```
'''


class SimilarityTests(unittest.TestCase):
    def test_python_formatting_docs_annotations_and_driver(self):
        ideal = DEFAULT_ANSWERS["python"]
        version = ideal.replace("def two_sum(nums, target):", 'def two_sum(nums: list[int], target: int) -> list[int]:\n    """Find indices."""')
        version += '\n\nif __name__ == "__main__":\n    print(two_sum([2, 7], 9))\n'
        self.assertEqual(calculate_similarity(ideal, version), 100)

    def test_changed_logic_and_invalid_indentation_are_not_perfect(self):
        ideal = DEFAULT_ANSWERS["python"]
        self.assertLess(calculate_similarity(ideal, ideal.replace("target - num", "target + num")), 100)
        self.assertLess(calculate_similarity(ideal, ideal.replace("    seen = {}", "seen = {}")), 100)

    def test_python_strings_and_indentation_keep_their_meaning(self):
        self.assertLess(calculate_similarity('def f():\n    return "a b"', 'def f():\n    return "a   b"'), 100)
        self.assertLess(calculate_similarity('def f(x):\n    if x:\n        return 1\n    return 2',
                                            'def f(x):\n    if x:\n        return 1\n        return 2'), 100)

    def test_javascript_comments_driver_and_string_literals(self):
        ideal = DEFAULT_ANSWERS["javascript"]
        self.assertEqual(calculate_similarity(ideal, '// example\n' + ideal + '\nconsole.log(twoSum([2, 7], 9));', "javascript"), 100)
        self.assertLess(calculate_similarity('function f() { return "https://a b"; }',
                                            'function f() { return "https://ab"; }', "javascript"), 100)

    def test_braced_driver_is_ignored_but_main_only_logic_is_kept(self):
        ideal = DEFAULT_ANSWERS["cpp"]
        self.assertEqual(calculate_similarity(ideal, ideal + '\nint main() { twoSum({2, 7}, 9); return 0; }', "cpp"), 100)
        self.assertLess(calculate_similarity('int main() { return 1; }', 'int main() { return 2; }', "cpp"), 100)

    def test_significant_newlines_cannot_be_normalized_into_perfect_match(self):
        self.assertLess(calculate_similarity('function f() { return [1]; }',
                                            'function f() { return\n[1]; }', "javascript"), 100)
        self.assertLess(calculate_similarity('func f() int { return 1 }',
                                            'func f() int { return\n1 }', "go"), 100)
        self.assertLess(calculate_similarity('def f\n  return 1\nend',
                                            'def f\n  return\n  1\nend', "ruby"), 100)

    def test_all_references_exact_match_and_empty_input(self):
        for language, code in DEFAULT_ANSWERS.items():
            with self.subTest(language=language):
                self.assertEqual(calculate_similarity(code, code, language), 100)
                self.assertEqual(calculate_similarity(code, "", language), 0)
        self.assertEqual(calculate_similarity("", ""), 0)


class ReviewFlowTests(unittest.TestCase):
    def setUp(self):
        self.quota = patch.dict(os.environ, {"REVIEW_REQUESTS_PER_MINUTE": "1000"})
        self.quota.start()
        self.addCleanup(self.quota.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.user = add_test_user(self.Session)
        app.dependency_overrides[get_current_user] = lambda: self.user

        def get_test_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = get_test_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def test_seed_is_idempotent_and_preserves_existing_answers(self):
        with self.Session() as db:
            db.add(SampleAnswer(language="python", question_title="two sum", ideal_code="custom answer"))
            db.commit()
            seed_default_answers(db)
            seed_default_answers(db)
            self.assertEqual(db.query(SampleAnswer).count(), sum(map(len, DEFAULT_SAMPLES.values())))
            self.assertEqual(db.query(SampleAnswer).filter_by(language="python", question_title="two sum").one().ideal_code, "custom answer")

    @patch("app.main.get_gemini_feedback", return_value=FEEDBACK)
    def test_all_ten_languages_review_and_save(self, gemini):
        with self.Session() as db:
            seed_default_answers(db)
        samples = self.client.get("/sample-questions").json()
        self.assertEqual(len(samples), sum(map(len, DEFAULT_SAMPLES.values())))
        self.assertTrue(all(sample["description"] for sample in samples))
        for language, code in DEFAULT_ANSWERS.items():
            with self.subTest(language=language):
                response = self.client.post("/submit-code", json={"language": language, "question_title": "two sum", "code": code})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["similarity_score"], 100)
                self.assertEqual(result["errors"], [])
                self.assertTrue(result["pass_status"])
                self.assertTrue(result["is_perfect"])
                self.assertEqual(result["correctness_status"], "correct")
        self.assertEqual(gemini.call_count, 10)
        gemini.assert_called_with("ruby", DEFAULT_ANSWERS["ruby"], "two sum", TWO_SUM_DESCRIPTION, "exercise")
        history = self.client.get("/submission-history").json()
        self.assertEqual(len(history), 10)
        self.assertTrue(all(review["is_perfect"] for review in history))

    def test_parser_none_bullets_and_score_bounds(self):
        parsed = parse_ai_feedback(FEEDBACK.replace("10/10", "12/10"))
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["suggestions"], [])
        self.assertIsNone(parsed["readability_score"])
        self.assertFalse(is_perfect_review(parsed))
        self.assertEqual(parsed["corrected_code"], "def add(a, b):\n    return a + b")

    @patch("app.main.get_gemini_feedback", return_value=FEEDBACK)
    def test_new_questions_use_their_own_reference_and_requirements(self, gemini):
        with self.Session() as db:
            seed_default_answers(db)
        for language, title in [("python", "flatten nested list"), ("javascript", "debounce function"),
                                ("typescript", "unique by key"), ("csharp", "group words by length")]:
            sample = DEFAULT_SAMPLES[language][title]
            response = self.client.post("/submit-code", json={"language": language, "question_title": title,
                                                              "code": sample["ideal_code"]})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["similarity_score"], 100)
            gemini.assert_called_with(language, sample["ideal_code"], title, sample["description"], "exercise")

    @patch("app.main.get_gemini_feedback", return_value=FEEDBACK)
    def test_custom_reviews_ignore_sample_selection_for_all_languages(self, gemini):
        with self.Session() as db:
            seed_default_answers(db)
        for language in DEFAULT_ANSWERS:
            with self.subTest(language=language):
                response = self.client.post("/submit-code", json={
                    "language": language, "review_mode": "custom", "question_title": "two sum",
                    "task_description": "Calculate the sum of two arguments.", "code": "my own program",
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsNone(response.json()["similarity_score"])
                self.assertIsNone(response.json()["is_similar_to_sample"])
                gemini.assert_called_with(language, "my own program", "", "Calculate the sum of two arguments.", "custom")

    @patch("app.main.get_gemini_feedback", return_value=FEEDBACK)
    def test_custom_review_allows_no_exercise_or_description(self, gemini):
        response = self.client.post("/submit-code", json={"language": "python", "code": "def add(a, b): return a + b", "review_mode": "custom"})
        self.assertEqual(response.status_code, 200)
        gemini.assert_called_once_with("python", "def add(a, b): return a + b", "", "", "custom")

    @patch("app.main.get_gemini_feedback")
    def test_missing_requirements_are_returned_saved_and_block_perfect(self, gemini):
        gemini.return_value = FEEDBACK.replace("### Missing items\n* None", "### Missing items\n* The required empty-input case is not handled.")
        response = self.client.post("/submit-code", json={"language": "python", "review_mode": "custom", "code": "def f(): pass"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["missing_items"], ["The required empty-input case is not handled."])
        self.assertFalse(result["is_perfect"])
        self.assertFalse(result["pass_status"])
        history = self.client.get("/submission-history").json()
        self.assertEqual(history[0]["missing_items"], result["missing_items"])

    @patch("app.ai_utils._generate")
    def test_custom_prompt_preserves_program_purpose_and_drops_exercise_context(self, model):
        from app.ai_utils import get_gemini_feedback
        model.return_value = json.dumps({key: value for key, value in parse_ai_feedback(FEEDBACK).items() if key != "review_complete"})
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-not-a-real-key"}):
            get_gemini_feedback("python", "def factorial(n): return 0", "two sum", "Return n factorial.", "custom")
        prompt = model.call_args.args[0]
        self.assertIn("def factorial(n): return 0", prompt)
        self.assertIn("Return n factorial.", prompt)
        self.assertEqual(json.loads(prompt)["context"]["review_mode"], "custom")
        self.assertNotIn("two sum", prompt)
        self.assertIn("cause and consequence", model.call_args.args[1].system_instruction)
        self.assertEqual(model.call_args.args[1].response_mime_type, "application/json")

    def test_perfect_requires_complete_correct_review_and_no_issues(self):
        self.assertTrue(is_perfect_review(parse_ai_feedback(FEEDBACK)))
        for feedback in [
            FEEDBACK.replace("Status: correct", "Status: incorrect"),
            FEEDBACK.replace("Status: correct", "Status: uncertain"),
            FEEDBACK.replace("### Correctness", "### Other"),
            FEEDBACK.replace("### Bugs\n* None", "### Bugs\n"),
            FEEDBACK.replace("### Suggestions\n* None", "### Suggestions\n"),
            FEEDBACK.replace("### Missing items\n* None", "### Missing items\nSomething is missing."),
            FEEDBACK.split("### Improved Version")[0],
            FEEDBACK.replace("def add(a, b):\n    return a + b", ""),
            FEEDBACK.replace("### Bugs\n* None", "### Bugs\n* Returns the wrong indices."),
            FEEDBACK.replace("### Suggestions\n* None", "### Suggestions\n* Fix a necessary bounds check."),
            FEEDBACK.replace("Readability: 10/10", "Readability: 9/10"),
            FEEDBACK.replace("Readability: 10/10", "Readability: -10/10"),
            FEEDBACK.replace("Readability: 10/10", "Readability: 10.5/10"),
            FEEDBACK.replace("Readability: 10/10", ""),
        ]:
            with self.subTest(feedback=feedback):
                self.assertFalse(is_perfect_review(parse_ai_feedback(feedback)))

    @patch("app.main.get_gemini_feedback")
    def test_reference_match_does_not_override_incorrect_or_incomplete_review(self, gemini):
        with self.Session() as db:
            seed_default_answers(db)
        for feedback in [FEEDBACK.replace("Status: correct", "Status: incorrect"),
                         FEEDBACK.replace("### Correctness", "### Other")]:
            gemini.return_value = feedback
            response = self.client.post("/submit-code", json={"language": "python", "question_title": "two sum", "code": DEFAULT_ANSWERS["python"]})
            result = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(result["similarity_score"], 100)
            self.assertFalse(result["pass_status"])
            self.assertFalse(result["is_perfect"])
        self.assertTrue(all(not review["is_perfect"] for review in self.client.get("/submission-history").json()))

    def test_legacy_full_scores_do_not_imply_verified_perfect(self):
        with self.Session() as db:
            db.add(Submission(language="python", user_id=self.user.id, code="return []", pass_status=True,
                              readability_score=10, efficiency_score=10, errors="",
                              raw_ai_feedback="### Scores\nReadability: 10/10\nEfficiency: 10/10"))
            db.commit()
        self.assertFalse(self.client.get("/submission-history").json()[0]["is_perfect"])


if __name__ == "__main__":
    unittest.main()
