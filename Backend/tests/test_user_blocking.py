from datetime import timedelta
import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.auth import BLOCKED_MESSAGE, digest, now
from app.database import get_db
from app.main import app
from app.models import (AccessToken, AuthSession, Base, ChatConversation, EmailCredential,
                        EmailVerification, OwnerAccount, SignInEvent, Submission, User)
from app.password_auth import hash_password

PASSWORD = "Orchid lantern river password!"


class UserBlockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password(PASSWORD)

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
        with self.Session() as db:
            for identity in ["owner", "visitor", "other"]:
                db.add(User(id=identity, google_sub="email:" + identity, auth_provider="email", email=identity + "@example.com",
                            name=identity, first_login_at=now(), last_login_at=now(), last_seen_at=now(), login_count=0))
                db.flush()
                db.add(EmailCredential(user_id=identity, email=identity + "@example.com", password_hash=self.password_hash, verified_at=now()))
            db.add(OwnerAccount(id=1, google_sub="email:owner", local_access_approved_at=now()))
            db.add(Submission(language="python", code="preserve visitor review", user_id="visitor"))
            db.add(ChatConversation(id="visitor-chat", user_id="visitor", title="Preserve visitor chat"))
            db.commit()
        self.owner = self.login(self.client, "owner")

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.environment.stop()

    def login(self, client, identity):
        response = client.post("/auth/login", json={"email": identity + "@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def headers(login):
        return {"Authorization": "Bearer " + login["access_token"]}

    def change(self, identity, blocked):
        return self.client.patch(f"/admin/users/{identity}/access", json={"blocked": blocked}, headers=self.headers(self.owner))

    def test_only_owner_can_block_unblock_and_cannot_block_the_owner(self):
        visitor_client = TestClient(app, headers={"Origin": "http://localhost:5173"})
        visitor = self.login(visitor_client, "visitor")
        for blocked in [True, False]:
            self.assertEqual(visitor_client.patch("/admin/users/other/access", json={"blocked": blocked}).status_code, 401)
            self.assertEqual(visitor_client.patch("/admin/users/other/access", json={"blocked": blocked}, headers=self.headers(visitor)).status_code, 403)
        self.assertEqual(self.change("owner", True).status_code, 400)
        self.assertEqual(self.change("missing", True).status_code, 404)
        self.assertEqual(self.client.patch("/admin/users/visitor/access", json={"blocked": "false"}, headers=self.headers(self.owner)).status_code, 422)
        self.assertEqual(self.client.patch("/admin/users/visitor/access", json={"blocked": True}, headers={**self.headers(self.owner), "Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        visitor_client.close()

    def test_block_revokes_every_session_and_preserves_user_reviews_and_chats(self):
        visitor_clients = [TestClient(app, headers={"Origin": "http://localhost:5173"}) for _ in range(2)]
        logins = [self.login(client, "visitor") for client in visitor_clients]
        response = self.change("visitor", True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["is_blocked"])
        self.assertIsNotNone(response.json()["blocked_at"])
        for client, login in zip(visitor_clients, logins):
            self.assertEqual(client.get("/auth/me").status_code, 401)
            self.assertEqual(client.get("/submission-history", headers=self.headers(login)).status_code, 401)
            denied = client.post("/auth/login", json={"email": "visitor@example.com", "password": PASSWORD})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["detail"], BLOCKED_MESSAGE)
            client.close()
        with self.Session() as db:
            self.assertEqual(db.query(AuthSession).filter_by(user_id="visitor").count(), 0)
            self.assertEqual(db.query(User).count(), 3)
            self.assertEqual(db.query(Submission).filter_by(user_id="visitor").count(), 1)
            self.assertEqual(db.query(ChatConversation).filter_by(user_id="visitor").count(), 1)
            self.assertEqual(db.query(SignInEvent).filter_by(user_id="visitor").count(), 2)

    def test_unblock_requires_new_sign_in_and_block_is_persistent_and_idempotent(self):
        visitor_client = TestClient(app, headers={"Origin": "http://localhost:5173"})
        login = self.login(visitor_client, "visitor")
        first = self.change("visitor", True)
        second = self.change("visitor", True)
        self.assertEqual(first.json()["blocked_at"], second.json()["blocked_at"])
        rows = self.client.get("/admin/users", headers=self.headers(self.owner)).json()["items"]
        self.assertTrue(next(row for row in rows if row["id"] == "visitor")["is_blocked"])
        self.assertFalse(self.change("visitor", False).json()["is_blocked"])
        self.assertEqual(visitor_client.get("/submission-history", headers=self.headers(login)).status_code, 401)
        fresh = self.login(visitor_client, "visitor")
        history = visitor_client.get("/submission-history", headers=self.headers(fresh))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["code"], "preserve visitor review")
        visitor_client.close()

    def test_blocked_status_is_checked_even_if_an_old_token_still_exists(self):
        visitor_client = TestClient(app, headers={"Origin": "http://localhost:5173"})
        login = self.login(visitor_client, "visitor")
        with self.Session() as db:
            db.get(User, "visitor").blocked_at = now()
            db.commit()
        self.assertEqual(visitor_client.get("/auth/me").status_code, 403)
        self.assertEqual(visitor_client.get("/submission-history", headers=self.headers(login)).status_code, 403)
        self.assertEqual(visitor_client.get("/chat/conversations", headers=self.headers(login)).status_code, 403)
        visitor_client.close()

    def test_blocked_accounts_cannot_reregister_or_activate_an_old_email_code(self):
        with self.Session() as db:
            db.add(EmailVerification(token_hash=digest("old-challenge"), email="visitor@example.com", password_hash=self.password_hash,
                                    code_hash=digest("old-challenge:123456"), attempts=0, created_at=now(), expires_at=now() + timedelta(minutes=10)))
            db.commit()
        self.assertEqual(self.change("visitor", True).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(EmailVerification).count(), 0)
        self.assertEqual(self.client.post("/auth/verify-email", json={"challenge_token": "old-challenge", "code": "123456"}).status_code, 400)
        self.assertEqual(self.client.post("/auth/register", json={"email": "visitor@example.com", "password": PASSWORD}).status_code, 403)
        # Even an unexpectedly retained challenge cannot clear the blocked state.
        with self.Session() as db:
            db.add(EmailVerification(token_hash=digest("retained"), email="visitor@example.com", password_hash=self.password_hash,
                                    code_hash=digest("retained:654321"), attempts=0, created_at=now(), expires_at=now() + timedelta(minutes=10)))
            db.commit()
        self.assertEqual(self.client.post("/auth/verify-email", json={"challenge_token": "retained", "code": "654321"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
