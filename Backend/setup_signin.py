"""Interactive, local-only OAuth setup. Run with the project's Python environment."""
from getpass import getpass
from pathlib import Path
import re
from uuid import UUID
import webbrowser

from dotenv import dotenv_values, set_key

ENV_FILE = Path(__file__).resolve().parent / ".env"
ALLOWED_KEYS = {"GOOGLE_CLIENT_ID", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET",
                "MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET", "MICROSOFT_TENANT_ID", "OWNER_EMAIL"}
PROVIDERS = [
    ("Google", "https://console.cloud.google.com/auth/clients", "GOOGLE_CLIENT_ID", None,
     "Select or create a Google Cloud project. Complete Google Auth Platform branding\n"
     "with the app name CodeCheck AI and your support/contact email.\n"
     "Choose External audience so other Google accounts can sign in.\n"
     "Create a Web application OAuth client.\n"
     "Authorized JavaScript origins:\n"
     "  http://localhost\n  http://localhost:5173\n  https://codereviewer8.netlify.app\n"
     "The Client ID ends in .apps.googleusercontent.com. No client secret is needed.\n"
     "This is separate from the Gemini API key; this app requests basic identity only."),
    ("GitHub", "https://github.com/settings/applications/new", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET",
     "Create an OAuth App named CodeCheck AI. For LOCAL testing:\n"
     "  Homepage: http://localhost:5173\n"
     "  Authorization callback: http://localhost:5173/auth/github/callback\n"
     "For the hosted site, use a separate OAuth App with:\n"
     "  Homepage: https://codereviewer8.netlify.app\n"
     "  Callback: https://codereviewer8.netlify.app/auth/github/callback\n"
     "Enter the LOCAL app's Client ID and generated client secret below."),
    ("Microsoft", "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
     "MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET",
     "Create an App registration named CodeCheck AI. Supported account types:\n"
     "  Accounts in any organizational directory AND personal Microsoft accounts.\n"
     "Add Web redirect URIs:\n"
     "  http://localhost:5173/auth/microsoft/callback\n"
     "  https://codereviewer8.netlify.app/auth/microsoft/callback\n"
     "Copy the Application (client) ID. Create a client secret and copy its VALUE, not its ID."),
]


def validate_value(key, value):
    if key not in ALLOWED_KEYS or not value or any(char in value for char in "\r\n\x00"):
        raise ValueError("Enter a nonempty, single-line configuration value.")
    if key == "GOOGLE_CLIENT_ID" and not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", value):
        raise ValueError("This must be a Google OAuth Web Client ID, not a Gemini API key.")
    if key == "MICROSOFT_CLIENT_ID":
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("The Microsoft Application (client) ID must be a UUID.") from error
    if key == "OWNER_EMAIL" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("Enter the Google email address you will use to sign in.")


def save_settings(updates, path=ENV_FILE):
    # Validate the entire step before changing anything. Never accept arbitrary
    # setting names or print credential values; preserve unrelated configuration.
    for key, value in updates.items():
        validate_value(key, value)
    for key, value in updates.items():
        set_key(path, key, value, quote_mode="always")


def read_value(key, prompt, secret=False):
    while True:
        value = (getpass(prompt) if secret else input(prompt)).strip()
        if not value:
            return None
        try:
            validate_value(key, value)
            return value
        except ValueError as error:
            print(error)


def main():
    print("CODECHECK AI - SIGN-IN SETUP\n")
    print("The provider app registrations must be created in accounts you control.")
    print("This helper opens their official pages and saves app credentials only in Backend/.env.")
    print("Existing Gemini/database settings are preserved. Secrets are hidden as you paste them.")
    print("Do not enter your provider password here; sign in on the provider's website.\n")
    for name, url, client_key, secret_key, instructions in PROVIDERS:
        values = dotenv_values(ENV_FILE)
        existing = bool(values.get(client_key) and (not secret_key or values.get(secret_key)))
        print("\n" + name.upper() + "\n" + instructions + "\n")
        action = input(("Already configured. Type CHANGE to replace, or press Enter to keep: " if existing
                        else "Press Enter to open registration, or type SKIP for now: ")).strip().lower()
        if (existing and action != "change") or action == "skip":
            continue
        webbrowser.open(url)
        client_id = read_value(client_key, "Paste the Client ID (Enter to skip): ")
        if not client_id:
            continue
        updates = {client_key: client_id}
        if secret_key:
            secret = read_value(secret_key, "Paste the client secret VALUE (hidden; Enter to skip): ", secret=True)
            if not secret:
                print("Skipped; no settings for this provider were changed.")
                continue
            updates[secret_key] = secret
        if name == "Google" and not values.get("OWNER_EMAIL"):
            email = read_value("OWNER_EMAIL", "Your owner Google email (unlocks your private user-access page): ")
            if email:
                updates["OWNER_EMAIL"] = email
        if name == "Microsoft" and not values.get("MICROSOFT_TENANT_ID"):
            updates["MICROSOFT_TENANT_ID"] = "common"
        save_settings(updates)
        print(name + " configuration saved. Credential values were not printed.")
    print("\nSaved. Return to Codex and say DONE so the backend can be restarted and checked.")
    input("Press Enter to close this setup window.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Any completed provider steps remain saved.")
