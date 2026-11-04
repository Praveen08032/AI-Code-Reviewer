"""TLS-only SMTP delivery. Verification codes are never logged or returned by APIs."""
from email.message import EmailMessage
from email.utils import parseaddr
import os
import smtplib
import ssl


class EmailDeliveryError(Exception):
    pass


def mail_settings():
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip()
    security = os.getenv("SMTP_SECURITY", "ssl").strip().lower()
    try:
        port = int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587"))
    except ValueError:
        return None
    if (not all([host, username, password, sender]) or security not in {"ssl", "starttls"} or
            not 1 <= port <= 65535 or any(c in sender for c in "\r\n") or
            parseaddr(sender)[1] != sender or "@" not in sender):
        return None
    return {"host": host, "port": port, "username": username, "password": password, "sender": sender, "security": security}


def mail_configured():
    return mail_settings() is not None


def smtp_connection(settings):
    context = ssl.create_default_context()
    if settings["security"] == "ssl":
        connection = smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=15, context=context)
    else:
        connection = smtplib.SMTP(settings["host"], settings["port"], timeout=15)
        try:
            connection.ehlo()
            connection.starttls(context=context)
            connection.ehlo()
        except Exception:
            connection.close()
            raise
    try:
        connection.login(settings["username"], settings["password"])
    except Exception:
        connection.close()
        raise
    return connection


def send_verification_email(recipient, code):
    settings = mail_settings()
    if not settings:
        raise EmailDeliveryError("Email delivery is not configured")
    message = EmailMessage()
    message["From"] = "CodeCheck AI <" + settings["sender"] + ">"
    message["To"] = recipient
    message["Subject"] = "Your CodeCheck email verification code"
    message.set_content(f"Your CodeCheck verification code is: {code}\n\n"
                        "This code expires in 10 minutes and can be used once.\n"
                        "Enter it only in the CodeCheck app where you requested it.\n"
                        "If you did not request this code, ignore this email. Your account will not be activated.\n")
    try:
        with smtp_connection(settings) as connection:
            if connection.send_message(message):
                raise EmailDeliveryError("Recipient was not accepted")
    except (OSError, smtplib.SMTPException, ValueError) as error:
        raise EmailDeliveryError("Verification email could not be sent") from error
