"""Security of the new surfaces: webhooks (private addresses, redirects, fire-time checks, timeouts, retries), API keys (scopes, rate limits, hashing),
the public API and MCP (isolation between workspaces), CSV uploads and exports (size, binary, formula neutralisation) and logs (no secrets, no personal data).
Each test here fails if the protection it names is removed."""
import ast
import io
import logging
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from test_integrations import Case, Receiver, SessionLocal, TestClient, app, core, models, settings  # noqa: E402  (sets the isolated environment)
from app import csv_safe
from app.routers import do_not_contact


def _addresses(*ips):
    """A stand-in for getaddrinfo that answers with these addresses."""
    def fake(host, port, *args, **kwargs):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]
    return fake


class Redirector(BaseHTTPRequestHandler):
    target = ""

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(302)
        self.send_header("Location", Redirector.target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class Sleeper(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        time.sleep(3)

    def log_message(self, *args):
        pass


def serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class WebhookSecurityTest(Case):
    def setUp(self):
        super().setUp()
        Receiver.got, Receiver.status = [], 200
        self.receiver = serve(Receiver)
        self.addCleanup(self.receiver.server_close)
        self.addCleanup(self.receiver.shutdown)
        self.url = f"http://127.0.0.1:{self.receiver.server_port}/hook"

    def hook(self, url=None, kind="webhook"):
        with SessionLocal() as db:
            hook = models.Webhook(user_id=self.owner_id, kind=kind, url=url or self.url, events=["reply_received"], secret="whsec_test")
            db.add(hook)
            db.commit()
            return hook.id

    def test_a_redirect_is_never_followed(self):
        Redirector.target = self.url  # a second, otherwise acceptable address
        redirecting = serve(Redirector)
        self.addCleanup(redirecting.server_close)
        self.addCleanup(redirecting.shutdown)
        with patch.object(settings, "allow_private_webhooks", True):
            hook = models.Webhook(kind="webhook", url=f"http://127.0.0.1:{redirecting.server_port}/x", secret="s")
            status, error = core._post(hook, "test", {})
        self.assertEqual(status, 302)
        self.assertIn("redirect", error)
        time.sleep(0.2)
        self.assertEqual(Receiver.got, [], "the redirect target was called")

    def test_the_address_is_checked_again_when_the_event_fires(self):
        hook_id = self.hook()  # saved while private addresses were allowed (a test setting)
        with patch.object(settings, "allow_private_webhooks", False):
            with SessionLocal() as db:
                status, error = core._post(db.get(models.Webhook, hook_id), "test", {})
        self.assertIsNone(status)
        self.assertTrue(error.startswith("Not sent"), error)
        time.sleep(0.2)
        self.assertEqual(Receiver.got, [])

    def test_every_dns_answer_must_be_public(self):
        with patch.object(settings, "allow_private_webhooks", False):
            for ips in (("10.0.0.5",), ("93.184.216.34", "192.168.1.9"), ("::1",), ("::ffff:127.0.0.1",), ("169.254.169.254",), ("100.64.0.1",), ("0.0.0.0",), ("224.0.0.1",)):
                with patch("socket.getaddrinfo", _addresses(*ips)):
                    self.assertIn("private network", core.check_webhook_url("https://hooks.example.org/x") or "", ips)
            with patch("socket.getaddrinfo", _addresses("93.184.216.34")):
                self.assertIsNone(core.check_webhook_url("https://hooks.example.org/x"))
            with patch("socket.getaddrinfo", side_effect=socket.gaierror):
                self.assertIn("could not be found", core.check_webhook_url("https://nowhere.example.org/x"))
            self.assertIn("username", core.check_webhook_url("https://user:pass@hooks.example.org/x"))

    def test_the_call_connects_to_the_address_that_was_checked(self):
        """A second DNS answer (rebinding) must not be used: the connection is pinned to the checked address."""
        seen = {}

        def capture(*handlers):
            seen["pinned"] = [h.ip for h in handlers if isinstance(h, core._PinnedHTTPSHandler)]
            raise RuntimeError("stop before connecting")
        with patch.object(settings, "allow_private_webhooks", False), patch("socket.getaddrinfo", _addresses("93.184.216.34")), patch("urllib.request.build_opener", capture):
            core._post(models.Webhook(kind="webhook", url="https://hooks.example.org/x", secret="s"), "test", {})
        self.assertEqual(seen["pinned"], ["93.184.216.34"])

    def test_a_slow_receiver_is_given_up_on(self):
        slow = serve(Sleeper)
        self.addCleanup(slow.server_close)
        self.addCleanup(slow.shutdown)
        started = time.time()
        with patch.object(settings, "allow_private_webhooks", True), patch.object(core, "TIMEOUT_SECONDS", 0.5):
            status, error = core._post(models.Webhook(kind="webhook", url=f"http://127.0.0.1:{slow.server_port}/x", secret="s"), "test", {})
        self.assertIsNone(status)
        self.assertIn("Could not reach", error)
        self.assertLess(time.time() - started, 2.5)

    def test_retries_stop_after_the_limit_and_only_for_failures_worth_retrying(self):
        hook_id = self.hook()
        with patch.object(settings, "allow_private_webhooks", True), patch.object(core, "RETRY_DELAYS", (0, 0, 0)):
            for status, expected in ((500, 3), (429, 3), (400, 1), (200, 1)):
                Receiver.got, Receiver.status = [], status
                core.deliver(hook_id, "reply_received", {"name": "Ada"})
                self.assertEqual(len(Receiver.got), expected, status)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.WebhookDelivery).filter_by(webhook_id=hook_id).count(), 3 + 3 + 1 + 1)  # every attempt is recorded
        self.assertEqual(core.MAX_ATTEMPTS, 3)

    def test_the_signature_depends_on_the_secret_and_the_exact_body(self):
        body = b'{"event":"x"}'
        self.assertEqual(core.sign("s1", body), core.sign("s1", body))
        self.assertNotEqual(core.sign("s1", body), core.sign("s2", body))
        self.assertNotEqual(core.sign("s1", body), core.sign("s1", body + b" "))


class ApiKeySecurityTest(Case):
    def make(self, **body):
        return self.client.post("/integrations/api-keys", json=body)

    def test_a_key_reads_by_default_and_writes_only_with_the_write_scope(self):
        read_key = self.make(name="read").json()
        self.assertEqual(read_key["scopes"], ["read"])
        client, h = self.public(read_key["key"])
        self.assertEqual(client.get("/public/v1/leads", headers=h).status_code, 200)
        refused = client.post("/public/v1/leads", headers=h, json={"firstName": "N", "lastName": "P", "linkedinUrl": "https://www.linkedin.com/in/np/"})
        self.assertEqual(refused.status_code, 403)
        write_key = self.make(name="write", scopes=["read", "write"]).json()
        client, h = self.public(write_key["key"])
        self.assertEqual(client.post("/public/v1/leads", headers=h, json={"firstName": "N", "lastName": "P", "linkedinUrl": "https://www.linkedin.com/in/np/"}).status_code, 201)
        self.assertEqual(self.make(scopes=["admin"]).status_code, 422)
        self.assertEqual(self.make(scopes=[]).status_code, 422)

    def test_a_key_made_before_scopes_existed_is_read_only(self):
        key = self.make().json()["key"]
        with SessionLocal() as db:
            row = db.query(models.ApiKey).one()
            row.scopes = None
            db.commit()
        client, h = self.public(key)
        self.assertEqual(client.get("/public/v1/leads", headers=h).status_code, 200)
        self.assertEqual(client.post("/public/v1/leads", headers=h, json={"firstName": "N", "lastName": "P", "linkedinUrl": "https://www.linkedin.com/in/np/"}).status_code, 403)

    def test_each_key_has_its_own_rate_limit(self):
        first, second = self.make(name="a").json()["key"], self.make(name="b").json()["key"]
        client, h1 = self.public(first)
        _, h2 = self.public(second)
        with patch.object(core, "RATE_PER_MINUTE", 3):
            for _ in range(3):
                self.assertEqual(client.get("/public/v1/leads", headers=h1).status_code, 200)
            limited = client.get("/public/v1/leads", headers=h1)
            self.assertEqual(limited.status_code, 429)
            self.assertGreaterEqual(int(limited.headers["Retry-After"]), 1)
            self.assertEqual(client.get("/public/v1/leads", headers=h2).status_code, 200, "another key shares the limit")
            self.assertEqual(client.post("/mcp", headers=h1, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 429, "MCP shares the key's limit")

    def test_the_window_slides(self):
        with patch.object(core, "RATE_PER_MINUTE", 2):
            self.assertEqual([core.retry_after("k-window", now=t) for t in (0, 1)], [0, 0])
            self.assertGreater(core.retry_after("k-window", now=2), 0)
            self.assertEqual(core.retry_after("k-window", now=61), 0)

    def test_the_key_is_stored_only_as_a_hash_and_a_revoked_key_stops_at_once(self):
        made = self.make().json()
        with SessionLocal() as db:
            row = db.query(models.ApiKey).one()
            stored = " ".join(str(getattr(row, c.name)) for c in row.__table__.columns)
        self.assertNotIn(made["key"], stored)
        self.assertNotIn(made["key"][12:], stored)
        client, h = self.public(made["key"])
        self.assertEqual(client.get("/public/v1/leads", headers=h).status_code, 200)
        self.assertEqual(self.client.delete(f"/integrations/api-keys/{made['id']}").status_code, 204)
        self.assertEqual(client.get("/public/v1/leads", headers=h).status_code, 401)
        self.assertEqual(client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 401)


class IsolationTest(Case):
    def test_a_key_sees_only_its_own_workspace_over_the_public_api_and_mcp(self):
        with SessionLocal() as db:
            db.add(models.Lead(user_id=self.other_id, first_name="Secret", last_name="Other", company="OtherCo", linkedin_url="https://www.linkedin.com/in/secret-other/"))
            db.add(models.Campaign(user_id=self.other_id, name="Other campaign", status="draft"))
            other_key = core.create_api_key(db, self.other_id, "other")[1]
            owner_key = core.create_api_key(db, self.owner_id, "owner")[1]
            db.commit()
        client, mine = self.public(owner_key)
        _, theirs = self.public(other_key)
        mine_names = {l["firstName"] for l in client.get("/public/v1/leads", headers=mine).json()["items"]}
        their_names = {l["firstName"] for l in client.get("/public/v1/leads", headers=theirs).json()["items"]}
        self.assertEqual(their_names, {"Secret"})
        self.assertNotIn("Secret", mine_names)
        self.assertEqual({c["name"] for c in client.get("/public/v1/campaigns", headers=theirs).json()}, {"Other campaign"})
        self.assertEqual(client.get("/public/v1/campaigns", headers=mine).json(), [])
        search = lambda h: client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_leads", "arguments": {}}}).json()["result"]["content"][0]["text"]
        self.assertIn("Secret", search(theirs))
        self.assertNotIn("Ada", search(theirs))
        self.assertIn("Ada", search(mine))
        self.assertNotIn("Secret", search(mine))

    def test_a_new_lead_lands_in_the_keys_workspace_and_keys_of_others_cannot_be_listed_or_revoked(self):
        with SessionLocal() as db:
            row, other_key = core.create_api_key(db, self.other_id, "other", ["read", "write"])
            db.commit()
            other_key_id = row.id
        client, h = self.public(other_key)
        created = client.post("/public/v1/leads", headers=h, json={"firstName": "Mine", "lastName": "Only", "linkedinUrl": "https://www.linkedin.com/in/mine-only/"})
        self.assertEqual(created.status_code, 201)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Lead).filter_by(first_name="Mine").one().user_id, self.other_id)
        self.assertEqual(self.client.get("/integrations/api-keys").json(), [])  # the owner sees none of the other workspace's keys
        self.assertEqual(self.client.delete(f"/integrations/api-keys/{other_key_id}").status_code, 404)


class CsvSafetyTest(Case):
    def test_every_formula_starter_is_neutralised(self):
        for bad in ("=1+1", "+1", "-1", "@SUM(A1)", "\t=x", "\r=x"):
            self.assertEqual(csv_safe.cell(bad), "'" + bad)
        self.assertEqual(csv_safe.cell("Ada"), "Ada")
        self.assertEqual(csv_safe.cell(5), 5)
        self.assertEqual(csv_safe.cell(None), "")

    def test_every_export_neutralises_text_from_the_database(self):
        with SessionLocal() as db:
            lead = db.query(models.Lead).filter_by(first_name="=Evil").one()
            lead.company, lead.phone, lead.job_title = "@cmd", "+65 1234", "-Boss"
            from app import dnc
            dnc.add_entries(db, self.owner_id, "person", [{"value": "https://www.linkedin.com/in/x/", "name": "=HYPERLINK(\"http://evil\")"}], "manual")
            db.commit()
        for tool, columns in (("smartlead", None), ("instantly", None)):
            text = self.client.get(f"/integrations/exports/{tool}?listId={self.list_id}").text
            for row in __import__("csv").reader(io.StringIO(text)):
                for value in row:
                    self.assertNotIn(value[:1], ("=", "@", "-", "\t", "\r"), (tool, value))
        dnc_text = self.client.get("/do-not-contact/export?kind=person").text
        self.assertIn("'=HYPERLINK", dnc_text)
        self.assertNotIn(",=HYPERLINK", dnc_text)

    def test_an_import_is_limited_in_rows_and_refuses_binary_content(self):
        with self.assertRaises(csv_safe.CsvTooLarge):
            csv_safe.parse("a\n1\n2\n3\n", max_rows=2)
        self.assertEqual(csv_safe.parse("a\n1\n2\n", max_rows=2)[1], [{"a": "1"}, {"a": "2"}])
        with patch.object(do_not_contact, "MAX_LINES", 2):
            r = self.client.post("/do-not-contact/import", json={"kind": "person", "csv": "linkedin_url\nhttps://www.linkedin.com/in/a/\nhttps://www.linkedin.com/in/b/\nhttps://www.linkedin.com/in/c/\n"})
        self.assertEqual(r.status_code, 422, r.text)
        for path, body in (("/integrations/import/leads", {"csv": "linkedin_url\n\x00\x01binary"}), ("/do-not-contact/import", {"kind": "person", "csv": "linkedin_url\n\x00"})):
            self.assertEqual(self.client.post(path, json=body).status_code, 422, path)
        too_big = self.client.post("/integrations/import/leads", json={"csv": "x" * 5_000_001})
        self.assertEqual(too_big.status_code, 422)


class LogHygieneTest(Case):
    SENSITIVE = ("password", "secret", "token", "cookie", "cookies", "api_key", "authorization", "hashed_password", "key_hash")

    def test_secrets_and_personal_data_never_reach_the_logs(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (root.removeHandler(handler), root.setLevel(previous)))
        made = self.client.post("/integrations/api-keys", json={"name": "logs", "scopes": ["read", "write"]}).json()
        client, h = self.public(made["key"])
        client.get("/public/v1/leads", headers=h)
        client.get("/public/v1/leads", headers={"Authorization": "Bearer syx_wrong-key-value"})
        client.post("/public/v1/leads", headers=h, json={"firstName": "Pia", "lastName": "Private", "email": "pia.private@example.org", "linkedinUrl": "https://www.linkedin.com/in/pia-private/"})
        hook = self.client.post("/integrations/webhooks", json={"url": "https://hooks.example.org/x", "events": ["reply_received"]})
        with patch.object(settings, "allow_private_webhooks", True), patch.object(core, "RETRY_DELAYS", (0, 0, 0)):
            self.client.post("/integrations/webhooks", json={"url": "http://127.0.0.1:9/x", "events": ["reply_received"]})
        self.client.post("/integrations/import/leads", json={"csv": "linkedin_url,email\nhttps://www.linkedin.com/in/zed-zero/,zed.zero@example.org\n"})
        text = stream.getvalue()
        for secret in (made["key"], made["key"][12:], "dg-SENTINEL-never-leak-9f3a7c", "pia.private@example.org", "zed.zero@example.org", hook.json().get("secret", "whsec_none")):
            self.assertNotIn(secret, text)

    def test_no_logging_call_in_the_app_passes_a_secret_variable(self):
        offenders = []
        for path in sorted(Path(__file__).resolve().parent.parent.joinpath("app").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("debug", "info", "warning", "error", "exception", "critical")
                        and isinstance(node.func.value, ast.Name) and node.func.value.id in ("log", "logger", "logging")):
                    for arg in node.args[1:] + [k.value for k in node.keywords] + [v for a in node.args[:1] if isinstance(a, ast.JoinedStr) for v in a.values if isinstance(v, ast.FormattedValue)]:
                        for name in ast.walk(arg):
                            ident = name.id if isinstance(name, ast.Name) else name.attr if isinstance(name, ast.Attribute) else ""
                            if ident.lower() in self.SENSITIVE:
                                offenders.append(f"{path.name}:{node.lineno} logs {ident}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
