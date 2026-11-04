from pathlib import Path
import tempfile
import unittest
from dotenv import dotenv_values
from setup_email import save_settings, validate_settings


class EmailSetupTests(unittest.TestCase):
    def settings(self):
        return {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465", "SMTP_SECURITY": "ssl",
                "SMTP_USERNAME": "sender@example.com", "SMTP_PASSWORD": "fixture-secret-'quoted'", "SMTP_FROM": "sender@example.com"}

    def test_save_preserves_existing_ai_and_database_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("GEMINI_API_KEY=fixture-key\nDATABASE_URL=sqlite:///fixture.db\n", encoding="utf-8")
            save_settings(self.settings(), path)
            values = dotenv_values(path)
            self.assertEqual(values["GEMINI_API_KEY"], "fixture-key")
            self.assertEqual(values["DATABASE_URL"], "sqlite:///fixture.db")
            self.assertEqual(values["SMTP_PASSWORD"], self.settings()["SMTP_PASSWORD"])

    def test_insecure_or_injected_settings_are_rejected_before_write(self):
        for changes in [{"SMTP_SECURITY": "none"}, {"SMTP_PORT": "0"}, {"SMTP_FROM": "bad\nBcc: victim@example.com"}, {"SMTP_PASSWORD": ""}]:
            with self.assertRaises(ValueError):
                validate_settings({**self.settings(), **changes})


if __name__ == "__main__":
    unittest.main()
