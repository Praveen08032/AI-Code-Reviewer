"""Create a private, one-use owner setup link from the backend terminal."""
import argparse
from datetime import timedelta
import secrets
from urllib.parse import urlsplit
import webbrowser

from app.auth import digest, now
from app.database import init_db, SessionLocal
from app.models import EmailCredential, EmailVerification, OwnerAccount, OwnerInvite, User


def restore_owner_access(email, db):
    """Local operator approval for the already pinned owner; not inbox verification.

    This is deliberately unavailable through HTTP. Matching an email alone never
    creates an owner, changes its identity, or bypasses the existing password.
    """
    pinned = db.get(OwnerAccount, 1)
    user = db.query(User).filter_by(google_sub=pinned.google_sub).first() if pinned else None
    if not user or user.auth_provider != "email" or user.email.casefold() != email.strip().casefold():
        raise ValueError("The email must match the existing pinned email/password owner account.")
    credential = db.get(EmailCredential, user.id)
    if not credential or credential.email.casefold() != user.email.casefold():
        raise ValueError("The pinned owner does not have a matching email/password credential.")
    pinned.local_access_approved_at = now()
    # Discard pending pre-recovery registrations; they cannot replace the owner's
    # established password after the local operator approves the account.
    db.query(EmailVerification).filter_by(email=credential.email).delete(synchronize_session=False)
    db.commit()


def create_owner_link(origin, db):
    parsed = urlsplit(origin)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if (parsed.scheme != "https" and not (local and parsed.scheme == "http")) or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Use the HTTPS frontend origin, or http://localhost:5173 for local setup.")
    if db.get(OwnerAccount, 1):
        raise ValueError("An owner already exists. Sign in with that account; this tool cannot replace it.")
    token = secrets.token_urlsafe(32)
    db.query(OwnerInvite).delete(synchronize_session=False)
    db.add(OwnerInvite(token_hash=digest(token), expires_at=now() + timedelta(hours=1)))
    db.commit()
    return origin.rstrip("/") + "/#owner-setup=" + token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://localhost:5173")
    parser.add_argument("--open", action="store_true", help="Open privately in the browser instead of printing the setup link.")
    parser.add_argument("--restore-access", action="store_true", help="Approve only the existing pinned owner's access locally, preserving their password.")
    parser.add_argument("--email", help="Exact email of the existing pinned owner, required for --restore-access.")
    args = parser.parse_args()
    init_db()
    try:
        with SessionLocal() as db:
            if args.restore_access:
                if not args.email:
                    raise ValueError("Supply --email for the existing pinned owner account.")
                restore_owner_access(args.email, db)
                print("Existing owner access restored. Sign in with the same CodeCheck password. Inbox verification was not changed.")
                return
            link = create_owner_link(args.origin, db)
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    if args.open:
        if not webbrowser.open(link):
            parser.exit(1, "The browser could not be opened. Run without --open to show a private setup link.\n")
        print("Owner account form opened. Choose your email and password there. The link expires in one hour.")
    else:
        print("Private owner setup link (one use, expires in one hour; do not share):\n" + link)


if __name__ == "__main__":
    main()
