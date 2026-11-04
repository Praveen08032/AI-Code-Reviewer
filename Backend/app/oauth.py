"""Server-side GitHub and Microsoft sign-in with browser-bound, single-use flows."""
from base64 import urlsafe_b64encode
from datetime import timedelta
from functools import lru_cache
from hashlib import sha256
import json
import logging
import os
import secrets
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
import httpx
import jwt
from jwt.exceptions import PyJWKClientConnectionError
import msal
import requests
from sqlalchemy.orm import Session

from .auth import (clear_cookie, complete_login, digest, now, provider_configuration,
                   set_cookie, trusted_origin)
from .database import get_db
from .models import OAuthFlow

router = APIRouter(prefix="/auth", tags=["Authentication"])
MS_CONSUMER_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
_metadata_cache = {}


class AuthAccessLogFilter(logging.Filter):
    def filter(self, record):
        # Authorization codes and handoff tickets must not enter access logs.
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str) and path.startswith("/auth/"):
                record.args = (*record.args[:2], path.partition("?")[0], *record.args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(AuthAccessLogFilter())


def cookie_name(provider):
    return "codecheck_oauth_" + provider


def enabled(provider):
    return any(item["id"] == provider and item["enabled"] for item in provider_configuration())


def microsoft_app():
    tenant = os.getenv("MICROSOFT_TENANT_ID", "common").strip()
    if tenant not in {"common", "organizations", "consumers"}:
        tenant = str(UUID(tenant))
    return msal.ConfidentialClientApplication(
        str(UUID(os.environ["MICROSOFT_CLIENT_ID"].strip())),
        client_credential=os.environ["MICROSOFT_CLIENT_SECRET"].strip(),
        authority="https://login.microsoftonline.com/" + tenant,
        exclude_scopes=["offline_access"], timeout=5, instance_discovery=False,
        http_cache=_metadata_cache, enable_pii_log=False,
    )


@lru_cache(maxsize=32)
def microsoft_keys(tenant):
    # The tenant is UUID-validated before it is inserted into this fixed host URL.
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", timeout=5)


def microsoft_profile(result):
    encoded = result.get("id_token")
    if not isinstance(encoded, str):
        raise ValueError("Microsoft did not return an ID token")
    unverified = jwt.decode(encoded, options={"verify_signature": False})
    tenant = str(UUID(unverified["tid"]))
    setting = os.getenv("MICROSOFT_TENANT_ID", "common").strip()
    if setting == "consumers" and tenant != MS_CONSUMER_TENANT:
        raise ValueError("A personal Microsoft account is required")
    if setting == "organizations" and tenant == MS_CONSUMER_TENANT:
        raise ValueError("A work or school account is required")
    if setting not in {"common", "organizations", "consumers"} and tenant != str(UUID(setting)):
        raise ValueError("Unexpected Microsoft tenant")
    key = microsoft_keys(tenant).get_signing_key_from_jwt(encoded)
    claims = jwt.decode(encoded, key.key, algorithms=["RS256"],
                        audience=str(UUID(os.environ["MICROSOFT_CLIENT_ID"].strip())),
                        issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
                        options={"require": ["exp", "iat", "aud", "iss", "sub", "nonce", "tid", "oid"]})
    # MSAL has already validated the flow state, PKCE exchange and token nonce.
    subject = tenant + ":" + str(UUID(claims["oid"]))
    email = claims.get("email") or claims.get("preferred_username") or ""
    email = email if isinstance(email, str) and "@" in email else ""
    return {"subject": subject, "email": email, "name": claims.get("name"), "picture": None, "claims": claims}


def github_profile(flow, code):
    with httpx.Client(timeout=httpx.Timeout(8, connect=4), follow_redirects=False) as client:
        token_response = client.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, data={
            "client_id": os.environ["GITHUB_CLIENT_ID"].strip(),
            "client_secret": os.environ["GITHUB_CLIENT_SECRET"].strip(),
            "code": code, "redirect_uri": flow["redirect_uri"], "code_verifier": flow["code_verifier"],
        })
        token_response.raise_for_status()
        token_data = token_response.json()
        if not token_data.get("access_token") or token_data.get("error"):
            raise ValueError("GitHub did not authorize the code")
        headers = {"Authorization": "Bearer " + token_data["access_token"],
                   "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        user_response = client.get("https://api.github.com/user", headers=headers)
        user_response.raise_for_status()
        user = user_response.json()
        email_response = client.get("https://api.github.com/user/emails", headers=headers)
        email_response.raise_for_status()
        addresses = email_response.json()
    if type(user.get("id")) is not int or user["id"] <= 0 or not isinstance(addresses, list):
        raise ValueError("Invalid GitHub account")
    verified = [entry for entry in addresses if entry.get("verified") is True and isinstance(entry.get("email"), str)]
    if not verified:
        raise ValueError("A verified GitHub email is required")
    primary = next((entry for entry in verified if entry.get("primary") is True), verified[0])
    return {"subject": str(user["id"]), "email": primary["email"], "name": user.get("name") or user.get("login"),
            "picture": user.get("avatar_url"), "claims": {}}


def redirect_error(code, provider=None):
    response = RedirectResponse("/?" + urlencode({"auth_error": code}), status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    if provider:
        clear_cookie(response, cookie_name(provider))
    return response


@router.post("/{provider}/start", dependencies=[Depends(trusted_origin)])
def start_oauth(provider: str, request: Request, response: Response, db: Session = Depends(get_db)):
    if provider not in {"github", "microsoft"}:
        raise HTTPException(404, "Sign-in provider not found.")
    if not enabled(provider):
        raise HTTPException(503, f"{provider.title()} sign-in has not been enabled by the site owner.")
    origin = request.headers["origin"]
    if os.getenv("APP_ENV", "development") == "production" and not origin.startswith("https://"):
        raise HTTPException(403, "Sign-in requires an HTTPS website.")
    state, cookie = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    redirect_uri = origin + f"/auth/{provider}/callback"
    if provider == "github":
        verifier = secrets.token_urlsafe(48)
        challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        flow = {"redirect_uri": redirect_uri, "state": state, "code_verifier": verifier}
        authorization_url = "https://github.com/login/oauth/authorize?" + urlencode({
            "client_id": os.environ["GITHUB_CLIENT_ID"].strip(), "redirect_uri": redirect_uri,
            "scope": "read:user user:email", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "prompt": "select_account",
        })
    else:
        try:
            flow = microsoft_app().initiate_auth_code_flow(["email"], redirect_uri=redirect_uri, state=state,
                                                          prompt="select_account", response_mode="form_post")
            authorization_url = flow["auth_uri"]
        except (ValueError, KeyError, requests.RequestException) as error:
            raise HTTPException(503, "Microsoft sign-in could not be started. Check the provider setup and try again.") from error
    previous_cookie = request.cookies.get(cookie_name(provider))
    if previous_cookie:
        db.query(OAuthFlow).filter_by(cookie_hash=digest(previous_cookie), provider=provider).delete(synchronize_session=False)
    db.query(OAuthFlow).filter(OAuthFlow.expires_at <= now()).delete(synchronize_session=False)
    db.add(OAuthFlow(state_hash=digest(state), cookie_hash=digest(cookie), provider=provider,
                     flow_data=json.dumps(flow), expires_at=now() + timedelta(minutes=5)))
    db.commit()
    set_cookie(response, cookie_name(provider), cookie, 300)
    response.headers["Cache-Control"] = "no-store"
    return {"authorization_url": authorization_url}


def consume_flow(provider, record, request, db):
    cookie = request.cookies.get(cookie_name(provider), "")
    if not record or record.provider != provider or record.expires_at <= now() or not cookie or not secrets.compare_digest(record.cookie_hash, digest(cookie)):
        return None
    flow = json.loads(record.flow_data)
    callback = json.loads(record.callback_data) if record.callback_data else None
    if db.query(OAuthFlow).filter_by(state_hash=record.state_hash).delete(synchronize_session=False) != 1:
        db.rollback()
        return None
    db.commit()
    return flow, callback


def finish_oauth(provider, flow, callback, request, db):
    if callback.get("error"):
        return redirect_error("access_denied", provider)
    if not callback.get("code") or not enabled(provider):
        return redirect_error("provider_unavailable", provider)
    try:
        if provider == "github":
            profile = github_profile(flow, callback["code"])
        else:
            # SDK validates the nonce and exchanges the browser's authorization code using PKCE.
            result = microsoft_app().acquire_token_by_auth_code_flow(flow, callback, scopes=["email"])
            if result.get("error"):
                return redirect_error("verification_failed", provider)
            profile = microsoft_profile(result)
        response = RedirectResponse("/", status_code=303)
        complete_login(provider, profile["subject"], profile["email"], profile["name"], profile["picture"],
                       profile["claims"], request, response, db)
        clear_cookie(response, cookie_name(provider))
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    except (httpx.RequestError, requests.RequestException, PyJWKClientConnectionError):
        db.rollback()
        return redirect_error("provider_unavailable", provider)
    except (ValueError, RuntimeError, KeyError, TypeError, jwt.PyJWTError, httpx.HTTPStatusError, HTTPException):
        db.rollback()
        return redirect_error("verification_failed", provider)


@router.get("/github/callback")
def github_callback(request: Request, db: Session = Depends(get_db)):
    if len(request.url.query) > 16000:
        return redirect_error("invalid_state")
    state = request.query_params.get("state", "")
    record = db.get(OAuthFlow, digest(state)) if state else None
    consumed = consume_flow("github", record, request, db)
    if not consumed:
        return redirect_error("invalid_state")
    return finish_oauth("github", consumed[0], dict(request.query_params), request, db)


@router.post("/microsoft/callback")
async def microsoft_callback(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if len(body) > 16000 or not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        return redirect_error("invalid_state")
    try:
        values = parse_qs(body.decode("utf-8"), max_num_fields=20)
    except (ValueError, UnicodeDecodeError):
        return redirect_error("invalid_state")
    if any(len(value) != 1 for value in values.values()):
        return redirect_error("invalid_state")
    callback = {key: value[0] for key, value in values.items() if key in {"state", "code", "error"}}
    state = callback.get("state", "")
    record = db.get(OAuthFlow, digest(state)) if state else None
    if not record or record.provider != "microsoft" or record.expires_at <= now() or record.handoff_hash:
        return redirect_error("invalid_state")
    ticket = secrets.token_urlsafe(32)
    # A form_post arrives cross-site. Redirect to a safe GET to check our Lax,
    # HttpOnly browser cookie before exchanging any code or establishing a session.
    updated = db.query(OAuthFlow).filter_by(state_hash=record.state_hash, handoff_hash=None).update({
        OAuthFlow.callback_data: json.dumps(callback), OAuthFlow.handoff_hash: digest(ticket),
        OAuthFlow.expires_at: min(record.expires_at, now() + timedelta(minutes=1)),
    }, synchronize_session=False)
    db.commit()
    if updated != 1:
        return redirect_error("invalid_state")
    response = RedirectResponse("/auth/microsoft/finish?" + urlencode({"ticket": ticket}), status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/microsoft/finish")
def microsoft_finish(ticket: str, request: Request, db: Session = Depends(get_db)):
    record = db.query(OAuthFlow).filter_by(handoff_hash=digest(ticket)).first() if len(ticket) <= 256 else None
    consumed = consume_flow("microsoft", record, request, db)
    if not consumed or not consumed[1]:
        return redirect_error("invalid_state")
    return finish_oauth("microsoft", consumed[0], consumed[1], request, db)
