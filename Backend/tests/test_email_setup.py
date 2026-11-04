import argparse
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from dotenv import dotenv_values
from setup_email import main, save_settings, sender_address, validate_settings


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

    def test_prefilled_sender_targets_its_google_account_and_cancel_keeps_settings_unsaved(self):
        with patch("setup_email.dotenv_values", return_value={}), \
                patch("setup_email.input", side_effect=AssertionError("The sender is already provided")), \
                patch("setup_email.getpass", return_value=""), \
                patch("setup_email.webbrowser.open") as browser, \
                patch("setup_email.save_settings") as save, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            main(["--gmail-address", "sender@gmail.com"])
        opened = urlparse(browser.call_args.args[0])
        self.assertEqual(opened.hostname, "myaccount.google.com")
        self.assertEqual(parse_qs(opened.query)["authuser"], ["sender@gmail.com"])
        self.assertIn("it is not emailed to you", output.getvalue())
        save.assert_not_called()

    def test_sender_rejects_invalid_or_injected_email(self):
        for address in ("not-an-email", "sender@gmail.com\nBcc: other@example.com"):
            with self.assertRaises(argparse.ArgumentTypeError):
                sender_address(address)


if __name__ == "__main__":
    unittest.main()
