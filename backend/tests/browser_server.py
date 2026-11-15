"""Local browser-test fixture. Never deploy this module."""
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(__file__).with_name("browser-test.db")).replace("\\", "/")
os.environ["SECRET_KEY"] = "browser-test-secret-0123456789-abcdef"
os.environ["ENCRYPTION_KEY"] = "browser-test-encryption-0123456789-abcdef"
os.environ["DEEPGRAM_API_KEY"] = "browser-test-fake-deepgram-key"  # never the real key from .env: no real Deepgram calls in tests
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5174"
os.environ["FRONTEND_URL"] = "http://127.0.0.1:5174"
os.environ["LINKEDIN_CLIENT_ID"] = "mock-browser-client"
os.environ["LINKEDIN_CLIENT_SECRET"] = "mock-browser-secret"
os.environ["LINKEDIN_REDIRECT_URI"] = "http://127.0.0.1:8011/linkedin/callback"
from app.main import app
from app.database import Base, engine, SessionLocal
from app.migrations import migrate
from app.models import User
from app.publishing_models import Connection
from app.security import hash_password, encrypt_secret
from app.publishing_worker import tick

# The test browser intercepts authorization locally. No provider traffic.
from app import linkedin
def mock_exchange(code, nonce):
    if code not in ("browser-login", "browser-connect"):
        raise ValueError("Not a fixture code")
    return ({"access_token":"fake-browser-token", "expires_in":3600, "scope":"openid profile email" + (" w_member_social" if code == "browser-connect" else "")}, {"sub":"test-browser-oidc", "name":"Browser OIDC Fixture", "email":"oidc@example.com", "email_verified":True})
linkedin.exchange = mock_exchange

# Keep all provider hops inside loopback, including HTTP redirects that browser
# interception may bypass. The real authorization builder still produces the parameters.
from urllib.parse import urlparse, urlencode
from html import escape
from fastapi.responses import HTMLResponse
real_begin = linkedin.begin

def local_begin(*args, **kwargs):
    official = urlparse(real_begin(*args, **kwargs))
    assert official.hostname == "www.linkedin.com" and official.path == "/oauth/v2/authorization"
    return "http://127.0.0.1:8011/test/provider?" + official.query
linkedin.begin = local_begin

@app.get("/test/provider", response_class=HTMLResponse)
def test_provider(state: str, scope: str, redirect_uri: str):
    assert redirect_uri == "http://127.0.0.1:8011/linkedin/callback"
    callback = redirect_uri + "?" + urlencode({"state":state,"code":"browser-connect" if "w_member_social" in scope.split() else "browser-login"})
    return "<h1>Test consent</h1><p id='scopes'>" + escape(scope) + "</p><a href='" + escape(callback) + "'>Approve test grant</a>"

Base.metadata.drop_all(engine)
migrate()
with SessionLocal() as db:
    user = User(email="browser@example.com", full_name="Alex Morgan", company="Editorial workspace", hashed_password=hash_password("Browser-Test-Password!"))
    db.add(user); db.flush()
    db.add(Connection(user_id=user.id, subject="TEST-NOT-A-REAL-LINKEDIN-MEMBER", name="Alex Morgan · Test account", access_token=encrypt_secret("FAKE-TEST-TOKEN"), expires_at=datetime.now(timezone.utc)+timedelta(days=1), scopes=["openid","profile","w_member_social"]))
    db.commit()

@app.post("/test/execute")
def execute():
    provider = Mock()
    provider.post.return_value = Mock(status_code=201, headers={"x-restli-id":"urn:li:share:test-only"})
    with SessionLocal() as db:
        tick(db, provider)
    return {"mockedRequests": provider.post.call_count}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011)
