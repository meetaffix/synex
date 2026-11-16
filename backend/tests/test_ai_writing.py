"""AI writing settings: validated per message, turned into a prompt with the campaign's context, written by the chosen provider (here a local
Ollama stand-in served from this process), previewed with its cost, and never used for a step that is not AI assisted."""
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
os.environ.pop("DEEPGRAM_API_KEY", None)
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import ai_prompt, database, drafts, models, providers, publishing_models  # noqa: F401
from app.assistant.config import assistant_config
from app.config import settings
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class FakeOllama(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.seen.append(body)
        reply = json.dumps({"response": "Hi Ada, loved your work at Acme. Open to a chat?"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


class PromptTest(unittest.TestCase):
    def test_settings_are_validated_with_a_reason(self):
        for bad, word in (({"mode": "wild"}, "direct or AI assisted"), ({"tone": "shouty"}, "Tone must"), ({"strategy": "pushy"}, "Strategy must"),
                          ({"instructions": "x" * 2001}, "2000 characters"), ({"profile_data": {"recent_posts": True}}, "profile reader"),
                          ({"profile_data": {"nonsense": True}}, "Profile data options")):
            with self.assertRaises(ValueError, msg=bad) as caught:
                ai_prompt.check_step_ai(bad)
            self.assertIn(word, str(caught.exception))
        ok = ai_prompt.check_step_ai({"mode": "ai", "tone": "witty", "strategy": "curiosity_hook", "instructions": " be brief "})
        self.assertEqual((ok["mode"], ok["tone"], ok["instructions"], ok["profile_data"]["role_company"]), ("ai", "witty", "be brief", True))

    def test_the_prompt_carries_tone_strategy_instructions_context_and_guardrails_but_only_known_facts(self):
        system, prompt = ai_prompt.build_prompt("message", {"first_name": "Ada", "company": "Acme", "job_title": "", "headline": ""},
                                                {"tone": "casual", "strategy": "value_offer", "instructions": "Mention the webinar"},
                                                {"goals": "Book demos for our audit", "do_not_mention": ["pricing", "competitors"]})
        self.assertIn("relaxed, casual tone", prompt)
        self.assertIn("concrete way the sender can help", prompt)
        self.assertIn("Mention the webinar", prompt)
        self.assertIn("Book demos for our audit", prompt)
        self.assertIn("first name: Ada", prompt)
        self.assertNotIn("job title", prompt)  # an empty field is never written as a fact
        self.assertIn("Never mention: pricing; competitors.", system)
        self.assertIn("never invent facts", system)

    def test_role_and_company_can_be_switched_off(self):
        _, prompt = ai_prompt.build_prompt("message", {"first_name": "Ada", "company": "Acme"}, {"profile_data": {"role_company": False}}, None)
        self.assertIn("first name: Ada", prompt)
        self.assertNotIn("Acme", prompt)

    def test_who_gets_an_ai_draft(self):
        class Step:
            def __init__(self, cfg):
                self.ai_config = cfg

        class Camp:
            def __init__(self, flag):
                self.ai_personalization = flag
        self.assertTrue(ai_prompt.wants_ai(Step({"mode": "ai"}), Camp(False)))
        self.assertFalse(ai_prompt.wants_ai(Step({"mode": "direct"}), Camp(True)))  # an explicit direct setting wins
        self.assertTrue(ai_prompt.wants_ai(Step(None), Camp(True)))  # older campaigns follow the campaign switch
        self.assertFalse(ai_prompt.wants_ai(Step(None), Camp(False)))


class OllamaTest(unittest.TestCase):
    def setUp(self):
        FakeOllama.seen = []
        self.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        key = patch.object(assistant_config, "deepgram_api_key", "")
        key.start()
        self.addCleanup(key.stop)
        for name, value in (("ai_provider", "ollama"), ("ollama_url", f"http://127.0.0.1:{self.server.server_port}"), ("ollama_model", "test-model")):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_local_model_writes_the_draft_and_receives_the_built_prompt(self):
        text, source = drafts._make_text("message", {"first_name": "Ada", "last_name": "L", "company": "Acme", "job_title": "", "headline": ""},
                                         {"config": {"tone": "witty"}, "context": {"goals": "Book demos"}})
        self.assertEqual(source, "ai")
        self.assertIn("Hi Ada", text)
        sent = FakeOllama.seen[0]
        self.assertEqual(sent["model"], "test-model")
        self.assertFalse(sent["stream"])
        self.assertIn("Book demos", sent["prompt"])

    def test_an_unreachable_model_falls_back_to_the_template_and_says_so(self):
        with patch.object(settings, "ollama_url", "http://127.0.0.1:9"):
            text, source = drafts._make_text("message", {"first_name": "Ada", "last_name": "L", "company": "Acme", "job_title": "", "headline": ""}, {"config": None, "context": {}})
        self.assertEqual(source, "template")
        self.assertTrue(text)

    def test_the_provider_choice_follows_the_setting(self):
        self.assertEqual(providers.provider_name(), "ollama")
        with patch.object(settings, "ai_provider", "template"):
            self.assertEqual(providers.provider_name(), "template")
        with patch.object(settings, "ai_provider", "auto"):
            self.assertEqual(providers.provider_name(), "template")  # no Deepgram key in this test


class ApiTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=10)
            lead_list = models.LeadList(user_id=owner.id, name="L")
            db.add_all([account, lead_list])
            db.flush()
            for name in ("Ada", "Bo"):
                lead = models.Lead(user_id=owner.id, first_name=name, company="Acme", linkedin_url=f"https://www.linkedin.com/in/{name.lower()}/")
                db.add(lead)
                lead_list.leads.append(lead)
            db.commit()
            self.owner_id, self.account_id, self.list_id = owner.id, account.id, lead_list.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        patcher = patch.object(settings, "ai_provider", "template")
        patcher.start()
        self.addCleanup(patcher.stop)
        key = patch.object(assistant_config, "deepgram_api_key", "")
        key.start()
        self.addCleanup(key.stop)

    def campaign(self, steps):
        r = self.client.post("/campaigns", json={"action": "create", "name": "C", "accountId": self.account_id, "leadListId": self.list_id, "steps": steps,
                                                  "aiContext": {"goals": "Book demos"}})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_ai_settings_round_trip_and_a_bad_setting_is_refused(self):
        made = self.campaign([{"type": "connection_request", "order": 0, "message": "hi"}, {"type": "message", "order": 1, "message": "yo", "aiConfig": {"mode": "ai", "tone": "casual"}}])
        self.assertIsNone(made["steps"][0]["aiConfig"])
        self.assertEqual(made["steps"][1]["aiConfig"]["tone"], "casual")
        bad = self.client.post("/campaigns", json={"action": "create", "name": "C", "steps": [{"type": "message", "order": 0, "message": "x", "aiConfig": {"tone": "loud"}}]})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("Tone must", bad.text)

    def test_only_ai_assisted_steps_are_estimated_and_the_estimate_names_the_provider_and_cost(self):
        made = self.campaign([{"type": "connection_request", "order": 0, "message": "hi", "aiConfig": {"mode": "direct"}},
                              {"type": "message", "order": 1, "message": "yo", "aiConfig": {"mode": "ai"}}])
        est = self.client.post(f"/campaigns/{made['id']}/drafts/estimate").json()
        self.assertEqual((est["count"], est["provider"], est["estimatedUsd"]), (2, "template", 0.0))  # 2 leads x 1 AI step
        self.assertIn("cost nothing", est["note"])

    def test_preview_writes_one_message_with_its_cost_and_needs_a_real_lead(self):
        made = self.campaign([{"type": "message", "order": 0, "message": "yo", "aiConfig": {"mode": "ai"}}])
        r = self.client.post(f"/campaigns/{made['id']}/drafts/preview", json={"stepType": "message", "config": {"mode": "ai", "tone": "witty"}})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual((data["provider"], data["estimatedUsd"], data["leadName"]), ("template", 0.0, "Ada"))
        self.assertTrue(data["text"])
        self.assertEqual(self.client.post(f"/campaigns/{made['id']}/drafts/preview", json={"stepType": "message", "config": {"tone": "loud"}}).status_code, 422)
        empty = self.client.post("/campaigns", json={"action": "create", "name": "Empty", "accountId": self.account_id}).json()
        self.assertEqual(self.client.post(f"/campaigns/{empty['id']}/drafts/preview", json={"stepType": "message"}).status_code, 409)


if __name__ == "__main__":
    unittest.main()
