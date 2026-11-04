from datetime import timedelta
import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.auth import digest, now
from app.database import get_db
from app.main import app
from app.models import (AuthSession, Base, EmailCredential, EmailVerification, OwnerAccount, User)
from app.password_auth import hash_password
from setup_owner import restore_owner_access

PASSWORD = "An existing owner password!"


class OwnerRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password(PASSWORD)

    def setUp(self):
        self.environment = patch.dict(os.environ, {"ALLOWED_ORIGINS": "http://localhost:5173", "APP_ENV": "development"})
        self.environment.start()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        def test_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app, headers={"Origin": "http://localhost:5173"})
        self.mail = patch("app.password_auth.mail_configured", return_value=False)
        self.mail.start()
        with self.Session() as db:
            for identity in ["owner", "visitor"]:
                db.add(User(id=identity, google_sub="email:" + identity, auth_provider="email", email=identity + "@example.com",
                            name=identity, first_login_at=now(), last_login_at=now(), last_seen_at=now(), login_count=1))
                db.flush()
                db.add(EmailCredential(user_id=identity, email=identity + "@example.com", password_hash=self.password_hash))
            db.add(OwnerAccount(id=1, google_sub="email:owner"))
            db.commit()

    def tearDown(self):
        self.mail.stop()
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.environment.stop()

    def login(self, email="owner@example.com", **extra):
        return self.client.post("/auth/login", json={"email": email, "password": PASSWORD, **extra})

    def test_operator_approval_restores_existing_owner_with_same_password_and_no_mail(self):
        self.assertEqual(self.login().status_code, 503)
        with self.Session() as db:
            restore_owner_access(" OWNER@example.com ", db)
            self.assertEqual(db.get(EmailCredential, "owner").password_hash, self.password_hash)
            self.assertIsNone(db.get(EmailCredential, "owner").verified_at)
        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)
        user = response.json()["user"]
        self.assertEqual(user["id"], "owner")
        self.assertTrue(user["is_owner"])
        self.assertTrue(user["owner_access_approved"])
        self.assertFalse(user["email_verified"])
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        self.assertEqual(self.client.get("/admin/users", headers={"Authorization": "Bearer " + response.json()["access_token"]}).status_code, 200)
        self.assertEqual(self.client.post("/auth/login", json={"email": "owner@example.com", "password": "Wrong password!"}).status_code, 401)

    def test_approval_cannot_be_requested_by_http_or_granted_to_a_visitor(self):
        self.assertEqual(self.login(owner_access_approved=True).status_code, 503)
        self.assertEqual(self.client.post("/auth/restore-access", json={"email": "owner@example.com"}).status_code, 404)
        with self.Session() as db:
            with self.assertRaises(ValueError):
                restore_owner_access("visitor@example.com", db)
            self.assertIsNone(db.get(OwnerAccount, 1).local_access_approved_at)
            restore_owner_access("owner@example.com", db)
        self.assertEqual(self.login("visitor@example.com").status_code, 503)
        response = self.client.post("/auth/register", json={"email": "new@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.post("/auth/register", json={"email": "owner@example.com", "password": PASSWORD}).status_code, 409)

    def test_existing_owner_session_restores_after_approval_without_resetting_identity(self):
        with self.Session() as db:
            db.add(AuthSession(token_hash=digest("old-owner-session"), user_id="owner", created_at=now(), expires_at=now() + timedelta(days=1)))
            db.commit()
        self.client.cookies.set("codecheck_session", "old-owner-session")
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        with self.Session() as db:
            restore_owner_access("owner@example.com", db)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], "owner")

    def test_recovery_clears_only_owner_pending_requests_and_preserves_other_accounts(self):
        with self.Session() as db:
            for identity in ["owner", "visitor"]:
                db.add(EmailVerification(token_hash=digest(identity), email=identity + "@example.com", password_hash=self.password_hash,
                                        code_hash=digest("fixture"), attempts=0, created_at=now(), expires_at=now() + timedelta(minutes=10)))
            db.commit()
            restore_owner_access("owner@example.com", db)
            self.assertEqual(db.query(User).count(), 2)
            self.assertEqual(db.get(OwnerAccount, 1).google_sub, "email:owner")
            self.assertEqual([pending.email for pending in db.query(EmailVerification)], ["visitor@example.com"])
            self.assertIsNone(db.get(EmailCredential, "visitor").verified_at)


if __name__ == "__main__":
    unittest.main()
