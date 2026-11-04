import base64
from datetime import timedelta, timezone
import json
import logging
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse

os.environ["DATABASE_URL"] = "sqlite://"

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt
import msal
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import auth, oauth
from app.database import get_db
from app.main import app
from app.models import Base, OAuthFlow, OwnerAccount, SignInEvent, User

CLIENT = "11111111-1111-4111-8111-111111111111"
TENANT = "22222222-2222-4222-8222-222222222222"
OBJECT = "33333333-3333-4333-8333-333333333333"


class MicrosoftServer:
    def __init__(self, private_key):
        self.private_key = private_key
        self.nonce = None
        self.challenge = None
        self.bad_nonce = False
        self.bad_signature = False
        self.bad_audience = False
        self.bad_issuer = False
        self.no_email = False
        self.posts = []

    def get(self, url, **kwargs):
        if ".well-known/openid-configuration" not in url:
            raise AssertionError("Unexpected metadata URL: " + url)
        return httpx.Response(200, json={
            "authorization_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "issuer": "https://login.microsoftonline.com/{tenantid}/v2.0",
            "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        })

    def post(self, url, data=None, **kwargs):
        self.posts.append(data)
        challenge = base64.urlsafe_b64encode(__import__("hashlib").sha256(data["code_verifier"].encode()).digest()).rstrip(b"=").decode()
        if challenge != self.challenge:
            raise AssertionError("PKCE verifier did not match the authorization request")
        stamp = int(auth.now().replace(tzinfo=timezone.utc).timestamp())
        claims = {"aud": "wrong-client" if self.bad_audience else CLIENT,
                  "iss": "https://evil.example" if self.bad_issuer else f"https://login.microsoftonline.com/{TENANT}/v2.0",
                  "iat": stamp, "exp": stamp + 300, "sub": "microsoft-pairwise-subject",
                  "tid": TENANT, "oid": OBJECT, "name": "Microsoft Person",
                  "nonce": "wrong-nonce" if self.bad_nonce else self.nonce}
        if not self.no_email:
            claims["email"] = "shared@example.com"
        token = jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "microsoft-test"})
        if self.bad_signature:
            header, payload, signature = token.split(".")
            signature = ("A" if signature[0] != "A" else "B") + signature[1:]
            token = ".".join([header, payload, signature])
        return httpx.Response(200, json={"access_token": "external-microsoft-token", "token_type": "Bearer", "expires_in": 300, "id_token": token})


class OAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "", "OWNER_EMAIL": "owner@gmail.com", "OWNER_PROVIDER": "google", "OWNER_SUBJECT": "",
            "GITHUB_CLIENT_ID": "github-public-client", "GITHUB_CLIENT_SECRET": "github-test-secret",
            "MICROSOFT_CLIENT_ID": CLIENT, "MICROSOFT_CLIENT_SECRET": "microsoft-test-secret",
            "MICROSOFT_TENANT_ID": "common", "ALLOWED_ORIGINS": "http://localhost:5173", "APP_ENV": "development",
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
        self.microsoft = MicrosoftServer(self.private)
        def ms_app():
            return msal.ConfidentialClientApplication(CLIENT, client_credential="microsoft-test-secret",
                authority="https://login.microsoftonline.com/common", instance_discovery=False,
                exclude_scopes=["offline_access"], http_client=self.microsoft)
        self.ms_patch = patch("app.oauth.microsoft_app", side_effect=ms_app)
        self.ms_patch.start()
        keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=self.private.public_key()))
        self.key_patch = patch("app.oauth.microsoft_keys", return_value=keys)
        self.key_patch.start()

    def tearDown(self):
        self.key_patch.stop()
        self.ms_patch.stop()
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.environment.stop()

    def start(self, provider):
        response = self.client.post(f"/auth/{provider}/start")
        self.assertEqual(response.status_code, 200, response.text)
        query = parse_qs(urlparse(response.json()["authorization_url"]).query)
        if provider == "microsoft":
            self.microsoft.nonce = query["nonce"][0]
            self.microsoft.challenge = query["code_challenge"][0]
        return response, query

    @staticmethod
    def github_transport(request):
        if request.url.host == "github.com" and request.url.path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            assert form["client_secret"] == ["github-test-secret"]
            assert form["code_verifier"]
            return httpx.Response(200, json={"access_token": "external-github-token", "token_type": "bearer"})
        assert request.headers["Authorization"] == "Bearer external-github-token"
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 42, "login": "githubperson", "name": "GitHub Person", "email": "untrusted-display-email@example.com"})
        if request.url.path == "/user/emails":
            return httpx.Response(200, json=[{"email": "shared@example.com", "primary": True, "verified": True}])
        raise AssertionError(str(request.url))

    def github_callback(self, query, transport=None, client=None):
        with patch("app.oauth.httpx.Client", return_value=httpx.Client(transport=httpx.MockTransport(transport or self.github_transport))):
            return (client or self.client).get("/auth/github/callback", params={"state": query["state"][0], "code": "provider-code"}, follow_redirects=False)

    def microsoft_callback(self, query):
        posted = self.client.post("/auth/microsoft/callback", data={"state": query["state"][0], "code": "microsoft-code"}, follow_redirects=False)
        self.assertEqual(posted.status_code, 303, posted.text)
        self.assertTrue(posted.headers["location"].startswith("/auth/microsoft/finish?ticket="))
        return self.client.get(posted.headers["location"], follow_redirects=False)

    def test_public_provider_configuration_does_not_leak_secrets_and_google_is_independent(self):
        response = self.client.get("/auth/config")
        config = response.json()
        self.assertEqual({p["id"]: p["enabled"] for p in config["providers"]}, {"google": False, "github": True, "microsoft": True})
        self.assertTrue(config["configured"])
        self.assertNotIn("test-secret", response.text)
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com", "OWNER_EMAIL": ""}):
            self.assertTrue(self.client.get("/auth/config").json()["providers"][0]["enabled"])

    def test_provider_authorization_codes_are_redacted_from_access_logs(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s", ("client", "GET", "/auth/github/callback?code=secret&state=nonce", 303), None)
        oauth.AuthAccessLogFilter().filter(record)
        self.assertEqual(record.args[2], "/auth/github/callback")
        self.assertNotIn("secret", record.getMessage())

    def test_start_requires_allowed_origin_credentials_and_known_provider(self):
        self.assertEqual(self.client.post("/auth/github/start", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/auth/unknown/start").status_code, 404)
        with patch.dict(os.environ, {"GITHUB_CLIENT_SECRET": ""}):
            self.assertEqual(self.client.post("/auth/github/start").status_code, 503)
        with patch.dict(os.environ, {"MICROSOFT_CLIENT_ID": "not-a-client-id"}):
            self.assertEqual(self.client.post("/auth/microsoft/start").status_code, 503)

    def test_github_code_exchange_pkce_identity_and_single_use_session(self):
        response, query = self.start("github")
        self.assertEqual(query["scope"], ["read:user user:email"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("github-test-secret", response.text)
        with self.Session() as db:
            flow = db.query(OAuthFlow).one()
            data = json.loads(flow.flow_data)
            computed = base64.urlsafe_b64encode(__import__("hashlib").sha256(data["code_verifier"].encode()).digest()).rstrip(b"=").decode()
            self.assertEqual(computed, query["code_challenge"][0])
            self.assertEqual(data["redirect_uri"], "http://localhost:5173/auth/github/callback")
        result = self.github_callback(query)
        self.assertEqual(result.headers["location"], "/")
        session = self.client.get("/auth/me").json()
        self.assertEqual(session["user"]["provider"], "github")
        self.assertEqual(session["user"]["provider_subject"], "42")
        self.assertEqual(session["user"]["email"], "shared@example.com")
        self.assertFalse(session["user"]["is_owner"])
        self.assertEqual(self.github_callback(query).headers["location"], "/?auth_error=invalid_state")
        with self.Session() as db:
            self.assertEqual(db.query(SignInEvent).count(), 1)
            self.assertEqual(db.query(OAuthFlow).count(), 0)

    def test_wrong_browser_expiry_and_cancellation_never_create_an_account(self):
        _, query = self.start("github")
        with TestClient(app) as other:
            self.assertEqual(self.github_callback(query, client=other).headers["location"], "/?auth_error=invalid_state")
        with self.Session() as db:
            db.query(OAuthFlow).update({OAuthFlow.expires_at: auth.now() - timedelta(seconds=1)})
            db.commit()
        self.assertEqual(self.github_callback(query).headers["location"], "/?auth_error=invalid_state")
        _, query = self.start("github")
        canceled = self.client.get("/auth/github/callback", params={"state": query["state"][0], "error": "access_denied"}, follow_redirects=False)
        self.assertEqual(canceled.headers["location"], "/?auth_error=access_denied")
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)

    def test_unverified_github_email_is_not_accepted(self):
        _, query = self.start("github")
        def unverified(request):
            if request.url.path == "/user/emails":
                return httpx.Response(200, json=[{"email": "owner@gmail.com", "verified": False, "primary": True}])
            return self.github_transport(request)
        self.assertEqual(self.github_callback(query, unverified).headers["location"], "/?auth_error=verification_failed")
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(SignInEvent).count(), 0)

    def test_microsoft_sdk_pkce_nonce_signature_and_account_profile(self):
        _, query = self.start("microsoft")
        self.assertEqual(query["response_mode"], ["form_post"])
        self.assertNotIn("offline_access", query["scope"][0])
        response = self.microsoft_callback(query)
        self.assertEqual(response.headers["location"], "/")
        profile = self.client.get("/auth/me").json()["user"]
        self.assertEqual(profile["provider"], "microsoft")
        self.assertEqual(profile["provider_subject"], TENANT + ":" + OBJECT)
        self.assertEqual(profile["email"], "shared@example.com")
        self.assertEqual(len(self.microsoft.posts), 1)

    def test_microsoft_rejects_wrong_nonce_signature_audience_and_issuer(self):
        for flag in ["bad_nonce", "bad_signature", "bad_audience", "bad_issuer"]:
            setattr(self.microsoft, flag, True)
            _, query = self.start("microsoft")
            response = self.microsoft_callback(query)
            self.assertEqual(response.headers["location"], "/?auth_error=verification_failed", flag)
            setattr(self.microsoft, flag, False)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(SignInEvent).count(), 0)

    def test_microsoft_form_post_uses_safe_cookie_bound_single_use_handoff(self):
        _, query = self.start("microsoft")
        with TestClient(app) as provider_client:
            response = provider_client.post("/auth/microsoft/callback", data={"state": query["state"][0], "code": "provider-code"}, follow_redirects=False)
            ticket_url = response.headers["location"]
            self.assertNotIn("provider-code", ticket_url)
            self.assertEqual(provider_client.get(ticket_url, follow_redirects=False).headers["location"], "/?auth_error=invalid_state")
        response = self.client.get(ticket_url, follow_redirects=False)
        self.assertEqual(response.headers["location"], "/")
        self.assertEqual(self.client.get(ticket_url, follow_redirects=False).headers["location"], "/?auth_error=invalid_state")
        self.assertEqual(self.client.get("/auth/me").status_code, 200)

    def test_same_email_from_two_providers_creates_separate_private_accounts(self):
        _, github = self.start("github")
        self.assertEqual(self.github_callback(github).headers["location"], "/")
        first = self.client.get("/auth/me").json()["user"]
        _, microsoft = self.start("microsoft")
        self.assertEqual(self.microsoft_callback(microsoft).headers["location"], "/")
        second = self.client.get("/auth/me").json()["user"]
        self.assertEqual(first["email"], second["email"])
        self.assertNotEqual(first["id"], second["id"])
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 2)

    def test_github_owner_needs_explicit_stable_provider_id(self):
        with patch.dict(os.environ, {"OWNER_PROVIDER": "github", "OWNER_SUBJECT": "42"}):
            _, query = self.start("github")
            self.assertEqual(self.github_callback(query).headers["location"], "/")
            session = self.client.get("/auth/me").json()
            self.assertTrue(session["user"]["is_owner"])
            self.assertEqual(self.client.get("/admin/users", headers={"Authorization": "Bearer " + session["access_token"]}).status_code, 200)
            with self.Session() as db:
                self.assertEqual(db.query(OwnerAccount).one().google_sub, "github:42")

    def test_microsoft_missing_email_does_not_invent_or_require_an_address(self):
        self.microsoft.no_email = True
        _, query = self.start("microsoft")
        self.assertEqual(self.microsoft_callback(query).headers["location"], "/")
        profile = self.client.get("/auth/me").json()["user"]
        self.assertEqual(profile["email"], "")
        self.assertFalse(profile["is_owner"])


if __name__ == "__main__":
    unittest.main()
