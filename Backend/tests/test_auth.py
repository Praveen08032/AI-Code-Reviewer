import base64
from datetime import timedelta, timezone
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from google.auth.exceptions import TransportError
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import auth
from app.database import get_db, init_db
from app.main import app
from app.models import (AccessToken, AuthSession, Base, ChatConversation, ChatMessage,
                        LoginChallenge, OwnerAccount, SampleAnswer, SignInEvent, Submission, User)


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public_pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.signer = crypt.RSASigner.from_string(private_pem, key_id="test-key")
        cls.certs = json.dumps({"test-key": public_pem.decode()}).encode()

    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com", "OWNER_EMAIL": "owner@gmail.com",
            "OWNER_GOOGLE_SUB": "", "ALLOWED_ORIGINS": "http://localhost:5173", "APP_ENV": "development",
            "OWNER_PROVIDER": "google", "OWNER_SUBJECT": "", "GITHUB_CLIENT_ID": "", "GITHUB_CLIENT_SECRET": "",
            "MICROSOFT_CLIENT_ID": "", "MICROSOFT_CLIENT_SECRET": "",
        })
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
        self.transport = patch("app.auth.VerificationRequest", return_value=lambda *args, **kwargs: SimpleNamespace(status=200, data=self.certs))
        self.transport.start()

    def tearDown(self):
        self.transport.stop()
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.environment.stop()

    def token(self, challenge_nonce, sub="google-user", email="user@gmail.com", **overrides):
        claims = {"iss": "https://accounts.google.com", "aud": os.environ["GOOGLE_CLIENT_ID"],
                  "iat": int(auth.now().replace(tzinfo=timezone.utc).timestamp()),
                  "exp": int((auth.now() + timedelta(minutes=5)).replace(tzinfo=timezone.utc).timestamp()),
                  "sub": sub, "email": email, "email_verified": True, "name": "Google User", "nonce": challenge_nonce}
        claims.update(overrides)
        return jwt.encode(self.signer, claims).decode()

    def login(self, client=None, sub="google-user", email="user@gmail.com", **overrides):
        client = client or self.client
        challenge = client.post("/auth/challenge")
        self.assertEqual(challenge.status_code, 200, challenge.text)
        credential = self.token(challenge.json()["nonce"], sub=sub, email=email, **overrides)
        response = client.post("/auth/google", json={"credential": credential})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), credential

    @staticmethod
    def headers(login):
        return {"Authorization": "Bearer " + login["access_token"]}

    def test_real_signature_verified_and_session_restored_without_google_reauthentication(self):
        login, credential = self.login()
        self.assertEqual(login["user"]["email"], "user@gmail.com")
        self.assertFalse(login["user"]["is_owner"])
        self.assertEqual(self.client.get("/submission-history", headers=self.headers(login)).status_code, 200)
        refreshed = self.client.get("/auth/me")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json()["user"]["id"], login["user"]["id"])
        self.assertNotEqual(refreshed.json()["access_token"], login["access_token"])
        self.assertNotIn("codecheck_session", refreshed.text)
        with self.Session() as db:
            self.assertEqual(db.query(SignInEvent).count(), 1)
            self.assertEqual(db.query(User).one().login_count, 1)
            self.assertTrue(all(row.token_hash != login["access_token"] for row in db.query(AccessToken)))
        self.assertEqual(self.client.post("/auth/google", json={"credential": credential}).status_code, 401)

    def test_rejects_tampered_wrong_audience_expired_unverified_and_wrong_nonce(self):
        for overrides in [{"aud": "other-app"}, {"exp": 1}, {"iss": "https://evil.example"},
                          {"email_verified": False}, {"nonce": "wrong-nonce"}]:
            nonce = self.client.post("/auth/challenge").json()["nonce"]
            response = self.client.post("/auth/google", json={"credential": self.token(nonce, **overrides)})
            self.assertEqual(response.status_code, 401, (overrides, response.text))
        nonce = self.client.post("/auth/challenge").json()["nonce"]
        parts = self.token(nonce).split(".")
        parts[1] = base64.urlsafe_b64encode(json.dumps({"sub": "forged-owner", "email": "owner@gmail.com"}).encode()).rstrip(b"=").decode()
        self.assertEqual(self.client.post("/auth/google", json={"credential": ".".join(parts)}).status_code, 401)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(SignInEvent).count(), 0)

    def test_login_requires_browser_challenge_and_allowed_origin(self):
        self.assertEqual(self.client.post("/auth/google", json={"credential": self.token("nonce")}).status_code, 401)
        self.assertEqual(self.client.post("/auth/challenge", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code, 403)
        nonce = self.client.post("/auth/challenge").json()["nonce"]
        with TestClient(app, headers={"Origin": "http://localhost:5173"}) as other:
            self.assertEqual(other.post("/auth/google", json={"credential": self.token(nonce)}).status_code, 401)

    def test_no_auth_bypass_when_google_config_missing(self):
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "", "OWNER_EMAIL": ""}):
            self.assertTrue(self.client.get("/auth/config").json()["email_password"])
            self.assertEqual(self.client.post("/auth/challenge").status_code, 503)
            for endpoint in ["/sample-questions", "/submission-history", "/chat/conversations", "/admin/users", "/admin/sign-ins"]:
                self.assertEqual(self.client.get(endpoint).status_code, 401, endpoint)
            self.assertEqual(self.client.post("/submit-code", json={"language": "python", "code": "pass"}).status_code, 401)
            self.assertEqual(self.client.post("/chat/messages", json={"message": "hi"}).status_code, 401)
            self.assertEqual(self.client.post("/add-sample-answer", json={"language": "python", "question_title": "q", "ideal_code": "pass"}).status_code, 401)
            self.assertEqual(self.client.delete("/chat/conversations").status_code, 401)

    def test_api_key_pasted_in_client_id_is_not_exposed_as_public_configuration(self):
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "not-an-oauth-client-key"}):
            config = self.client.get("/auth/config").json()
            self.assertTrue(config["email_password"])
            self.assertIsNone(config["client_id"])
            self.assertTrue(all(not provider["enabled"] for provider in config["providers"]))

    def test_google_unavailable_never_creates_a_fake_login(self):
        nonce = self.client.post("/auth/challenge").json()["nonce"]
        with patch("app.auth.verify_google", side_effect=TransportError("network failure")):
            self.assertEqual(self.client.post("/auth/google", json={"credential": self.token(nonce)}).status_code, 503)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(SignInEvent).count(), 0)

    def test_owner_bootstrap_rejects_external_email_without_explicit_subject(self):
        with patch.dict(os.environ, {"OWNER_EMAIL": "owner@example.com"}):
            nonce = self.client.post("/auth/challenge").json()["nonce"]
            credential = self.token(nonce, sub="external-owner", email="owner@example.com")
            self.assertEqual(self.client.post("/auth/google", json={"credential": credential}).status_code, 403)
            with self.Session() as db:
                self.assertEqual(db.query(OwnerAccount).count(), 0)
                self.assertEqual(db.query(User).count(), 0)
            with patch.dict(os.environ, {"OWNER_GOOGLE_SUB": "external-owner"}):
                login, _ = self.login(sub="external-owner", email="owner@example.com")
                self.assertTrue(login["user"]["is_owner"])

    def test_owner_is_configured_account_not_first_visitor_and_legacy_data_is_preserved(self):
        with self.Session() as db:
            db.add(Submission(language="python", code="legacy private code"))
            db.add(ChatConversation(id="legacy-chat", title="Owner old chat"))
            db.add(SampleAnswer(language="python", question_title="private custom problem", ideal_code="legacy sample"))
            db.commit()
        visitor, _ = self.login()
        self.assertFalse(visitor["user"]["is_owner"])
        self.assertEqual(self.client.get("/submission-history", headers=self.headers(visitor)).json(), [])
        self.assertEqual(self.client.get("/chat/conversations", headers=self.headers(visitor)).json(), [])
        self.assertFalse(any(sample["question_title"] == "private custom problem" for sample in self.client.get("/sample-questions", headers=self.headers(visitor)).json()))
        self.assertEqual(self.client.get("/admin/users", headers=self.headers(visitor)).status_code, 403)
        owner, _ = self.login(sub="owner-google-sub", email="owner@gmail.com")
        self.assertTrue(owner["user"]["is_owner"])
        self.assertEqual(len(self.client.get("/submission-history", headers=self.headers(owner)).json()), 1)
        self.assertEqual(len(self.client.get("/chat/conversations", headers=self.headers(owner)).json()), 1)
        users = self.client.get("/admin/users", headers=self.headers(owner)).json()
        self.assertEqual(users["total"], 2)
        self.assertEqual(users["total_sign_ins"], 2)
        self.assertEqual(self.client.get("/admin/sign-ins", headers=self.headers(owner)).json()["total"], 2)
        with self.Session() as db:
            self.assertEqual(db.query(OwnerAccount).one().google_sub, "owner-google-sub")
            self.assertEqual(db.query(Submission).one().user_id, owner["user"]["id"])
        # Even a different verified subject with the same email cannot take over the pinned owner.
        impostor, _ = self.login(sub="different-google-sub", email="owner@gmail.com")
        self.assertFalse(impostor["user"]["is_owner"])
        self.assertEqual(self.client.get("/admin/users", headers=self.headers(impostor)).status_code, 403)

    @patch("app.main.get_gemini_feedback")
    @patch("app.chat.get_chat_reply", return_value="Private reply")
    def test_two_users_cannot_read_modify_or_clear_each_others_reviews_chats_or_samples(self, chat_reply, feedback):
        from test_review import FEEDBACK
        feedback.return_value = FEEDBACK
        first, _ = self.login(sub="first")
        h1 = self.headers(first)
        self.assertEqual(self.client.post("/submit-code", headers=h1, json={"language": "python", "review_mode": "custom", "code": "def first(): return 1"}).status_code, 200)
        chat_id = self.client.post("/chat/messages", headers=h1, json={"message": "First private chat"}).json()["conversation"]["id"]
        self.client.post("/add-sample-answer", headers=h1, json={"language": "python", "question_title": "private problem", "ideal_code": "first secret"})
        with TestClient(app, headers={"Origin": "http://localhost:5173"}) as second_client:
            second, _ = self.login(second_client, sub="second", email="second@gmail.com")
            h2 = self.headers(second)
            self.assertEqual(second_client.get("/submission-history", headers=h2).json(), [])
            self.assertEqual(second_client.get("/chat/conversations", headers=h2).json(), [])
            self.assertFalse(any(row["question_title"] == "private problem" for row in second_client.get("/sample-questions", headers=h2).json()))
            self.assertEqual(second_client.get(f"/chat/conversations/{chat_id}", headers=h2).status_code, 404)
            self.assertEqual(second_client.delete(f"/chat/conversations/{chat_id}", headers=h2).status_code, 404)
            self.assertEqual(second_client.post("/chat/messages", headers=h2, json={"conversation_id": chat_id, "message": "Steal context"}).status_code, 404)
            self.assertEqual(second_client.delete("/chat/conversations", headers=h2).status_code, 204)
        self.assertEqual(len(self.client.get("/submission-history", headers=h1).json()), 1)
        self.assertEqual(len(self.client.get(f"/chat/conversations/{chat_id}", headers=h1).json()["messages"]), 2)
        chat_reply.assert_called_once()

    def test_logout_revokes_access_and_refresh_cookies_and_expired_tokens_fail(self):
        login, _ = self.login()
        self.assertEqual(self.client.post("/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/submission-history", headers=self.headers(login)).status_code, 401)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        with self.Session() as db:
            self.assertEqual(db.query(AuthSession).count(), 0)
            self.assertEqual(db.query(AccessToken).count(), 0)
            self.assertEqual(db.query(SignInEvent).count(), 1)
        login, _ = self.login()
        with self.Session() as db:
            db.query(AccessToken).update({AccessToken.expires_at: auth.now() - timedelta(seconds=1)})
            db.commit()
        self.assertEqual(self.client.get("/submission-history", headers=self.headers(login)).status_code, 401)
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        with self.Session() as db:
            db.query(AuthSession).update({AuthSession.expires_at: auth.now() - timedelta(seconds=1)})
            db.commit()
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_production_cookies_are_secure_httponly_and_same_site_auth_responses_are_not_cached(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            with TestClient(app, base_url="https://app.example", headers={"Origin": "http://localhost:5173"}) as client:
                response = client.post("/auth/challenge")
                self.assertEqual(response.status_code, 200)
                cookie = response.headers["set-cookie"]
                self.assertIn("HttpOnly", cookie)
                self.assertIn("Secure", cookie)
                self.assertIn("SameSite=lax", cookie)
                self.assertIn("Path=/auth", cookie)
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_challenge_expiry_does_not_create_users(self):
        nonce = self.client.post("/auth/challenge").json()["nonce"]
        with self.Session() as db:
            db.query(LoginChallenge).update({LoginChallenge.expires_at: auth.now() - timedelta(seconds=1)})
            db.commit()
        self.assertEqual(self.client.post("/auth/google", json={"credential": self.token(nonce)}).status_code, 401)

    def test_blocked_google_identity_cannot_create_another_session(self):
        visitor, _ = self.login(sub="blocked-google", email="visitor@gmail.com")
        owner, _ = self.login(sub="owner-google", email="owner@gmail.com")
        response = self.client.patch(f"/admin/users/{visitor['user']['id']}/access", json={"blocked": True}, headers=self.headers(owner))
        self.assertEqual(response.status_code, 200)
        nonce = self.client.post("/auth/challenge").json()["nonce"]
        denied = self.client.post("/auth/google", json={"credential": self.token(nonce, sub="blocked-google", email="visitor@gmail.com")})
        self.assertEqual(denied.status_code, 403)
        with self.Session() as db:
            self.assertEqual(db.get(User, visitor["user"]["id"]).login_count, 1)


class MigrationTests(unittest.TestCase):
    def test_existing_users_gain_unblocked_status_without_replacing_their_data(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, google_sub VARCHAR(255) UNIQUE NOT NULL, email VARCHAR(320), name VARCHAR(200), picture TEXT, first_login_at TIMESTAMP, last_login_at TIMESTAMP, last_seen_at TIMESTAMP, login_count INTEGER)"))
            connection.execute(text("INSERT INTO users (id, google_sub, email, name, first_login_at, last_login_at, last_seen_at, login_count) VALUES ('legacy', 'legacy-subject', 'legacy@example.com', 'Legacy user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 3)"))
        with patch("app.database.engine", engine):
            init_db()
            init_db()
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT id, google_sub, login_count, auth_provider, blocked_at FROM users")).one(), ("legacy", "legacy-subject", 3, "google", None))
        engine.dispose()

    def test_additive_migration_keeps_legacy_records_and_is_idempotent(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE submissions (id INTEGER PRIMARY KEY, code TEXT)"))
            connection.execute(text("INSERT INTO submissions (code) VALUES ('keep this code')"))
            connection.execute(text("CREATE TABLE sample_answers (id INTEGER PRIMARY KEY, ideal_code TEXT)"))
            connection.execute(text("CREATE TABLE chat_conversations (id VARCHAR(36) PRIMARY KEY, title TEXT)"))
        with patch("app.database.engine", engine):
            init_db()
            init_db()
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT code, user_id FROM submissions")).one(), ("keep this code", None))
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
