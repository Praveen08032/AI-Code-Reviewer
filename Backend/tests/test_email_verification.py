from datetime import timedelta
import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.auth import digest, now
from app.database import get_db
from app.mailer import EmailDeliveryError
from app.main import app
from app.models import (AccessToken, AuthSession, Base, EmailCredential, EmailVerification,
                        OwnerAccount, SignInEvent, Submission, User)
from app.password_auth import hash_password
from setup_owner import create_owner_link

PASSWORD = "Orchid lantern river pebble!"
EMAIL = "person@example.com"


class EmailVerificationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"ALLOWED_ORIGINS": "http://localhost:5173", "APP_ENV": "development"})
        self.environment.start()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        def test_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app, headers={"Origin": "http://localhost:5173"})
        self.mail_ready = patch("app.password_auth.mail_configured", return_value=True)
        self.mail_ready.start()
        self.delivery = patch("app.password_auth.send_verification_email")
        self.sent = self.delivery.start()

    def tearDown(self):
        self.delivery.stop()
        self.mail_ready.stop()
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.environment.stop()

    def begin(self, **extra):
        response = self.client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, **extra})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json(), self.sent.call_args.args[1]

    def confirm(self, pending, code):
        return self.client.post("/auth/verify-email", json={"challenge_token": pending["challenge_token"], "code": code})

    def legacy(self, password=PASSWORD):
        with self.Session() as db:
            user = User(id="legacy-email-user", google_sub="email:legacy-email-user", auth_provider="email", email=EMAIL,
                        name="Legacy user", first_login_at=now(), last_login_at=now(), last_seen_at=now(), login_count=1)
            db.add(user)
            db.flush()
            db.add(EmailCredential(user_id=user.id, email=EMAIL, password_hash=hash_password(password)))
            db.add(AuthSession(token_hash=digest("old-session"), user_id=user.id, created_at=now(), expires_at=now() + timedelta(days=1)))
            db.flush()
            db.add(AccessToken(token_hash=digest("old-access"), session_hash=digest("old-session"), expires_at=now() + timedelta(minutes=5)))
            db.add(Submission(language="python", code="preserved private code", user_id=user.id))
            db.commit()

    def test_no_user_or_session_until_correct_single_use_inbox_code(self):
        pending, code = self.begin()
        self.assertNotIn("access_token", pending)
        self.assertNotIn("code", pending)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(AuthSession).count(), 0)
            row = db.query(EmailVerification).one()
            self.assertNotEqual(row.token_hash, pending["challenge_token"])
            self.assertNotEqual(row.code_hash, code)
            self.assertNotEqual(row.password_hash, PASSWORD)
        wrong = "000001" if code != "000001" else "000002"
        self.assertEqual(self.confirm(pending, wrong).status_code, 400)
        result = self.confirm(pending, code)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["user"]["email_verified"])
        self.assertEqual(self.confirm(pending, code).status_code, 400)
        with self.Session() as db:
            self.assertIsNotNone(db.query(EmailCredential).one().verified_at)
            self.assertEqual(db.query(SignInEvent).count(), 1)
            self.assertEqual(db.query(EmailVerification).count(), 0)

    def test_missing_sender_blocks_signup_instead_of_fake_verification(self):
        with patch("app.password_auth.mail_configured", return_value=False):
            response = self.client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(response.status_code, 503)
        self.sent.assert_not_called()
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(EmailVerification).count(), 0)

    def test_mail_failure_removes_pending_code_and_never_grants_a_session(self):
        self.sent.side_effect = EmailDeliveryError("provider rejected delivery")
        response = self.client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("provider rejected", response.text)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(EmailVerification).count(), 0)
            self.assertEqual(db.query(AuthSession).count(), 0)

    def test_expired_code_five_attempt_limit_and_resend_rotates_token_and_code(self):
        with patch("app.password_auth.secrets.randbelow", side_effect=[123456, 654321]):
            pending, first_code = self.begin()
            self.assertEqual(self.client.post("/auth/resend-verification", json={"challenge_token": pending["challenge_token"]}).status_code, 429)
            for _ in range(5):
                self.assertEqual(self.confirm(pending, "999999").status_code, 400)
            self.assertEqual(self.confirm(pending, first_code).status_code, 429)
            with self.Session() as db:
                row = db.query(EmailVerification).one()
                row.created_at = now() - timedelta(minutes=2)
                row.expires_at = now() - timedelta(seconds=1)
                db.commit()
            self.assertEqual(self.confirm(pending, first_code).status_code, 400)
            resent = self.client.post("/auth/resend-verification", json={"challenge_token": pending["challenge_token"]})
            self.assertEqual(resent.status_code, 202, resent.text)
            self.assertNotEqual(pending["challenge_token"], resent.json()["challenge_token"])
            self.assertEqual(self.confirm(pending, first_code).status_code, 400)
            self.assertEqual(self.confirm(resent.json(), "654321").status_code, 200)

    def test_legacy_unverified_accounts_and_old_sessions_must_verify_before_access(self):
        self.legacy()
        self.client.cookies.set("codecheck_session", "old-session")
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/submission-history", headers={"Authorization": "Bearer old-access"}).status_code, 401)
        response = self.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(response.status_code, 202)
        confirmed = self.confirm(response.json(), self.sent.call_args.args[1])
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["user"]["id"], "legacy-email-user")
        self.assertEqual(self.client.get("/submission-history", headers={"Authorization": "Bearer old-access"}).status_code, 401)
        history = self.client.get("/submission-history", headers={"Authorization": "Bearer " + confirmed.json()["access_token"]})
        self.assertEqual([row["code"] for row in history.json()], ["preserved private code"])

    def test_inbox_owner_replaces_an_unverified_preregistration_password(self):
        self.legacy(password="Earlier attacker password!")
        pending, code = self.begin()
        self.assertEqual(self.confirm(pending, code).status_code, 200)
        self.assertEqual(self.client.post("/auth/login", json={"email": EMAIL, "password": "Earlier attacker password!"}).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code, 200)

    def test_owner_claim_and_legacy_assignment_wait_for_email_verification(self):
        with self.Session() as db:
            db.add(Submission(language="python", code="old anonymous code"))
            db.commit()
            token = create_owner_link("http://localhost:5173", db).split("=", 1)[1]
        pending, code = self.begin(owner_token=token)
        with self.Session() as db:
            self.assertIsNone(db.get(OwnerAccount, 1))
            self.assertIsNone(db.query(Submission).one().user_id)
        result = self.confirm(pending, code)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["user"]["is_owner"])
        with self.Session() as db:
            self.assertEqual(db.query(Submission).one().user_id, result.json()["user"]["id"])

    def test_verification_requires_allowed_origin_and_never_echoes_codes(self):
        pending, code = self.begin()
        response = self.client.post("/auth/verify-email", headers={"Origin": "https://evil.example"}, json={"challenge_token": pending["challenge_token"], "code": code})
        self.assertEqual(response.status_code, 403)
        response = self.confirm(pending, "123")
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("123", response.text)
        self.assertNotIn(pending["challenge_token"], response.text)


if __name__ == "__main__":
    unittest.main()
