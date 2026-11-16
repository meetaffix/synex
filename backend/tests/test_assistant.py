"""Assistant tests: tool permissions, schemas, audit, confirmation, ceilings, key secrecy, caps, idle timeout, and
a scripted conversation through the real backend against a mocked Deepgram agent server. No real Deepgram calls."""
import atexit
import json
import logging
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
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
from app import engine, models
from app.assistant import registry, relay, service
from app.assistant import tools as _tools  # noqa: F401  (registers the tools)
from app.assistant.config import assistant_config
from app.assistant.models import AssistantAudit, AssistantMessage, AssistantProposal, AssistantSettings, AssistantUsage
from app.config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, settings
safety.assert_isolated_database(settings.database_url)
from app.database import Base, SessionLocal, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate
from mock_deepgram import MockDeepgram

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
KEY = os.environ["DEEPGRAM_API_KEY"]
PASSWORD = "Strong-Test-Password!"


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class AssistantCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        service._tickets.clear()
        service._active.clear()
        self.logs = LogCapture()
        logging.getLogger().addHandler(self.logs)
        self.addCleanup(logging.getLogger().removeHandler, self.logs)
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Olive Owner", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        self.owner_id = r.json()["user"]["id"]
        self.bodies: list[str] = []  # every response body, checked for the key at the end of tests that use it

    # ---- helpers -------------------------------------------------------------------------------------------
    def member_client(self, role: str) -> tuple[TestClient, str]:
        c = TestClient(app, headers=ORIGIN)
        self.addCleanup(c.close)
        email = f"{role}@example.com"
        r = c.post("/auth", json={"action": "register", "email": email, "fullName": f"{role.title()} Person", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        uid = r.json()["user"]["id"]
        with SessionLocal() as db:
            db.add(models.TeamMember(owner_id=self.owner_id, member_id=uid, email=email, role=role, status="active"))
            db.commit()
        return c, uid

    def user(self, db, uid):
        return db.get(models.User, uid)

    def call(self, uid, name, args=None, page=None):
        with SessionLocal() as db:
            return registry.run_tool(db, db.get(models.User, uid), name, json.dumps(args or {}), page)

    def audits(self, tool=None):
        with SessionLocal() as db:
            q = db.query(AssistantAudit).order_by(AssistantAudit.created_at)
            return [a for a in q.all() if tool is None or a.tool == tool]

    def counts(self):
        with SessionLocal() as db:
            return tuple(db.query(m).count() for m in (models.Lead, models.LeadList, models.Template, models.Campaign))

    def seed(self):
        with SessionLocal() as db:
            account = models.LinkedInAccount(user_id=self.owner_id, name="Main sender", status="active", session_status="connected", daily_action_limit=50)
            lst = models.LeadList(user_id=self.owner_id, name="Existing list")
            lead = models.Lead(user_id=self.owner_id, first_name="Priya", last_name="Nair", company="Finlytics", job_title="CTO", email="priya@secret-mail.example", phone="+91 99999 11111")
            lead.lists = [lst]
            tpl = models.Template(user_id=self.owner_id, name="Intro", category="first_message", body="Hi {{first_name}}")
            camp = models.Campaign(user_id=self.owner_id, name="Fintech push", status="active", launched_at=datetime.now(timezone.utc), account_id=None)
            draft = models.Campaign(user_id=self.owner_id, name="Unlaunched", status="draft")
            db.add_all([account, lst, lead, tpl, camp, draft])
            db.commit()
            return {"account": account.id, "list": lst.id, "lead": lead.id, "template": tpl.id, "campaign": camp.id, "draft": draft.id}

    def ticket(self, client=None, mode="text", page=None):
        r = (client or self.client).post("/assistant/session", json={"mode": mode, "page": page or {}})
        self.bodies.append(r.text)
        return r

    def recv(self, ws):
        event = ws.receive()
        if event.get("bytes") is not None:
            return {"_bytes": len(event["bytes"])}
        text = event.get("text")
        self.bodies.append(text or "")
        return json.loads(text)

    def collect(self, ws, until, limit=60):
        seen = []
        for _ in range(limit):
            msg = self.recv(ws)
            seen.append(msg)
            if until(msg):
                return seen
        self.fail(f"never saw the expected message; saw {seen}")

    def open_session(self, mock, mode="text", client=None, page=None):
        """Connect through the real backend to the mock and wait for ready."""
        assistant_config.deepgram_agent_url = mock.url
        t = self.ticket(client, mode, page).json()["ticket"]
        ws_cm = (client or self.client).websocket_connect("/assistant/ws")
        ws = ws_cm.__enter__()
        self.addCleanup(lambda: ws_cm.__exit__(None, None, None))
        ws.send_json({"type": "auth", "ticket": t})
        ready = self.recv(ws)
        return ws, ready


class ToolRegistryTest(AssistantCase):
    def test_every_tool_has_a_plain_json_schema_and_a_valid_shape(self):
        defs = registry.function_definitions()
        self.assertGreaterEqual(len(defs), 15)
        for d in defs:
            text = json.dumps(d)
            self.assertNotIn("$ref", text, d["name"])
            self.assertNotIn("$defs", text, d["name"])
            self.assertEqual(d["parameters"]["type"], "object", d["name"])
            self.assertTrue(d["description"])
        for t in registry.REGISTRY.values():
            self.assertIn(t.kind, ("read", "draft", "write"))
            self.assertIn(t.min_role, ("member", "manager", "admin"))
            if t.kind == "write":
                self.assertTrue(t.propose and t.apply)
        self.assertFalse([n for n in registry.REGISTRY if n.split("_")[0] in ("confirm", "send", "delete", "launch", "import", "reply")])

    def test_things_not_available_yet_are_refused_plainly(self):
        for name in ("send_message", "reply_in_inbox", "launch_campaign", "delete_campaign", "import_from_linkedin"):
            out = self.call(self.owner_id, name, {})
            self.assertFalse(out.result["ok"])
            self.assertIn("not available yet", out.result["error"])

    def test_invalid_arguments_and_unknown_arguments_are_refused_and_audited(self):
        ids = self.seed()
        out = self.call(self.owner_id, "search_campaigns", {"limit": 500})
        self.assertFalse(out.result["ok"])
        self.assertIn("Invalid arguments", out.result["error"])
        extra = self.call(self.owner_id, "get_campaign", {"campaign_id": ids["campaign"], "sneaky": True})
        self.assertFalse(extra.result["ok"])
        bad_json = None
        with SessionLocal() as db:
            bad_json = registry.run_tool(db, db.get(models.User, self.owner_id), "get_campaign", "{not json")
        self.assertFalse(bad_json.result["ok"])
        self.assertEqual([a.status for a in self.audits()], ["invalid", "invalid", "invalid"])

    def test_every_call_leaves_an_audit_entry_with_minimised_arguments(self):
        ids = self.seed()
        self.call(self.owner_id, "search_leads", {"query": "Priya Nair"})
        self.call(self.owner_id, "create_lead_list", {"name": "Secret Targets", "leads": [{"first_name": "Zed", "last_name": "Zero", "company": "Hidden Corp"}]})
        reads, writes = self.audits("search_leads"), self.audits("create_lead_list")
        self.assertEqual((reads[0].status, reads[0].kind, reads[0].via, reads[0].user_id), ("ok", "read", "assistant", self.owner_id))
        self.assertIsNotNone(reads[0].created_at)
        self.assertEqual((writes[0].status, writes[0].kind), ("proposed", "write"))
        dump = json.dumps([a.arguments for a in reads + writes] + [a.result for a in reads + writes])
        for secret in ("Priya", "Nair", "Zed", "Zero", "Hidden Corp", "Secret Targets"):
            self.assertNotIn(secret, dump)

    def test_read_tools_return_workspace_data_without_contact_details(self):
        ids = self.seed()
        lead = self.call(self.owner_id, "get_lead", {"lead_id": ids["lead"]}).result
        self.assertEqual(lead["name"], "Priya Nair")
        blob = json.dumps(lead) + json.dumps(self.call(self.owner_id, "search_leads", {"query": "priya"}).result)
        self.assertNotIn("secret-mail", blob)
        self.assertNotIn("99999", blob)
        self.assertEqual(self.call(self.owner_id, "get_dashboard_summary").result["campaignsByStatus"], {"active": 1, "draft": 1})
        self.assertEqual(self.call(self.owner_id, "list_lead_lists").result["lists"][0]["leadCount"], 1)
        self.assertEqual(self.call(self.owner_id, "explain_campaign_status", {"campaign_id": ids["draft"]}).result["status"], "draft")
        acct = self.call(self.owner_id, "explain_account_status", {"account_id": ids["account"]}).result
        self.assertIn("healthy", acct["reasons"][0])

    def test_a_record_from_another_workspace_is_not_found(self):
        ids = self.seed()
        other, other_id = TestClient(app, headers=ORIGIN), None
        self.addCleanup(other.close)
        r = other.post("/auth", json={"action": "register", "email": "other@example.com", "fullName": "Other", "password": PASSWORD})
        other_id = r.json()["user"]["id"]
        for name, args in (("get_lead", {"lead_id": ids["lead"]}), ("get_campaign", {"campaign_id": ids["campaign"]}), ("explain_account_status", {"account_id": ids["account"]})):
            out = self.call(other_id, name, args).result
            self.assertFalse(out["ok"], name)
            self.assertIn("can't find", out["error"])


class PermissionTest(AssistantCase):
    def test_each_tool_enforces_its_minimum_role(self):
        ids = self.seed()
        _, member = self.member_client("member")
        _, manager = self.member_client("manager")
        for tool in registry.REGISTRY.values():
            for uid, role in ((member, "member"), (manager, "manager")):
                if registry.ROLE_RANK[role] >= registry.ROLE_RANK[tool.min_role]:
                    continue
                out = self.call(uid, tool.name, {})  # the role check comes before argument validation
                self.assertFalse(out.result["ok"], f"{tool.name} as {role}")
                self.assertIn("does not allow", out.result["error"], f"{tool.name} as {role}")
        denied = [a for a in self.audits() if a.status == "denied"]
        self.assertTrue(denied)
        self.assertTrue(all(a.via == "assistant" for a in denied))

    def test_roles_that_meet_the_rule_can_use_the_tool(self):
        ids = self.seed()
        _, member = self.member_client("member")
        _, manager = self.member_client("manager")
        self.assertTrue(self.call(member, "list_templates").result["ok"])
        self.assertTrue(self.call(manager, "create_template", {"name": "T", "body": "x"}).result["ok"])
        self.assertFalse(self.call(manager, "set_account_state", {"account_id": ids["account"], "action": "pause"}).result["ok"])
        self.assertEqual(self.call(self.owner_id, "set_account_state", {"account_id": ids["account"], "action": "pause"}).result["status"], "awaiting_confirmation")

    def test_a_manager_cannot_change_account_limits_even_though_the_tool_is_manager_level(self):
        ids = self.seed()
        _, manager = self.member_client("manager")
        out = self.call(manager, "set_daily_limits", {"target": "account", "id": ids["account"], "daily_action_limit": 20}).result
        self.assertFalse(out["ok"])
        self.assertIn("admin", out["error"])

    def test_member_cannot_confirm_and_nobody_can_confirm_someone_elses_proposal(self):
        ids = self.seed()
        mclient, member = self.member_client("member")
        out = self.call(self.owner_id, "create_template", {"name": "T", "body": "x"}).result
        self.assertEqual(mclient.post(f"/assistant/proposals/{out['proposalId']}/confirm").status_code, 404)
        self.assertEqual(self.counts()[2], 1)
        # Role lowered between proposal and click: the role is checked again at apply time.
        with SessionLocal() as db:
            seat = db.query(models.TeamMember).filter_by(member_id=member).one()
            seat.role = "manager"
            db.commit()
        mine = self.call(member, "create_template", {"name": "M", "body": "x"}).result
        with SessionLocal() as db:
            db.query(models.TeamMember).filter_by(member_id=member).one().role = "member"
            db.commit()
        r = mclient.post(f"/assistant/proposals/{mine['proposalId']}/confirm")
        self.assertEqual(r.status_code, 403, r.text)
        self.assertEqual(self.counts()[2], 1)

    def test_a_turned_off_assistant_refuses_every_tool(self):
        self.seed()
        r = self.client.put("/assistant/settings", json={"enabled": False})
        self.assertEqual(r.status_code, 200, r.text)
        out = self.call(self.owner_id, "list_templates").result
        self.assertFalse(out["ok"])
        self.assertIn("turned off", out["error"])


class ConfirmationTest(AssistantCase):
    def valid_calls(self, ids):
        return {
            "create_lead_list": {"name": "Fintech CTOs", "leads": [{"first_name": "Asha", "last_name": "Rao", "company": "PayCo"}]},
            "create_template": {"name": "Warm intro", "category": "connection", "body": "Hi {{first_name}}"},
            "update_template": {"template_id": ids["template"], "body": "Changed text"},
            "create_campaign_draft": {"name": "Demo push", "steps": [{"type": "profile_visit"}, {"type": "connection_request", "message": "Hi"}, {"type": "wait", "delay_hours": 48}, {"type": "message", "message": "Thanks"}],
                                      "lead_list_id": ids["list"], "daily_connection_limit": 15},
            "set_campaign_state": {"campaign_id": ids["campaign"], "action": "pause"},
            "set_account_state": {"account_id": ids["account"], "action": "pause"},
            "set_daily_limits": {"target": "account", "id": ids["account"], "daily_action_limit": 30},
            "add_do_not_contact": {"kind": "company", "values": ["Acme Inc"]},
        }

    def test_every_write_tool_only_proposes_until_the_user_confirms(self):
        ids = self.seed()
        calls = self.valid_calls(ids)
        self.assertEqual(set(calls), {t.name for t in registry.REGISTRY.values() if t.kind == "write"})
        before = self.counts()
        with SessionLocal() as db:
            snapshot = (db.get(models.Template, ids["template"]).body, db.get(models.Campaign, ids["campaign"]).status,
                        db.get(models.LinkedInAccount, ids["account"]).status, db.get(models.LinkedInAccount, ids["account"]).daily_action_limit)
        proposals = {}
        for name, args in calls.items():
            out = self.call(self.owner_id, name, args)
            self.assertTrue(out.result["ok"], f"{name}: {out.result}")
            self.assertEqual(out.result["status"], "awaiting_confirmation", name)
            self.assertIn("NOT applied", out.result["message"])
            self.assertEqual(out.ui[0]["type"], "proposal")
            card = out.ui[0]["proposal"]
            self.assertEqual(card["status"], "pending")
            self.assertTrue(card["summary"] and card["changes"], name)
            proposals[name] = card["id"]
        self.assertEqual(self.counts(), before, "a proposal changed data")
        with SessionLocal() as db:
            after = (db.get(models.Template, ids["template"]).body, db.get(models.Campaign, ids["campaign"]).status,
                     db.get(models.LinkedInAccount, ids["account"]).status, db.get(models.LinkedInAccount, ids["account"]).daily_action_limit)
        self.assertEqual(after, snapshot)
        self.assertEqual({a.status for a in self.audits() if a.kind == "write"}, {"proposed"})
        # Only the click applies. Each endpoint call is the user's click.
        for name, pid in proposals.items():
            r = self.client.post(f"/assistant/proposals/{pid}/confirm")
            self.assertEqual(r.status_code, 200, f"{name}: {r.text}")
            self.assertEqual(r.json()["status"], "applied")
        leads, lists, templates, campaigns = self.counts()
        self.assertEqual((leads, lists, templates, campaigns), (before[0] + 1, before[1] + 1, before[2] + 1, before[3] + 1))
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Template, ids["template"]).body, "Changed text")
            self.assertEqual(db.get(models.Campaign, ids["campaign"]).status, "paused")
            self.assertEqual(db.get(models.LinkedInAccount, ids["account"]).status, "paused")
            self.assertEqual(db.get(models.LinkedInAccount, ids["account"]).daily_action_limit, 30)
            draft = db.query(models.Campaign).filter_by(name="Demo push").one()
            self.assertEqual(draft.status, "draft")
            self.assertEqual([s.type for s in sorted(draft.steps, key=lambda s: s.order)], ["profile_visit", "connection_request", "wait", "message", "end"])
        self.assertEqual({a.status for a in self.audits() if a.kind == "write"}, {"proposed", "applied"})
        again = self.client.post(f"/assistant/proposals/{proposals['create_template']}/confirm")
        self.assertEqual(again.status_code, 409)

    def test_cancel_applies_nothing_and_cannot_be_undone_by_confirm(self):
        self.seed()
        before = self.counts()
        pid = self.call(self.owner_id, "create_template", {"name": "T", "body": "x"}).result["proposalId"]
        self.assertEqual(self.client.post(f"/assistant/proposals/{pid}/cancel").json()["status"], "cancelled")
        self.assertEqual(self.client.post(f"/assistant/proposals/{pid}/confirm").status_code, 409)
        self.assertEqual(self.counts(), before)
        self.assertIn("cancelled", [a.status for a in self.audits("create_template")])

    def test_an_expired_proposal_cannot_be_confirmed(self):
        self.seed()
        pid = self.call(self.owner_id, "create_template", {"name": "T", "body": "x"}).result["proposalId"]
        with SessionLocal() as db:
            db.get(AssistantProposal, pid).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.post(f"/assistant/proposals/{pid}/confirm").status_code, 409)

    def test_resuming_an_unlaunched_campaign_is_not_available(self):
        ids = self.seed()
        out = self.call(self.owner_id, "set_campaign_state", {"campaign_id": ids["draft"], "action": "resume"}).result
        self.assertFalse(out["ok"])
        self.assertIn("not available through the assistant yet", out["error"])

    def test_drafts_are_text_only_and_never_sent_or_saved(self):
        ids = self.seed()
        before = self.counts()
        with SessionLocal() as db:
            messages = db.query(models.Message).count()
        out = self.call(self.owner_id, "draft_message", {"step_type": "connection_request", "lead_id": ids["lead"], "text": "Hi {{first_name}}, loved your work at {{company}}."})
        self.assertEqual(out.result["draft"], "Hi Priya, loved your work at Finlytics.")
        self.assertEqual(out.ui[0]["type"], "draft")
        long = self.call(self.owner_id, "draft_message", {"step_type": "connection_request", "text": "x" * 400}).result
        self.assertEqual(len(long["draft"]), 300)
        self.assertTrue(long["warnings"])
        generated = self.call(self.owner_id, "draft_message", {"step_type": "message", "lead_id": ids["lead"]}).result
        self.assertIn("Priya", generated["draft"])
        self.assertEqual(self.counts(), before)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Message).count(), messages)

    def test_sequence_and_limit_suggestions_respect_the_safety_rules(self):
        ids = self.seed()
        seq = self.call(self.owner_id, "propose_sequence", {"goal": "book demos with fintech CTOs"}).result
        self.assertIn("connection_request", [s["type"] for s in seq["steps"]])
        for age in ("new", "warming", "established"):
            s = self.call(self.owner_id, "suggest_limits", {"account_age": age}).result
            self.assertLessEqual(s["dailyActionLimit"], DAILY_ACTION_CEILING)
            self.assertLessEqual(s["dailyConnectionLimit"], DAILY_TYPE_CEILINGS["send_invite"])
            self.assertLessEqual(s["dailyMessageLimit"], DAILY_TYPE_CEILINGS["send_message"])
        self.assertEqual(self.call(self.owner_id, "suggest_limits", {"account_id": ids["account"]}).result["accountAge"], "new")


class CeilingTest(AssistantCase):
    def test_limits_above_a_ceiling_are_refused_naming_it(self):
        ids = self.seed()
        cases = [
            ({"target": "account", "id": ids["account"], "daily_action_limit": DAILY_ACTION_CEILING + 1}, str(DAILY_ACTION_CEILING)),
            ({"target": "campaign", "id": ids["campaign"], "daily_connection_limit": DAILY_TYPE_CEILINGS["send_invite"] + 1}, str(DAILY_TYPE_CEILINGS["send_invite"])),
            ({"target": "campaign", "id": ids["campaign"], "daily_message_limit": DAILY_TYPE_CEILINGS["send_message"] + 1}, str(DAILY_TYPE_CEILINGS["send_message"])),
        ]
        for args, ceiling in cases:
            out = self.call(self.owner_id, "set_daily_limits", args).result
            self.assertFalse(out["ok"], args)
            self.assertIn("hard ceiling", out["error"])
            self.assertIn(ceiling, out["error"])
        out = self.call(self.owner_id, "create_campaign_draft", {"name": "Too hot", "steps": [{"type": "connection_request"}], "daily_connection_limit": 41}).result
        self.assertFalse(out["ok"])
        self.assertIn("40", out["error"])
        self.assertEqual(self.counts()[3], 2)

    def test_a_proposal_edited_past_a_ceiling_still_fails_when_confirmed(self):
        ids = self.seed()
        pid = self.call(self.owner_id, "set_daily_limits", {"target": "account", "id": ids["account"], "daily_action_limit": 30}).result["proposalId"]
        with SessionLocal() as db:
            p = db.get(AssistantProposal, pid)
            p.arguments = {**p.arguments, "daily_action_limit": 5000}
            db.commit()
        r = self.client.post(f"/assistant/proposals/{pid}/confirm")
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("200", r.text)
        with SessionLocal() as db:
            self.assertEqual(db.get(models.LinkedInAccount, ids["account"]).daily_action_limit, 50)

    def test_zero_means_stopped_and_stays_zero(self):
        ids = self.seed()
        pid = self.call(self.owner_id, "set_daily_limits", {"target": "account", "id": ids["account"], "daily_action_limit": 0}).result["proposalId"]
        self.assertEqual(self.client.post(f"/assistant/proposals/{pid}/confirm").status_code, 200)
        cid = self.call(self.owner_id, "set_daily_limits", {"target": "campaign", "id": ids["campaign"], "daily_connection_limit": 0}).result["proposalId"]
        self.assertEqual(self.client.post(f"/assistant/proposals/{cid}/confirm").status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(engine.configured_daily_limit(db.get(models.LinkedInAccount, ids["account"])), 0)
            self.assertEqual(engine.campaign_type_limit(db.get(models.Campaign, ids["campaign"]), "send_invite"), 0)

    def test_the_card_shows_the_current_limit_from_the_engine(self):
        ids = self.seed()
        card = self.call(self.owner_id, "set_daily_limits", {"target": "campaign", "id": ids["campaign"], "daily_connection_limit": 25}).ui[0]["proposal"]
        self.assertIn("20 now, 25 after", " ".join(card["changes"]))


class SessionApiTest(AssistantCase):
    def test_session_returns_a_ticket_and_config_but_never_the_key(self):
        r = self.ticket(mode="voice")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["agent"]["model"], assistant_config.assistant_llm_model)
        self.assertEqual(data["agent"]["voice"], assistant_config.assistant_voice)
        self.assertEqual(data["idleTimeoutSeconds"], 120)
        self.assertNotIn(KEY, r.text)
        for path in ("/assistant/settings", "/assistant/audit", "/assistant/history"):
            self.assertNotIn(KEY, self.client.get(path).text)
        self.assertNotIn("dg-", json.dumps(data))

    def test_session_needs_a_signed_in_user(self):
        anon = TestClient(app, headers=ORIGIN)
        self.addCleanup(anon.close)
        self.assertEqual(anon.post("/assistant/session", json={"mode": "text"}).status_code, 401)

    def test_off_cap_and_unconfigured_each_give_a_clear_message(self):
        self.client.put("/assistant/settings", json={"enabled": False})
        r = self.ticket()
        self.assertEqual(r.status_code, 403)
        self.assertIn("turned off", r.json()["detail"])
        self.client.put("/assistant/settings", json={"enabled": True, "monthlyMinuteCap": 1})
        with SessionLocal() as db:
            db.add(AssistantUsage(workspace_id=self.owner_id, month=service.month_key(), seconds=60))
            db.commit()
        r = self.ticket()
        self.assertEqual(r.status_code, 429)
        self.assertIn("1 assistant minutes", r.json()["detail"])
        self.assertTrue(self.client.get("/assistant/settings").json()["capReached"])
        self.client.put("/assistant/settings", json={"monthlyMinuteCap": 10})
        with patch.object(assistant_config, "deepgram_api_key", ""):
            r = self.ticket()
            self.assertEqual(r.status_code, 503)
            self.assertFalse(self.client.get("/assistant/settings").json()["available"])

    def test_only_an_admin_edits_settings_and_values_are_bounded(self):
        mclient, _ = self.member_client("manager")
        self.assertEqual(mclient.put("/assistant/settings", json={"enabled": False}).status_code, 403)
        self.assertFalse(mclient.get("/assistant/settings").json()["canEdit"])
        self.assertEqual(self.client.put("/assistant/settings", json={"idleTimeoutSeconds": 5}).status_code, 422)
        self.assertEqual(self.client.put("/assistant/settings", json={"language": "fr"}).status_code, 422)
        ok = self.client.put("/assistant/settings", json={"monthlyMinuteCap": 30, "idleTimeoutSeconds": 300, "language": "en-IN", "historyEnabled": True})
        self.assertEqual((ok.json()["monthlyMinuteCap"], ok.json()["idleTimeoutSeconds"], ok.json()["language"], ok.json()["historyEnabled"]), (30, 300, "en-IN", True))

    def test_defaults_are_a_two_minute_idle_timeout_and_history_off(self):
        s = self.client.get("/assistant/settings").json()
        self.assertEqual((s["idleTimeoutSeconds"], s["historyEnabled"], s["enabled"]), (120, False, True))

    def test_the_session_endpoint_rejects_a_foreign_origin(self):
        r = self.client.post("/assistant/session", json={"mode": "text"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)


class RelayTest(AssistantCase):
    def setUp(self):
        super().setUp()
        self.ids = self.seed()
        for name, value in (("TICK_SECONDS", 0.1), ("USAGE_SECONDS", 0.2)):
            patcher = patch.object(relay, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_scripted_conversation_with_a_function_call_runs_through_the_real_backend(self):
        script = {"dashboard": [("text", "assistant", "Let me check."), ("call", "get_dashboard_summary", {}), ("audio",),
                                ("text", "assistant", "You have 1 lead and 1 active campaign."), ("done",)]}
        with MockDeepgram(script, expected_auth=f"Token {KEY}") as mock:
            ws, ready = self.open_session(mock, mode="voice", page={"path": "/campaigns", "campaignId": self.ids["campaign"]})
            self.assertEqual(ready["type"], "ready")
            ws.send_json({"type": "user_text", "text": "How is my dashboard?"})
            seen = self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            kinds = [m.get("type") or "audio" for m in seen]
            self.assertIn("tool", kinds)
            self.assertIn("audio", kinds)
            self.assertEqual([m for m in seen if m.get("role") == "user"][0], {"type": "transcript", "role": "user", "text": "How is my dashboard?", "typed": True})
            self.assertEqual([m["status"] for m in seen if m.get("type") == "tool"], ["running", "done"])
            self.assertEqual([m["text"] for m in seen if m.get("role") == "assistant"][-1], "You have 1 lead and 1 active campaign.")
            # The key went to Deepgram in the Authorization header, and nowhere else.
            self.assertEqual(mock.headers[0]["authorization"], f"Token {KEY}")
            settings_message = mock.settings()
            self.assertNotIn(KEY, json.dumps(settings_message))
            think = settings_message["agent"]["think"]
            self.assertEqual(think["provider"], {"type": "anthropic", "model": assistant_config.assistant_llm_model})
            self.assertEqual(settings_message["agent"]["speak"]["provider"]["model"], assistant_config.assistant_voice)
            self.assertEqual(settings_message["agent"]["listen"]["provider"]["language"], "en")
            self.assertEqual(settings_message["audio"]["input"], {"encoding": "linear16", "sample_rate": 16000})
            self.assertTrue(all("endpoint" not in f for f in think["functions"]), "functions must be client-side (run by our relay)")
            self.assertIn("Fintech push", think["prompt"])
            self.assertIn('the campaign "Fintech push"', think["prompt"])
            self.assertNotIn("secret-mail", think["prompt"])
            self.assertNotIn("99999", think["prompt"])
            self.assertIn("Leads: 1.", think["prompt"])
            result = json.loads(mock.call_results[0]["content"])
            self.assertTrue(result["ok"])
            self.assertEqual(result["campaignsByStatus"], {"active": 1, "draft": 1})
        audit = self.audits("get_dashboard_summary")
        self.assertEqual((audit[0].status, audit[0].via, audit[0].user_id), ("ok", "assistant", self.owner_id))

    def test_a_write_in_conversation_waits_for_the_click_then_the_agent_is_told(self):
        args = {"name": "Fintech CTOs", "leads": [{"first_name": "Asha", "last_name": "Rao", "company": "PayCo"}]}
        script = {"make a list": [("call", "create_lead_list", args), ("text", "assistant", "I've prepared it. Press Confirm."), ("done",)]}
        before = self.counts()
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock)
            ws.send_json({"type": "user_text", "text": "Please make a list of fintech CTOs"})
            seen = self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            proposal = next(m for m in seen if m.get("type") == "proposal")["proposal"]
            self.assertEqual(proposal["status"], "pending")
            self.assertEqual(self.counts(), before, "the voice session applied a change without a click")
            self.assertIn("NOT applied", json.loads(mock.call_results[0]["content"])["message"])
            # A spoken or typed 'yes' is only text to the agent; it cannot apply anything.
            ws.send_json({"type": "user_text", "text": "yes, confirm it"})
            self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            self.assertEqual(self.counts(), before)
            ws.send_json({"type": "note", "proposalId": proposal["id"]})  # the browser says it was clicked: ignored while pending
            time.sleep(0.3)
            self.assertFalse([m for m in mock.messages("InjectUserMessage") if "pressed Confirm" in m["content"]])
            self.assertEqual(self.client.post(f"/assistant/proposals/{proposal['id']}/confirm").status_code, 200)
            ws.send_json({"type": "note", "proposalId": proposal["id"]})
            self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            told = [m["content"] for m in mock.messages("InjectUserMessage")][-1]
            self.assertIn("I pressed Confirm and it was applied", told)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1, before[2], before[3]))

    def test_the_key_never_appears_in_any_message_response_or_log(self):
        script = {"hello": [("text", "assistant", "Hi."), ("done",)]}
        with MockDeepgram(script, expected_auth=f"Token {KEY}") as mock:
            ws, _ = self.open_session(mock)
            ws.send_json({"type": "user_text", "text": "hello"})
            self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
        with MockDeepgram({}, expected_auth="Token some-other-key") as wrong:  # Deepgram refuses: the failure must not echo the key
            assistant_config.deepgram_agent_url = wrong.url
            t = self.ticket().json()["ticket"]
            with self.client.websocket_connect("/assistant/ws") as ws:
                ws.send_json({"type": "auth", "ticket": t})
                msgs = self.collect(ws, lambda m: m.get("type") == "closed")
            self.assertEqual(msgs[0]["code"], "upstream_unavailable")
            self.assertEqual(msgs[-1]["reason"], "upstream_unavailable")
        everything = "\n".join(self.bodies + self.logs.lines)
        self.assertNotIn(KEY, everything)
        self.assertNotIn("SENTINEL", everything)
        self.assertEqual(assistant_config.deepgram_api_key, KEY)

    def test_a_ticket_works_once_and_a_bad_or_expired_one_is_refused(self):
        with MockDeepgram() as mock:
            assistant_config.deepgram_agent_url = mock.url
            t = self.ticket().json()["ticket"]
            with self.client.websocket_connect("/assistant/ws") as ws:
                ws.send_json({"type": "auth", "ticket": t})
                self.assertEqual(self.recv(ws)["type"], "ready")
            with self.client.websocket_connect("/assistant/ws") as ws:
                ws.send_json({"type": "auth", "ticket": t})
                self.assertEqual(self.recv(ws)["code"], "bad_ticket")
            with self.client.websocket_connect("/assistant/ws") as ws:
                ws.send_json({"type": "auth", "ticket": "made-up"})
                self.assertEqual(self.recv(ws)["code"], "bad_ticket")
            t2 = self.ticket().json()["ticket"]
            for ticket in service._tickets.values():
                ticket.expires = time.monotonic() - 1
            with self.client.websocket_connect("/assistant/ws") as ws:
                ws.send_json({"type": "auth", "ticket": t2})
                self.assertEqual(self.recv(ws)["code"], "bad_ticket")
            t3 = self.ticket().json()["ticket"]
            with self.assertRaises(Exception):  # a page on another origin is closed before it is accepted
                with self.client.websocket_connect("/assistant/ws", headers={"Origin": "https://evil.example"}):
                    pass
            self.assertIn(t3, service._tickets)

    def test_the_monthly_cap_ends_a_running_session_and_usage_is_saved(self):
        self.client.put("/assistant/settings", json={"monthlyMinuteCap": 1})
        with SessionLocal() as db:
            db.add(AssistantUsage(workspace_id=self.owner_id, month=service.month_key(), seconds=59.6))
            db.commit()
        with MockDeepgram() as mock:
            ws, ready = self.open_session(mock)
            self.assertLessEqual(ready["remainingSeconds"], 1)
            msgs = self.collect(ws, lambda m: m.get("type") == "closed")
            self.assertEqual(msgs[-1]["reason"], "cap_reached")
        with SessionLocal() as db:
            self.assertGreaterEqual(db.get(AssistantUsage, (self.owner_id, service.month_key())).seconds, 60)
        r = self.ticket()
        self.assertEqual(r.status_code, 429)

    def test_a_session_cannot_start_when_the_cap_is_already_used(self):
        self.client.put("/assistant/settings", json={"monthlyMinuteCap": 1})
        with MockDeepgram() as mock:
            assistant_config.deepgram_agent_url = mock.url
            t = self.ticket().json()["ticket"]
            with SessionLocal() as db:  # the cap fills up between the ticket and the connection
                db.add(AssistantUsage(workspace_id=self.owner_id, month=service.month_key(), seconds=61))
                db.commit()
            with self.client.websocket_connect("/assistant/ws") as ws:
                ws.send_json({"type": "auth", "ticket": t})
                msgs = self.collect(ws, lambda m: m.get("type") == "closed")
            self.assertEqual(msgs[0]["code"], "cap_reached")
            self.assertEqual(len(mock.received), 0, "Deepgram must not be contacted once the cap is reached")

    def test_the_session_ends_after_the_idle_timeout_and_activity_resets_it(self):
        with SessionLocal() as db:
            service.get_settings_row(db, self.owner_id).idle_timeout_seconds = 1
            db.commit()
        script = {"hello": [("text", "assistant", "Hi."), ("done",)]}
        with MockDeepgram(script) as mock:
            ws, ready = self.open_session(mock)
            self.assertEqual(ready["idleTimeoutSeconds"], 1)
            started = time.monotonic()
            for _ in range(3):  # three 0.5 s gaps with activity in between: 1.5 s total, longer than the timeout
                time.sleep(0.5)
                ws.send_json({"type": "activity"})
            self.assertGreaterEqual(time.monotonic() - started, 1.5)
            msgs = self.collect(ws, lambda m: m.get("type") == "closed")
            self.assertEqual(msgs[-1]["reason"], "idle")
            self.assertGreaterEqual(time.monotonic() - started, 2.0)

    def test_voice_audio_is_relayed_both_ways_and_typing_mode_drops_microphone_audio(self):
        script = {"hello": [("audio",), ("done",)]}
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock, mode="voice")
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_json({"type": "user_text", "text": "hello"})
            seen = self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            self.assertTrue([m for m in seen if "_bytes" in m])
            self.assertEqual(mock.audio_frames, 2)
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock, mode="text")
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_json({"type": "user_text", "text": "hello"})
            self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            self.assertEqual(mock.audio_frames, 0)
            self.assertNotIn("greeting", mock.settings()["agent"])
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock, mode="voice")
            self.assertIn("greeting", mock.settings()["agent"])

    def test_transcripts_are_stored_only_when_history_is_on_and_audio_never(self):
        script = {"hello": [("text", "assistant", "Hi there."), ("done",)]}
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock)
            ws.send_json({"type": "user_text", "text": "hello"})
            self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
        with SessionLocal() as db:
            self.assertEqual(db.query(AssistantMessage).count(), 0)
        self.client.put("/assistant/settings", json={"historyEnabled": True})
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock, mode="voice")
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "user_text", "text": "hello"})
            self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
        rows = self.client.get("/assistant/history").json()
        self.assertEqual([(r["role"], r["text"]) for r in rows], [("user", "hello"), ("assistant", "Hi there.")])
        self.assertEqual(self.client.delete("/assistant/history").status_code, 204)
        self.assertEqual(self.client.get("/assistant/history").json(), [])
        self.assertEqual([c.name for c in AssistantMessage.__table__.columns if "audio" in c.name], [])

    def test_a_context_change_updates_the_prompt_and_ignores_ids_from_other_workspaces(self):
        other = TestClient(app, headers=ORIGIN)
        self.addCleanup(other.close)
        oid = other.post("/auth", json={"action": "register", "email": "other@example.com", "fullName": "Other", "password": PASSWORD}).json()["user"]["id"]
        with SessionLocal() as db:
            foreign = models.Campaign(user_id=oid, name="Foreign campaign", status="draft")
            db.add(foreign)
            db.commit()
            foreign_id = foreign.id
        with MockDeepgram() as mock:
            ws, _ = self.open_session(mock, page={"path": "/leads", "leadId": self.ids["lead"], "campaignId": foreign_id})
            self.assertIn("Priya Nair", mock.settings()["agent"]["think"]["prompt"])
            self.assertNotIn("Foreign campaign", mock.settings()["agent"]["think"]["prompt"])
            ws.send_json({"type": "context", "page": {"path": "/campaigns", "campaignId": self.ids["campaign"]}})
            deadline = time.monotonic() + 5
            while not mock.messages("UpdatePrompt") and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertIn('the campaign "Fintech push"', mock.messages("UpdatePrompt")[-1]["prompt"])

    def test_a_tool_a_member_may_not_use_is_refused_inside_a_session_too(self):
        mclient, member = self.member_client("member")
        script = {"pause": [("call", "set_account_state", {"account_id": self.ids["account"], "action": "pause"}), ("text", "assistant", "I can't do that."), ("done",)]}
        with MockDeepgram(script) as mock:
            ws, _ = self.open_session(mock, client=mclient)
            ws.send_json({"type": "user_text", "text": "pause the account"})
            seen = self.collect(ws, lambda m: m.get("type") == "agent_audio_done")
            self.assertEqual([m["status"] for m in seen if m.get("type") == "tool"], ["running", "failed"])
            self.assertFalse([m for m in seen if m.get("type") == "proposal"])
            self.assertIn("does not allow", json.loads(mock.call_results[0]["content"])["error"])
        self.assertEqual([a.status for a in self.audits("set_account_state")], ["denied"])


if __name__ == "__main__":
    unittest.main()
