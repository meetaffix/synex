"""Deepgram is the only AI service: message drafting and post editing go through its Voice Agent (a mocked server
here, never the real one), fall back to the local template when it fails, and never expose the key."""
import atexit
import json
import logging
import os
import tempfile
import unittest
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"  # tests use the built-in sign-in whatever backend/.env says
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["LINKEDIN_CLIENT_ID"] = "test-client"
os.environ["LINKEDIN_CLIENT_SECRET"] = "test-client-secret"
os.environ["DEEPGRAM_API_KEY"] = "dg-SENTINEL-never-leak-9f3a7c"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import providers
from app.assistant.config import assistant_config
from app.config import settings
safety.assert_isolated_database(settings.database_url)
from app.database import Base, engine as db_engine
from app.deepgram_text import DeepgramTextError, complete
from app.main import app, _attempts
from app.migrations import migrate
from mock_deepgram import MockDeepgram

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
KEY = os.environ["DEEPGRAM_API_KEY"]
PASSWORD = "Strong-Test-Password!"
DRAFT = "Hi Ada, I admire the work Analytical Engines is doing in fintech. Would love to connect."


class DraftingCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        self.lines: list[str] = []
        handler = logging.Handler(logging.DEBUG)
        handler.emit = lambda record: self.lines.append(record.getMessage())
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Olive Owner", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)

    def agent(self, script=None):
        mock = MockDeepgram(script or {"connection": [("text", "assistant", DRAFT), ("audio",), ("done",)]}, expected_auth=f"Token {KEY}")
        mock.__enter__()
        self.addCleanup(mock.__exit__, None, None, None)
        patcher = patch.object(assistant_config, "deepgram_agent_url", mock.url)
        patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def post(self, **fields):
        return self.client.post("/ai/generate-message", json={"stepType": "connection_request", "firstName": "Ada", "company": "Analytical Engines", "jobTitle": "CTO", **fields})


class OneShotCompletionTest(DraftingCase):
    def test_the_reply_is_the_agents_text_and_the_audio_is_discarded(self):
        mock = self.agent()
        self.assertEqual(complete("Be brief.", "Write a connection note"), DRAFT)
        self.assertEqual(mock.headers[0]["authorization"], f"Token {KEY}")
        settings_sent = mock.settings()
        self.assertEqual(settings_sent["agent"]["think"]["prompt"], "Be brief.")
        self.assertNotIn("functions", settings_sent["agent"]["think"])  # no tools: a draft cannot change anything
        self.assertNotIn("greeting", settings_sent["agent"])
        self.assertTrue(settings_sent["mip_opt_out"])
        self.assertEqual(mock.messages("InjectUserMessage")[0]["content"], "Write a connection note")

    def test_failures_raise_without_the_key(self):
        with patch.object(assistant_config, "deepgram_agent_url", "ws://127.0.0.1:1/v1/agent/converse"):
            with self.assertRaises(DeepgramTextError) as caught:
                complete("x", "y", timeout=3)
        self.assertNotIn(KEY, str(caught.exception))
        with patch.object(assistant_config, "deepgram_api_key", ""):
            with self.assertRaises(DeepgramTextError):
                complete("x", "y")

    def test_a_wrong_key_is_refused_and_never_echoed(self):
        self.agent()
        with patch.object(assistant_config, "deepgram_api_key", "dg-other-key"):
            with self.assertRaises(DeepgramTextError) as caught:
                complete("x", "y", timeout=3)
        self.assertNotIn("dg-other-key", str(caught.exception))


class GenerateMessageTest(DraftingCase):
    def test_the_provider_is_deepgram_only_when_the_key_is_set(self):
        self.assertIsInstance(providers.get_ai_provider(), providers.DeepgramAIProvider)
        with patch.object(assistant_config, "deepgram_api_key", ""):
            self.assertIsInstance(providers.get_ai_provider(), providers.TemplateAIProvider)

    def test_the_route_returns_the_deepgram_draft_built_from_the_leads_fields(self):
        mock = self.agent()
        r = self.post()
        self.assertEqual((r.status_code, r.json()), (200, {"body": DRAFT}))
        asked = mock.messages("InjectUserMessage")[0]["content"]
        for fact in ("Ada", "Analytical Engines", "CTO", "connection request"):
            self.assertIn(fact, asked)
        self.assertNotIn(KEY, r.text)

    def test_when_deepgram_fails_the_local_template_draft_is_returned(self):
        with patch.object(assistant_config, "deepgram_agent_url", "ws://127.0.0.1:1/v1/agent/converse"), patch("app.deepgram_text.complete", side_effect=DeepgramTextError("down")):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ada", r.json()["body"])
        self.assertNotIn(KEY, r.text)
        self.assertNotIn(KEY, "\n".join(self.lines))

    def test_without_a_key_the_template_is_used_and_nothing_is_contacted(self):
        with patch.object(assistant_config, "deepgram_api_key", ""):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ada", r.json()["body"])

    def test_requires_sign_in(self):
        anonymous = TestClient(app, headers=ORIGIN)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.post("/ai/generate-message", json={"stepType": "message"}).status_code, 401)


class PostAssistTest(DraftingCase):
    def assist(self, **fields):
        return self.client.post("/publishing/assist", json={"body": "we shipped a thing", "instruction": "Make concise", **fields})

    def test_the_edited_post_comes_from_deepgram(self):
        mock = self.agent({"concise": [("text", "assistant", "We shipped."), ("done",)]})
        r = self.assist()
        self.assertEqual((r.status_code, r.json()), (200, {"body": "We shipped."}))
        self.assertIn("Never invent claims", mock.settings()["agent"]["think"]["prompt"])
        self.assertNotIn(KEY, r.text)

    def test_not_configured_and_failure_are_explicit_and_leave_the_draft_alone(self):
        with patch.object(assistant_config, "deepgram_api_key", ""):
            self.assertEqual(self.assist().status_code, 503)
        with patch("app.publishing.complete", side_effect=DeepgramTextError("down")):
            r = self.assist()
        self.assertEqual(r.status_code, 502)
        self.assertIn("Your draft has not changed", r.json()["detail"])
        self.assertNotIn(KEY, r.text)

    def test_the_diagnostics_report_assistance_as_configured_by_the_deepgram_key(self):
        r = self.client.get("/publishing/diagnostics")
        if r.status_code == 200:
            self.assertTrue(r.json()["aiConfigured"])
            with patch.object(assistant_config, "deepgram_api_key", ""):
                self.assertFalse(self.client.get("/publishing/diagnostics").json()["aiConfigured"])


class SpintaxFallbackTest(unittest.TestCase):
    """Without Deepgram the draft comes from templates with variables and spintax, the same wording for the same lead."""
    def test_spin_picks_one_option_deterministically_and_leaves_other_braces_alone(self):
        text = "{Hi|Hello|Hey} {{first_name}}, {solo} {a|b}"
        first = providers.spin(text, "lead-1")
        self.assertEqual(first, providers.spin(text, "lead-1"))
        self.assertIn("{{first_name}}", first)
        self.assertIn("{solo}", first)
        self.assertNotIn("|", first)
        self.assertGreater(len({providers.spin("{a|b|c|d|e|f}", f"lead-{n}") for n in range(40)}), 1)  # different leads vary

    def test_variables_then_spintax_in_a_step_message(self):
        from types import SimpleNamespace
        lead = SimpleNamespace(id="lead-9", first_name="Ada", last_name="Lovelace", company="Engines", job_title="CTO")
        once = providers.render_variables("{Hi|Hello} {{first_name}} at {{company}}", lead)
        self.assertEqual(once, providers.render_variables("{Hi|Hello} {{first_name}} at {{company}}", lead))
        self.assertIn(once, ("Hi Ada at Engines", "Hello Ada at Engines"))

    def test_the_template_provider_drafts_with_the_leads_fields_and_no_leftover_markup(self):
        for step in ("connection_request", "message", "follow_up"):
            body = providers.TemplateAIProvider().generate_message(step, "friendly", {"first_name": "Ada", "company": "Engines", "job_title": "CTO"})
            self.assertIn("Ada", body)
            self.assertIn("Engines", body)
            self.assertNotRegex(body, r"[{}|]")


if __name__ == "__main__":
    unittest.main()
