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
from app.main import app
from app.models import (AccessToken, AuthSession, Base, ChatConversation, EmailCredential, EmailVerification,
                        OwnerAccount, OwnerInvite, SignInEvent, Submission, User)
from app.password_auth import hash_password, verify_password, password_policy_error
from setup_owner import create_owner_link

PASSWORD = "A long test password!"


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"ALLOWED_ORIGINS": "http://localhost:5173", "APP_ENV": "development",
                                                   "OWNER_EMAIL": "owner@example.com", "OWNER_PROVIDER": "google"})
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

    def register(self, email="person@example.com", **extra):
        response = self.client.post("/auth/register", json={"email": email, "password": PASSWORD, **extra})
        self.assertEqual(response.status_code, 202, response.text)
        confirmed = self.client.post("/auth/verify-email", json={"challenge_token": response.json()["challenge_token"],
                                                               "code": self.sent.call_args.args[1]})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        return confirmed.json()

    def test_real_password_hash_round_trip_random_salts_and_invalid_formats(self):
        first, second = hash_password(PASSWORD), hash_password(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertNotIn(PASSWORD, first)
        self.assertTrue(verify_password(PASSWORD, first))
        self.assertFalse(verify_password(PASSWORD + "wrong", first))
        self.assertFalse(verify_password(PASSWORD, None))
        self.assertFalse(verify_password(PASSWORD, "scrypt$2$8$1$YQ==$Yg=="))

    def test_new_accounts_reject_predictable_passwords_before_creating_any_user(self):
        choices = ["aaaaaaaaaaaa", "a" * 20, "123456789012345", "qwertyuiopasdfgh", "abcabcabcabcabcabc",
                   "passwordpassword", "Password123456789!", "P@ssw0rd123456789!", "CodeCheck12345678!",
                   "person12345678901", "person@example.com"]
        for password in choices:
            with self.subTest(password=choices.index(password)):
                response = self.client.post("/auth/register", json={"email": "person@example.com", "password": password})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(password, response.text)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(EmailCredential).count(), 0)
            self.assertEqual(db.query(AuthSession).count(), 0)
        self.assertFalse(password_policy_error("orchid lantern river pebble"))
        self.assertFalse(password_policy_error("湖辺の静かな景色を眺める午後の時間"))

    def test_registration_never_accepts_a_password_in_place_of_existing_account_login(self):
        self.register()
        for email, password in [("unknown@example.com", PASSWORD), ("person@example.com", "a" * 20)]:
            response = self.client.post("/auth/login", json={"email": email, "password": password})
            self.assertEqual(response.status_code, 401)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual(db.query(SignInEvent).count(), 1)

    def test_register_login_restore_and_logout_use_real_revocable_sessions(self):
        registered = self.register(" Person@Example.COM ")
        self.assertEqual(registered["user"]["email"], "person@example.com")
        self.assertEqual(registered["user"]["provider"], "email")
        self.assertFalse(registered["user"]["is_owner"])
        self.assertEqual(self.client.get("/auth/me").json()["user"]["id"], registered["user"]["id"])
        with self.Session() as db:
            self.assertTrue(db.query(EmailCredential).one().password_hash.startswith("scrypt$131072$8$1$"))
            self.assertEqual(db.query(SignInEvent).count(), 1)
        self.assertEqual(self.client.post("/auth/logout").status_code, 204)
        headers = {"Authorization": "Bearer " + registered["access_token"]}
        self.assertEqual(self.client.get("/submission-history", headers=headers).status_code, 401)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        logged = self.client.post("/auth/login", json={"email": "PERSON@example.com", "password": PASSWORD})
        self.assertEqual(logged.status_code, 200, logged.text)
        self.assertEqual(logged.json()["user"]["id"], registered["user"]["id"])
        with self.Session() as db:
            self.assertEqual(db.query(User).one().login_count, 2)
            self.assertEqual(db.query(SignInEvent).count(), 2)

    def test_wrong_password_unknown_email_and_validation_do_not_leak_passwords(self):
        self.register()
        failures = [self.client.post("/auth/login", json={"email": email, "password": "wrong password"})
                    for email in ["person@example.com", "unknown@example.com"]]
        self.assertEqual([r.status_code for r in failures], [401, 401])
        self.assertEqual(failures[0].json(), failures[1].json())
        for body in [{"email": "bad email", "password": PASSWORD}, {"email": "valid@example.com", "password": "short"},
                     {"email": "valid@example.com", "password": "x" * 129}]:
            response = self.client.post("/auth/register", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(body["password"], response.text)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual(db.query(SignInEvent).count(), 1)

    def test_duplicate_email_cannot_overwrite_password_or_inherit_owner_role(self):
        self.register("owner@example.com")
        duplicate = self.client.post("/auth/register", json={"email": "OWNER@example.com", "password": "Different password!"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.post("/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual(db.query(OwnerAccount).count(), 0)

    def test_cross_origin_auth_is_denied_and_password_is_not_exposed_in_owner_records(self):
        for path in ["/auth/register", "/auth/login"]:
            response = self.client.post(path, headers={"Origin": "https://evil.example"}, json={"email": "owner@example.com", "password": PASSWORD})
            self.assertEqual(response.status_code, 403)
        with self.Session() as db:
            token = create_owner_link("http://localhost:5173", db).split("=", 1)[1]
        login = self.register("owner@example.com", owner_token=token)
        records = self.client.get("/admin/users", headers={"Authorization": "Bearer " + login["access_token"]})
        self.assertEqual(records.status_code, 200)
        self.assertNotIn(PASSWORD, records.text)
        self.assertNotIn("scrypt", records.text)

    def test_invite_is_required_to_claim_owner_and_legacy_data(self):
        with self.Session() as db:
            db.add(Submission(language="python", code="old private code"))
            db.add(ChatConversation(id="legacy-chat", title="Private chat"))
            db.commit()
            token = create_owner_link("http://localhost:5173", db).split("=", 1)[1]
            self.assertIsNotNone(db.get(OwnerInvite, digest(token)))
        visitor = self.register("visitor@example.com")
        visitor_headers = {"Authorization": "Bearer " + visitor["access_token"]}
        self.assertEqual(self.client.get("/admin/users", headers=visitor_headers).status_code, 403)
        self.assertEqual(self.client.get("/submission-history", headers=visitor_headers).json(), [])
        owner = self.register("owner@example.com", owner_token=token)
        self.assertTrue(owner["user"]["is_owner"])
        with self.Session() as db:
            self.assertEqual(db.query(OwnerInvite).count(), 0)
            self.assertEqual(db.query(Submission).one().user_id, owner["user"]["id"])
            self.assertEqual(db.query(ChatConversation).one().user_id, owner["user"]["id"])
            with self.assertRaises(ValueError):
                create_owner_link("http://localhost:5173", db)
        reused = self.client.post("/auth/register", json={"email": "attacker@example.com", "password": PASSWORD, "owner_token": token})
        self.assertEqual(reused.status_code, 400)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 2)

    def test_expired_invite_cannot_create_account_and_existing_user_can_claim_valid_invite(self):
        with self.Session() as db:
            token = create_owner_link("http://localhost:5173", db).split("=", 1)[1]
            db.get(OwnerInvite, digest(token)).expires_at = now() - timedelta(seconds=1)
            db.commit()
        expired = self.client.post("/auth/register", json={"email": "person@example.com", "password": PASSWORD, "owner_token": token})
        self.assertEqual(expired.status_code, 400)
        registered = self.register()
        with self.Session() as db:
            token = create_owner_link("http://localhost:5173", db).split("=", 1)[1]
        owner = self.client.post("/auth/login", json={"email": "person@example.com", "password": PASSWORD, "owner_token": token})
        self.assertEqual(owner.status_code, 200, owner.text)
        self.assertTrue(owner.json()["user"]["is_owner"])
        self.assertEqual(owner.json()["user"]["id"], registered["user"]["id"])

    def test_login_throttling_is_persistent_and_applies_to_unknown_accounts(self):
        with patch("app.password_auth.verify_password", return_value=False) as verify:
            for _ in range(10):
                self.assertEqual(self.client.post("/auth/login", json={"email": "unknown@example.com", "password": PASSWORD}).status_code, 401)
            blocked = self.client.post("/auth/login", json={"email": "unknown@example.com", "password": PASSWORD})
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(verify.call_count, 10)
            self.assertEqual(blocked.headers["retry-after"], "900")

    def test_email_users_have_private_reviews_and_cannot_use_each_others_sessions(self):
        first = self.register("first@example.com")
        second = self.register("second@example.com")
        with self.Session() as db:
            db.add(Submission(language="python", code="first private code", user_id=first["user"]["id"]))
            db.add(Submission(language="python", code="second private code", user_id=second["user"]["id"]))
            db.commit()
        first_rows = self.client.get("/submission-history", headers={"Authorization": "Bearer " + first["access_token"]})
        # Signing into a second account revokes the previous browser session.
        self.assertEqual(first_rows.status_code, 401)
        second_rows = self.client.get("/submission-history", headers={"Authorization": "Bearer " + second["access_token"]}).json()
        self.assertEqual([row["code"] for row in second_rows], ["second private code"])


if __name__ == "__main__":
    unittest.main()
