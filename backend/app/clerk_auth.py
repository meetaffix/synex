"""Clerk authentication: verify a Clerk session token and map it to a Synex user.

Design and risks: docs/CLERK_MIGRATION.md. In short: the token is checked with PyJWT against Clerk's JWKS (RS256,
``exp``, ``nbf``, ``iss`` and ``azp``); the Clerk user id is linked to a Synex user by VERIFIED primary email, so
existing data stays attached and nobody can claim an account with an unverified address. Any failure is a plain 401
that says nothing about why.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .security import hash_password

log = logging.getLogger("synex.clerk")

CLOCK_SKEW_SECONDS = 5


class ClerkAuthError(Exception):
    """The token or the Clerk lookup could not be trusted. Never shown to the caller in detail."""


def enabled() -> bool:
    return settings.auth_provider.strip().lower() == "clerk"


def frontend_api_host() -> str:
    """The Clerk Frontend API host, which is encoded in the publishable key: pk_test_<base64(host$)>."""
    key = settings.clerk_publishable_key.strip()
    if not key.startswith(("pk_test_", "pk_live_")):
        raise ClerkAuthError("Clerk publishable key is missing or malformed")
    body = key.split("_", 2)[2]
    try:
        host = base64.b64decode(body + "=" * (-len(body) % 4)).decode().rstrip("$")
    except Exception as exc:  # noqa: BLE001
        raise ClerkAuthError("Clerk publishable key is malformed") from exc
    if not host or "." not in host:
        raise ClerkAuthError("Clerk publishable key is malformed")
    return host


def issuer() -> str:
    return (settings.clerk_issuer.strip() or f"https://{frontend_api_host()}").rstrip("/")


_jwks_lock = threading.Lock()
_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks_client() -> PyJWKClient:
    url = f"{issuer()}/.well-known/jwks.json"
    with _jwks_lock:
        client = _jwks_clients.get(url)
        if client is None:
            client = _jwks_clients[url] = PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=10)
        return client


def verify_session_token(token: str) -> dict:
    """The verified claims of a Clerk session token, or ClerkAuthError."""
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], issuer=issuer(), leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "sub", "iss"], "verify_aud": False},
        )
    except (jwt.PyJWTError, httpx.HTTPError, OSError) as exc:
        raise ClerkAuthError(type(exc).__name__) from None
    azp = claims.get("azp")
    if azp and not settings.origin_allowed(azp):
        raise ClerkAuthError("unauthorized party")
    if "nbf" in claims and claims["nbf"] > time.time() + CLOCK_SKEW_SECONDS:
        raise ClerkAuthError("not yet valid")
    return claims


def fetch_clerk_user(clerk_user_id: str) -> dict:
    """The Clerk user from the Backend API (needs CLERK_SECRET_KEY)."""
    if not settings.clerk_secret_key:
        raise ClerkAuthError("CLERK_SECRET_KEY is not configured")
    try:
        response = httpx.get(f"{settings.clerk_api_url.rstrip('/')}/v1/users/{clerk_user_id}",
                             headers={"Authorization": f"Bearer {settings.clerk_secret_key}"}, timeout=10)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ClerkAuthError(type(exc).__name__) from None


def verified_primary_email(clerk_user: dict) -> str | None:
    """The primary email address, only when Clerk has verified it."""
    primary_id = clerk_user.get("primary_email_address_id")
    for entry in clerk_user.get("email_addresses") or []:
        if entry.get("id") == primary_id:
            if (entry.get("verification") or {}).get("status") == "verified" and entry.get("email_address"):
                return str(entry["email_address"]).strip().lower()
            return None
    return None


def _display_name(clerk_user: dict, email: str) -> str:
    name = " ".join(p for p in (clerk_user.get("first_name"), clerk_user.get("last_name")) if p).strip()
    return name or email.split("@")[0]


def link_user(db: Session, clerk_user_id: str, clerk_user: dict) -> models.User:
    """The Synex user for this Clerk user: linked already, matched by verified email, or newly created."""
    email = verified_primary_email(clerk_user)
    if not email:
        raise ClerkAuthError("no verified primary email")
    user = db.query(models.User).filter(models.User.clerk_user_id == clerk_user_id).first()
    if user is None:
        user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
        if user is not None and user.clerk_user_id and user.clerk_user_id != clerk_user_id:
            raise ClerkAuthError("email already linked to another Clerk user")
    if user is None:
        user = models.User(email=email, full_name=_display_name(clerk_user, email),
                           hashed_password=hash_password(secrets.token_urlsafe(32)),  # never used: Clerk signs in
                           avatar_url=clerk_user.get("image_url") or None)
        db.add(user)
    user.clerk_user_id = clerk_user_id
    db.commit()
    db.refresh(user)
    return user


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def authenticate(request: Request, db: Session) -> models.User:
    """The Synex user behind a Clerk bearer token, or an HTTP 401 with no detail about why."""
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = bearer_token(request)
    if not token:
        raise unauthorized
    try:
        claims = verify_session_token(token)
        clerk_user_id = claims["sub"]
        user = db.query(models.User).filter(models.User.clerk_user_id == clerk_user_id).first()
        if user is None:  # first sign-in: look the person up once, then the link is stored
            user = link_user(db, clerk_user_id, fetch_clerk_user(clerk_user_id))
        return user
    except ClerkAuthError as exc:
        log.info("Clerk sign-in refused: %s", exc)
        raise unauthorized from None


# ---- webhook signature (Standard Webhooks, the scheme Svix and Clerk use) -----------------------------------

WEBHOOK_TOLERANCE_SECONDS = 300


def verify_webhook(body: bytes, headers) -> dict:
    """The event dict when the signature is valid and fresh, else ClerkAuthError."""
    secret = settings.clerk_webhook_secret.strip()
    if not secret:
        raise ClerkAuthError("webhook secret is not configured")
    msg_id, timestamp, signature = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature")
    if not (msg_id and timestamp and signature):
        raise ClerkAuthError("missing signature headers")
    try:
        if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
            raise ClerkAuthError("timestamp outside tolerance")
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    except (ValueError, IndexError) as exc:
        raise ClerkAuthError("bad webhook secret or timestamp") from exc
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    candidates = [part.split(",", 1)[1] for part in signature.split() if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise ClerkAuthError("signature mismatch")
    import json
    try:
        return json.loads(body)
    except ValueError as exc:
        raise ClerkAuthError("body is not JSON") from exc
