"""Integrations: notifications, API keys with the public API and MCP, signed webhooks and Slack, usage, support, exports, importer and HubSpot."""
import atexit
import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, integrations_core as core, models, publishing_models  # noqa: F401
from app.config import settings
from app.database import Base, SessionLocal
from app.deps import get_admin_user, get_current_user, get_data_user, get_manager_user
from app.main import app
from app.routers import integrations

atexit.register(database.engine.dispose)


class Receiver(BaseHTTPRequestHandler):
    got: list[dict] = []
    status = 200

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Receiver.got.append({"body": body, "sig": self.headers.get("X-Synex-Signature"), "event": self.headers.get("X-Synex-Event")})
        self.send_response(Receiver.status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class Case(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([owner, other])
            db.flush()
            lead_list = models.LeadList(user_id=owner.id, name="Prospects")
            db.add(lead_list)
            db.flush()
            for first, email in (("Ada", "ada@example.com"), ("Bo", None), ("=Evil", "evil@example.com")):
                lead = models.Lead(user_id=owner.id, first_name=first, last_name="L", company="Acme", email=email, linkedin_url=f"https://www.linkedin.com/in/{first.lower().strip('=')}/")
                db.add(lead)
                lead_list.leads.append(lead)
            db.commit()
            self.owner_id, self.other_id, self.list_id = owner.id, other.id, lead_list.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_admin_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def public(self, key):
        # the public API and MCP use the key, not the signed-in session
        client = TestClient(app)
        app.dependency_overrides.pop(get_current_user, None)
        return client, {"Authorization": f"Bearer {key}"}


class NotificationTest(Case):
    def test_settings_are_validated_saved_and_a_test_email_lands_in_the_outbox(self):
        self.assertEqual(self.client.put("/integrations/notifications", json={"emails": ["not an email"]}).status_code, 422)
        saved = self.client.put("/integrations/notifications", json={"emails": ["Boss@Example.com"], "reply_received": True}).json()
        self.assertEqual((saved["emails"], saved["reply_received"], saved["account_disconnected"]), (["boss@example.com"], True, True))
        out = self.client.post("/integrations/notifications/test").json()
        self.assertEqual(out["results"], ["stored"])  # no SMTP host in tests
        self.assertEqual(self.client.get("/integrations/outbox").json()[0]["to"], "boss@example.com")

    def test_an_event_emails_only_when_that_notification_is_on_and_a_test_needs_an_address(self):
        self.assertEqual(self.client.post("/integrations/notifications/test").status_code, 409)
        self.client.put("/integrations/notifications", json={"emails": ["boss@example.com"], "reply_received": False, "account_disconnected": True})
        with SessionLocal() as db:
            core.emit(db, self.owner_id, "reply_received", {"name": "Ada"})
            core.emit(db, self.owner_id, "account_disconnected", {"name": "Sender", "reason": "Signed out"})
            db.commit()
            subjects = [m.subject for m in db.query(models.OutboxEmail).all()]
        self.assertEqual(subjects, ["Synex: A sender account was disconnected"])


class KeyAndApiTest(Case):
    def test_a_key_is_shown_once_stored_hashed_works_for_the_public_api_and_stops_when_revoked(self):
        made = self.client.post("/integrations/api-keys", json={"name": "CRM"}).json()
        key = made["key"]
        self.assertTrue(key.startswith("syx_"))
        listed = self.client.get("/integrations/api-keys").json()[0]
        self.assertNotIn("key", listed)
        self.assertEqual(listed["prefix"], key[:12])
        with SessionLocal() as db:
            self.assertNotIn(key, str(db.query(models.ApiKey).one().key_hash))
        client, headers = self.public(key)
        self.assertEqual(len(client.get("/public/v1/leads", headers=headers).json()["items"]), 3)
        self.assertEqual(client.get("/public/v1/campaigns", headers=headers).status_code, 200)
        created = client.post("/public/v1/leads", headers=headers, json={"firstName": "New", "lastName": "Person", "linkedinUrl": "https://www.linkedin.com/in/new/"})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(client.get("/public/v1/leads", headers={"Authorization": "Bearer nope"}).status_code, 401)
        self.assertEqual(client.get("/public/v1/leads").status_code, 401)
        self.assertEqual(self.client.get("/integrations/api-keys").json()[0]["lastUsedAt"] is not None, True)
        self.assertEqual(self.client.delete(f"/integrations/api-keys/{made['id']}").status_code, 204)
        self.assertEqual(client.get("/public/v1/leads", headers=headers).status_code, 401)

    def test_mcp_lists_only_read_and_draft_tools_and_runs_one(self):
        key = self.client.post("/integrations/api-keys", json={}).json()["key"]
        client, h = self.public(key)
        init = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).json()
        self.assertEqual(init["result"]["serverInfo"]["name"], "synex")
        tools = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertIn("get_funnel", names)
        self.assertNotIn("add_do_not_contact", names)  # a tool that changes data needs a click inside Synex
        self.assertTrue(all("inputSchema" in t for t in tools))
        call = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_funnel", "arguments": {}}}).json()["result"]
        self.assertFalse(call["isError"])
        self.assertIn("stages", call["content"][0]["text"])
        blocked = client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "add_do_not_contact", "arguments": {"kind": "company", "values": ["x"]}}}).json()["result"]
        self.assertTrue(blocked["isError"])
        self.assertEqual(client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 5, "method": "nope"}).json()["error"]["code"], -32601)
        self.assertEqual(client.post("/mcp", headers=h, json={"hello": 1}).json()["error"]["code"], -32600)
        self.assertEqual(client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 401)


class WebhookTest(Case):
    def setUp(self):
        super().setUp()
        Receiver.got, Receiver.status = [], 200
        self.server = HTTPServer(("127.0.0.1", 0), Receiver)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        patcher = patch.object(settings, "allow_private_webhooks", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def wait(self, count, timeout=5):
        end = time.time() + timeout
        while len(Receiver.got) < count and time.time() < end:
            time.sleep(0.05)

    def test_an_event_is_sent_signed_and_recorded_and_a_disabled_hook_is_silent(self):
        hook = self.client.post("/integrations/webhooks", json={"url": self.url, "events": ["reply_received"]}).json()
        self.assertTrue(hook["secret"].startswith("whsec_"))
        with SessionLocal() as db:
            self.assertEqual(core.emit(db, self.owner_id, "reply_received", {"name": "Ada"}), 1)
            self.assertEqual(core.emit(db, self.owner_id, "campaign_launched", {"name": "C"}), 0)  # not subscribed
        self.wait(1)
        got = Receiver.got[0]
        self.assertEqual(got["event"], "reply_received")
        self.assertEqual(got["sig"], "sha256=" + hmac.new(hook["secret"].encode(), got["body"], hashlib.sha256).hexdigest())
        self.assertEqual(json.loads(got["body"])["data"]["name"], "Ada")
        time.sleep(0.3)
        self.assertTrue(self.client.get(f"/integrations/webhooks/{hook['id']}/deliveries").json()[0]["ok"])
        self.client.patch(f"/integrations/webhooks/{hook['id']}", json={"enabled": False})
        with SessionLocal() as db:
            core.emit(db, self.owner_id, "reply_received", {"name": "Bo"})
        time.sleep(0.3)
        self.assertEqual(len(Receiver.got), 1)

    def test_the_test_button_reports_the_receivers_answer_and_a_failing_receiver_is_logged_with_its_status(self):
        hook = self.client.post("/integrations/webhooks", json={"url": self.url, "events": ["reply_received"]}).json()
        self.assertTrue(self.client.post(f"/integrations/webhooks/{hook['id']}/test").json()["ok"])
        Receiver.status = 500
        bad = self.client.post(f"/integrations/webhooks/{hook['id']}/test").json()
        self.assertEqual((bad["ok"], bad["status"]), (False, 500))
        self.assertIn("500", bad["error"])

    def test_addresses_events_and_slack_are_checked(self):
        with patch.object(settings, "allow_private_webhooks", False):
            self.assertEqual(self.client.post("/integrations/webhooks", json={"url": "http://example.com/x", "events": ["reply_received"]}).status_code, 422)
            private = self.client.post("/integrations/webhooks", json={"url": "https://127.0.0.1/x", "events": ["reply_received"]})
            self.assertEqual(private.status_code, 422)
            self.assertIn("private network", private.json()["detail"])
            self.assertEqual(self.client.post("/integrations/webhooks", json={"kind": "slack", "url": "https://example.com/x", "events": ["reply_received"]}).status_code, 422)
        self.assertEqual(self.client.post("/integrations/webhooks", json={"url": self.url, "events": ["nope"]}).status_code, 422)
        self.assertEqual(self.client.post("/integrations/webhooks", json={"url": self.url, "events": []}).status_code, 422)

    def test_another_workspaces_webhook_cannot_be_touched(self):
        with SessionLocal() as db:
            theirs = models.Webhook(user_id=self.other_id, url="https://example.com/h", events=["reply_received"], secret="s")
            db.add(theirs)
            db.commit()
            hid = theirs.id
        self.assertEqual(self.client.delete(f"/integrations/webhooks/{hid}").status_code, 404)
        self.assertEqual(self.client.post(f"/integrations/webhooks/{hid}/test").status_code, 404)


class OtherTest(Case):
    def test_usage_support_and_events(self):
        usage = self.client.get("/integrations/usage").json()
        self.assertEqual((usage["leads"], usage["aiDraftsThisMonth"], usage["actionsLast24h"]), (3, 0, {}))
        self.assertIn("not a balance", usage["note"])
        self.assertEqual(self.client.post("/integrations/support", json={"subject": "Hi", "body": "short"}).status_code, 422)
        self.assertEqual(self.client.post("/integrations/support", json={"subject": "Help please", "body": "My account is stuck at login."}).status_code, 201)
        self.assertEqual(self.client.get("/integrations/support").json()[0]["subject"], "Help please")
        self.assertIn("reply_received", {e["id"] for e in self.client.get("/integrations/events").json()})

    def test_email_tool_exports_include_only_people_with_an_email_in_the_tools_columns_and_neutralise_formulas(self):
        r = self.client.get("/integrations/exports/smartlead", params={"listId": self.list_id})
        rows = list(csv.reader(io.StringIO(r.text)))
        self.assertEqual(rows[0][:3], ["email", "first_name", "last_name"])
        self.assertEqual(len(rows) - 1, 2)
        self.assertEqual(r.headers["x-skipped-no-email"], "1")
        self.assertIn("'=Evil", r.text)
        instantly = self.client.get("/integrations/exports/instantly", params={"listId": self.list_id}).text.splitlines()[0]
        self.assertTrue(instantly.startswith("Email,First Name"))
        self.assertEqual(self.client.get("/integrations/exports/smartlead", params={"listId": "nope"}).status_code, 404)

    def test_the_importer_matches_columns_by_name_makes_lists_from_a_list_column_and_never_duplicates(self):
        text = ("Profile URL,First Name,Last Name,Company,Campaign\nhttps://www.linkedin.com/in/new-one/,New,One,Initech,Spring\n"
                "https://www.linkedin.com/in/ada/,Ada,L,Acme,Spring\nhttps://www.linkedin.com/in/new-two/,New,Two,Hooli,Autumn\nnot a link,No,Body,X,Spring\n")
        r = self.client.post("/integrations/import/leads", json={"csv": text, "listColumn": "Campaign"}).json()
        self.assertEqual((r["created"], r["alreadyKnown"], r["withoutProfileLink"], r["lists"]), (2, 1, 1, ["Autumn", "Spring"]))
        again = self.client.post("/integrations/import/leads", json={"csv": text, "listColumn": "Campaign"}).json()
        self.assertEqual((again["created"], again["alreadyKnown"]), (0, 3))
        bad = self.client.post("/integrations/import/leads", json={"csv": "Name,Email\nAda,a@example.com\n"})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("LinkedIn profile address", bad.json()["detail"])

    def test_hubspot_needs_a_token_imports_contacts_with_a_linkedin_address_and_keeps_the_token_encrypted(self):
        self.assertEqual(self.client.post("/integrations/hubspot/import").status_code, 409)
        self.client.put("/integrations/hubspot", json={"token": "pat-na1-0123456789"})
        with SessionLocal() as db:
            self.assertNotIn("pat-na1", json.dumps(db.get(models.WorkspaceSetting, (self.owner_id, "hubspot")).value))
        pages = [{"results": [{"properties": {"firstname": "Hub", "lastname": "Spot", "hs_linkedin_url": "https://www.linkedin.com/in/hubspot-one/", "company": "HS"}},
                              {"properties": {"firstname": "No", "lastname": "Link"}}], "paging": {"next": {"after": "2"}}},
                 {"results": [{"properties": {"firstname": "Two", "hs_linkedin_url": "https://www.linkedin.com/in/hubspot-two/"}}]}]
        seen_tokens = []
        with patch.object(integrations, "hubspot_fetch", side_effect=lambda token, after: (seen_tokens.append(token), pages.pop(0))[1]):
            r = self.client.post("/integrations/hubspot/import").json()
        self.assertEqual((r["seen"], r["created"], r["withoutLinkedinAddress"]), (3, 2, 1))
        self.assertEqual(seen_tokens[0], "pat-na1-0123456789")
        self.assertTrue(self.client.get("/integrations/hubspot").json()["connected"])
        self.assertEqual(self.client.delete("/integrations/hubspot").status_code, 204)
        self.assertFalse(self.client.get("/integrations/hubspot").json()["connected"])


if __name__ == "__main__":
    unittest.main()
