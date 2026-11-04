import os
import smtplib
import unittest
from unittest.mock import MagicMock, patch

from app.mailer import EmailDeliveryError, mail_configured, send_verification_email


class MailerTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465", "SMTP_SECURITY": "ssl",
            "SMTP_USERNAME": "sender@example.com", "SMTP_PASSWORD": "test-smtp-secret", "SMTP_FROM": "sender@example.com"})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def connection(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.send_message.return_value = {}
        return connection

    def test_smtp_ssl_authentication_and_message_contain_code_not_password(self):
        connection = self.connection()
        with patch("app.mailer.smtplib.SMTP_SSL", return_value=connection) as smtp:
            send_verification_email("recipient@example.com", "012345")
        self.assertEqual(smtp.call_args.args, ("smtp.example.com", 465))
        self.assertIn("context", smtp.call_args.kwargs)
        connection.login.assert_called_once_with("sender@example.com", "test-smtp-secret")
        message = connection.send_message.call_args.args[0]
        self.assertEqual(message["To"], "recipient@example.com")
        self.assertIn("012345", message.get_content())
        self.assertNotIn("test-smtp-secret", str(message))

    def test_starttls_is_required_before_credentials_are_sent(self):
        connection = self.connection()
        with patch.dict(os.environ, {"SMTP_SECURITY": "starttls", "SMTP_PORT": "587"}), patch("app.mailer.smtplib.SMTP", return_value=connection):
            send_verification_email("recipient@example.com", "012345")
        names = [call[0] for call in connection.mock_calls]
        self.assertLess(names.index("starttls"), names.index("login"))
        connection.starttls.assert_called_once()

    def test_bad_credentials_tls_settings_and_recipient_failure_never_fall_back(self):
        for change in [{"SMTP_PASSWORD": ""}, {"SMTP_SECURITY": "none"}, {"SMTP_FROM": "sender@example.com\nBcc: victim@example.com"}]:
            with patch.dict(os.environ, change):
                self.assertFalse(mail_configured())
                with self.assertRaises(EmailDeliveryError):
                    send_verification_email("recipient@example.com", "012345")
        connection = self.connection()
        connection.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
        with patch("app.mailer.smtplib.SMTP_SSL", return_value=connection):
            with self.assertRaises(EmailDeliveryError):
                send_verification_email("recipient@example.com", "012345")
        connection.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
