"""Configure a verification-email sender locally without exposing secrets in chat."""
import argparse
from getpass import getpass
from pathlib import Path
import re
import smtplib
from urllib.parse import urlencode
import webbrowser

from dotenv import dotenv_values, set_key
from app.mailer import smtp_connection

ENV_FILE = Path(__file__).resolve().parent / ".env"
SETTING_KEYS = {"SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"}


def validate_settings(values):
    if set(values) != SETTING_KEYS or any(not value or any(c in value for c in "\r\n\x00") for value in values.values()):
        raise ValueError("Complete all six SMTP settings with single-line values.")
    if values["SMTP_SECURITY"] not in {"ssl", "starttls"} or not values["SMTP_PORT"].isdigit() or not 1 <= int(values["SMTP_PORT"]) <= 65535:
        raise ValueError("Use SSL or STARTTLS with a valid port.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["SMTP_FROM"]):
        raise ValueError("Enter a valid sender email address.")


def save_settings(values, path=ENV_FILE):
    validate_settings(values)
    for key, value in values.items():
        set_key(path, key, value, quote_mode="always")


def sender_address(value):
    value = value.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise argparse.ArgumentTypeError("Enter a valid sender email address.")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gmail-address", type=sender_address,
                        help="Use this Gmail sender and open Google settings for that account.")
    args = parser.parse_args(argv)
    print("CODECHECK AI - VERIFICATION EMAIL SETUP\n")
    print("This configures the ONE sender account that mails verification codes to users.")
    print("Users still sign in with email/password; they do not need provider app registration.")
    print("Credentials are saved only in Backend/.env. Gemini/database settings are preserved.")
    print("Hidden password input does not show characters as you paste.\n")
    existing = dotenv_values(ENV_FILE)
    if all(existing.get(key) for key in SETTING_KEYS):
        if input("Email settings already exist. Type CHANGE to replace, or Enter to keep: ").strip().lower() != "change":
            return
    gmail = bool(args.gmail_address) or input("Press Enter for a Gmail sender, or type CUSTOM for another SMTP provider: ").strip().lower() != "custom"
    if gmail:
        sender = args.gmail_address or sender_address(input("Sender Gmail address: "))
        print(f"\nVerification emails will be sent FROM {sender}.")
        print("\nGoogle requires 2-Step Verification and a separate 16-character APP PASSWORD.")
        print("The Google page opens for this sender. Confirm the account email before continuing.")
        print("1. If needed, turn on 2-Step Verification in Google Account > Security.")
        print("2. On App passwords, enter CodeCheck AI as the app name and choose Create.")
        print("3. Google SHOWS the app password on that page; it is not emailed to you.")
        print("4. Paste it into the hidden prompt below. Do not use your usual Gmail password.")
        webbrowser.open("https://myaccount.google.com/apppasswords?" + urlencode({"authuser": sender}))
        values = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "465", "SMTP_SECURITY": "ssl", "SMTP_USERNAME": sender, "SMTP_FROM": sender}
    else:
        values = {"SMTP_HOST": input("SMTP host: ").strip(), "SMTP_PORT": input("SMTP port [587]: ").strip() or "587",
                  "SMTP_SECURITY": input("Security, ssl or starttls [starttls]: ").strip().lower() or "starttls",
                  "SMTP_USERNAME": input("SMTP username: ").strip(), "SMTP_FROM": input("Sender email address: ").strip()}
    while True:
        secret = getpass("Paste the SMTP/app password (hidden; Enter to cancel): ")
        if gmail:
            secret = secret.replace(" ", "")
        if not secret:
            print("Cancelled. Email settings were not changed.")
            return
        if gmail and not re.fullmatch(r"[A-Za-z0-9]{16}", secret):
            print("Use the 16-character Google app password, not your normal account password.")
            continue
        values["SMTP_PASSWORD"] = secret
        try:
            validate_settings(values)
            settings = {"host": values["SMTP_HOST"], "port": int(values["SMTP_PORT"]), "security": values["SMTP_SECURITY"],
                        "username": values["SMTP_USERNAME"], "password": secret, "sender": values["SMTP_FROM"]}
            print("Checking the secure SMTP connection and sender login...")
            with smtp_connection(settings):
                pass
        except smtplib.SMTPAuthenticationError:
            print("Sender login was rejected. Check the username and SMTP/app password. Nothing was saved.")
            continue
        except (OSError, smtplib.SMTPException, ValueError):
            print("Could not establish the secure SMTP connection. Check the host, port and provider settings. Nothing was saved.")
            return
        save_settings(values)
        print("\nSender login checked and settings saved. Return to Codex and say DONE to restart the backend.")
        print("No verification codes or credentials were printed.")
        input("Press Enter to close this setup window.")
        return


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt, argparse.ArgumentTypeError) as error:
        if isinstance(error, argparse.ArgumentTypeError):
            print(str(error))
        print("\nStopped. Only completed setup steps were saved.")
