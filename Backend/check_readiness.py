"""Read-only configuration and deployment checks. Never prints secrets or sends email."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
import httpx

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", help="Optional deployed frontend HTTPS origin; tests the sign-in proxy without logging in.")
    args = parser.parse_args()
    checks = []
    def check(name, passed, detail, optional=False):
        checks.append({"check": name, "status": "pass" if passed else "warning" if optional else "needs_setup", "detail": detail})
    from app.mailer import mail_configured
    from app.database import engine, SessionLocal
    from app.models import OwnerAccount
    from sqlalchemy import text
    check("gemini_key", bool(os.getenv("GEMINI_API_KEY", "").strip()), "Presence only; this does not test provider quota.")
    check("verification_sender", mail_configured(), "Run setup_email.py with a real SMTP sender if missing; inbox delivery is required for public registration.")
    production = os.getenv("APP_ENV", "development") == "production"
    check("persistent_hosted_database", engine.dialect.name == "postgresql", "Use persistent PostgreSQL when hosting; local SQLite is suitable for development.", optional=not production)
    origins = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "").split(",") if item.strip()]
    check("frontend_origins", bool(origins) and all(urlparse(item).scheme in ({"https"} if production else {"http", "https"}) and urlparse(item).netloc and not urlparse(item).path.strip("/") for item in origins), "Production requires explicit HTTPS frontend origins.")
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            owner = db.query(OwnerAccount).first()
            check("database", True, "Connection succeeded; no records were changed.")
            check("pinned_owner", bool(owner), "An owner must be assigned using the private setup_owner.py flow.", optional=True)
    except Exception:
        check("database", False, "Could not read application tables. Start the backend once to apply its additive migrations.")
    if args.site:
        origin = args.site.rstrip("/")
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path:
            parser.error("--site must be an HTTPS origin without credentials or a path")
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.get(origin + "/auth/config")
            config = response.json() if "application/json" in response.headers.get("content-type", "") else {}
            check("live_signin_proxy", response.status_code == 200 and config.get("email_password") is True,
                  "The frontend /auth/config must return backend JSON, not the SPA HTML. Set VITE_API_BASE_URL and rebuild Netlify if this fails.")
            if config.get("email_password"):
                check("live_verification_sender", config.get("email_delivery_ready") is True, "The deployed backend must have its own SMTP settings.")
        except (httpx.HTTPError, ValueError):
            check("live_signin_proxy", False, "The deployed sign-in endpoint could not be verified.")
    print(json.dumps({"checks": checks, "ready_for_public_signup": all(item["status"] != "needs_setup" for item in checks)}, indent=2))
    return 1 if any(item["status"] == "needs_setup" for item in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
