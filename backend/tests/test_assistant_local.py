"""The free local-model assistant: a model answers typed requests through the same tools, permissions and confirmation cards as the voice assistant."""
import atexit
import json
import os
import tempfile
import threading
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
from app import database, models, publishing_models  # noqa: F401
from app.assistant.models import AssistantAudit
from app.config import settings
from app.database import Base, SessionLocal
from app.deps import get_current_user
from app.main import app

atexit.register(database.engine.dispose)


class FakeOllama(BaseHTTPRequestHandler):
    script: list[dict] = []
    seen: list[dict] = []

    def do_POST(self):
        FakeOllama.seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        reply = json.dumps({"message": FakeOllama.script.pop(0)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def do_GET(self):
        reply = json.dumps({"models": [{"name": "llama3.2:latest"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


class LocalAssistantTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            db.add(models.LinkedInAccount(user_id=owner.id, name="Ada Lovelace", status="active", session_status="connected", daily_action_limit=10))
            db.commit()
            self.owner_id = owner.id
        FakeOllama.script, FakeOllama.seen = [], []
        self.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        for name, value in (("ollama_url", f"http://127.0.0.1:{self.server.server_port}"), ("ollama_model", "llama3.2")):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        app.dependency_overrides[get_current_user] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def say(self, text="hello"):
        return self.client.post("/assistant/local/chat", json={"text": text})

    def test_a_plain_answer_comes_back_and_the_model_is_given_the_tools_and_the_workspace(self):
        FakeOllama.script = [{"role": "assistant", "content": "You have one sender account."}]
        r = self.say("How many accounts do I have?").json()
        self.assertEqual((r["reply"], r["cards"]), ("You have one sender account.", []))
        sent = FakeOllama.seen[0]
        self.assertEqual(sent["model"], "llama3.2")
        self.assertTrue(any(t["function"]["name"] == "list_sender_accounts" for t in sent["tools"]))
        self.assertIn("Synex", sent["messages"][0]["content"])
        self.assertEqual(sent["messages"][-1], {"role": "user", "content": "How many accounts do I have?"})

    def test_a_read_tool_call_runs_through_the_registry_and_its_result_goes_back_to_the_model(self):
        FakeOllama.script = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "list_sender_accounts", "arguments": {}}}]},
                             {"role": "assistant", "content": "Ada Lovelace is connected."}]
        r = self.say("List my accounts").json()
        self.assertEqual(r["reply"], "Ada Lovelace is connected.")
        tool_message = FakeOllama.seen[1]["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertIn("Ada Lovelace", tool_message["content"])
        with SessionLocal() as db:
            self.assertTrue(db.query(AssistantAudit).filter_by(tool="list_sender_accounts", status="ok").count())

    def test_a_write_tool_only_makes_a_confirmation_card_and_changes_nothing(self):
        FakeOllama.script = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "create_lead_list", "arguments": {"name": "Fintech CTOs", "leads": [{"first_name": "Asha", "last_name": "Rao", "company": "PayCo"}]}}}]},
                             {"role": "assistant", "content": "I prepared it. Please confirm."}]
        r = self.say("Make a list called Fintech CTOs").json()
        self.assertEqual(r["cards"][0]["type"], "proposal")
        self.assertEqual(r["cards"][0]["proposal"]["status"], "pending")
        with SessionLocal() as db:
            self.assertEqual(db.query(models.LeadList).count(), 0)  # nothing applied until the person clicks Confirm

    def test_an_unknown_tool_or_bad_arguments_are_explained_to_the_model_not_run(self):
        FakeOllama.script = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "send_everything", "arguments": {}}}]},
                             {"role": "assistant", "content": "I cannot do that."}]
        self.assertEqual(self.say("Send everything").json()["reply"], "I cannot do that.")
        self.assertIn("not available", FakeOllama.seen[1]["messages"][-1]["content"])

    def test_a_model_that_keeps_calling_tools_stops_after_a_few_rounds(self):
        call = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "list_sender_accounts", "arguments": {}}}]}
        FakeOllama.script = [call, call, call, call, call]
        self.assertIn("smaller pieces", self.say("Loop").json()["reply"])

    def test_an_unreachable_model_says_how_to_fix_it_and_the_status_reports_it(self):
        with patch.object(settings, "ollama_url", "http://127.0.0.1:9"):
            r = self.say()
            self.assertEqual(r.status_code, 503)
            self.assertIn("Start Ollama", r.json()["detail"])
            self.assertFalse(self.client.get("/assistant/local/status").json()["reachable"])
        status = self.client.get("/assistant/local/status").json()
        self.assertEqual((status["reachable"], status["installed"]), (True, True))

    def test_the_assistant_switched_off_for_the_workspace_refuses(self):
        with SessionLocal() as db:
            from app.assistant.service import get_settings_row
            get_settings_row(db, self.owner_id).enabled = False
            db.commit()
        r = self.say()
        self.assertEqual(r.status_code, 403)


class NewToolsTest(LocalAssistantTest):
    def run_tool(self, name, args):
        from app.assistant import registry
        with SessionLocal() as db:
            actor = db.get(models.User, self.owner_id)
            return registry.run_tool(db, actor, name, args)

    def test_inbox_search_and_funnel_are_read_tools(self):
        out = self.run_tool("search_conversations", {"query": "nobody"})
        self.assertEqual((out.result["ok"], out.result["total"]), (True, 0))
        funnel = self.run_tool("get_funnel", {})
        self.assertEqual([s["count"] for s in funnel.result["stages"]], [0, 0, 0, 0, 0])
        self.assertFalse(self.run_tool("get_funnel", {"campaign_id": "nope"}).result["ok"])

    def test_adding_to_do_not_contact_is_a_proposal_until_confirmed_and_bad_values_are_refused(self):
        from app.assistant import registry
        out = self.run_tool("add_do_not_contact", {"kind": "company", "values": ["Acme Inc"]})
        self.assertEqual(out.result["status"], "awaiting_confirmation")
        with SessionLocal() as db:
            self.assertEqual(db.query(models.DoNotContact).count(), 0)
            actor = db.get(models.User, self.owner_id)
            registry.confirm_proposal(db, actor, out.result["proposalId"])
            self.assertEqual(db.query(models.DoNotContact).filter_by(kind="company").count(), 1)
        bad = self.run_tool("add_do_not_contact", {"kind": "person", "values": ["not a link"]})
        self.assertFalse(bad.result["ok"])


if __name__ == "__main__":
    unittest.main()
