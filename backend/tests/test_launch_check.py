"""The launch check: every blocker has its own message and says which step of the builder fixes it; AI messages must be written and approved first;
the dry run leaves out do-not-contact and excluded people."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timezone
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
from app import database, drafts, models, planner, publishing_models  # noqa: F401
from app.assistant.config import assistant_config
from app.config import settings
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class LaunchCase(unittest.TestCase):
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
            self.lead_ids = {}
            for name in ("ada", "bo"):
                lead = models.Lead(user_id=owner.id, first_name=name, company="Acme", linkedin_url=f"https://www.linkedin.com/in/{name}/")
                db.add(lead)
                lead_list.leads.append(lead)
                db.flush()
                self.lead_ids[name] = lead.id
            db.commit()
            self.owner_id, self.account_id, self.list_id = owner.id, account.id, lead_list.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        for patcher in (patch.object(settings, "ai_provider", "template"), patch.object(assistant_config, "deepgram_api_key", "")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def make(self, steps, **fields):
        body = {"action": "create", "name": "C", "timezone": "UTC", "steps": steps, **fields}
        r = self.client.post("/campaigns", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def check(self, campaign_id):
        return self.client.get(f"/campaigns/{campaign_id}/launch-check").json()

    def kinds(self, campaign_id):
        return {p["kind"]: p["step"] for p in self.check(campaign_id)["problems"]}


class CheckTest(LaunchCase):
    def test_a_blank_campaign_lists_every_blocker_with_the_step_that_fixes_it(self):
        cid = self.make([])
        # the builder opens with no senders and no leads; the check, not the builder, gates launch
        self.assertEqual(self.kinds(cid), {"no_connected_account": "senders", "empty_lead_list": "leads", "empty_message": "sequence"})  # the starter sequence has empty messages
        problems = self.check(cid)["problems"]
        self.assertTrue(all(p["message"] for p in problems))
        self.assertFalse(self.check(cid)["ready"])

    def test_a_complete_plain_campaign_is_ready(self):
        cid = self.make([{"type": "connection_request", "order": 0, "message": "hi {{first_name}}"}], accountId=self.account_id, leadListId=self.list_id)
        self.assertEqual(self.check(cid), {"ready": True, "problems": []})

    def test_an_empty_message_blocks_unless_the_step_is_ai_assisted(self):
        steps = [{"type": "connection_request", "order": 0, "message": "hi"}, {"type": "message", "order": 1, "message": ""}]
        cid = self.make(steps, accountId=self.account_id, leadListId=self.list_id)
        self.assertEqual(self.kinds(cid), {"empty_message": "sequence"})

    def test_ai_messages_must_be_written_then_approved_before_launch(self):
        steps = [{"type": "connection_request", "order": 0, "message": "hi"}, {"type": "message", "order": 1, "message": "", "aiConfig": {"mode": "ai"}}]
        cid = self.make(steps, accountId=self.account_id, leadListId=self.list_id)
        self.assertEqual(self.kinds(cid), {"ai_drafts_missing": "review"})
        self.assertIn("2 AI messages not written yet", self.check(cid)["problems"][0]["message"])
        estimate = self.client.post(f"/campaigns/{cid}/drafts/estimate").json()
        self.client.post(f"/campaigns/{cid}/drafts/generate", json={"confirmedCount": estimate["count"]})
        drafts.wait_for_job(cid)
        self.assertEqual(self.kinds(cid), {"ai_drafts_unreviewed": "review"})
        self.assertIn("2 AI messages are waiting for your review", self.check(cid)["problems"][0]["message"])
        self.client.post(f"/campaigns/{cid}/drafts/approve", json={"all": True})
        self.assertEqual(self.check(cid), {"ready": True, "problems": []})

    def test_launching_through_the_api_refuses_with_the_same_problems(self):
        cid = self.make([])
        r = self.client.post("/campaigns", json={"action": "update", "id": cid, "status": "active"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual({d["type"] for d in r.json()["detail"]}, {"launch.no_connected_account", "launch.empty_lead_list", "launch.empty_message"})

    def test_a_week_schedule_with_a_valid_zone_passes_and_an_unknown_zone_is_a_blocker(self):
        steps = [{"type": "connection_request", "order": 0, "message": "hi"}]
        week = {d: {"on": True, "start": "08:00", "end": "20:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        ok = self.make(steps, accountId=self.account_id, leadListId=self.list_id, weekSchedule=week)
        self.assertTrue(self.check(ok)["ready"])
        with SessionLocal() as db:
            db.get(models.Campaign, ok).timezone = "Nowhere/Land"
            db.commit()
        self.assertEqual(self.kinds(ok), {"invalid_working_hours": "review"})


class DryRunTest(LaunchCase):
    def test_the_dry_run_leaves_out_do_not_contact_and_excluded_people_with_the_reason(self):
        steps = [{"type": "connection_request", "order": 0, "message": "hi"}]
        cid = self.make(steps, accountId=self.account_id, leadListId=self.list_id, exclusions={"existing_connections": True})
        with SessionLocal() as db:
            db.add(models.DoNotContact(user_id=self.owner_id, kind="person", key="linkedin.com/in/ada", name="", source="manual"))
            db.get(models.Lead, self.lead_ids["bo"]).connection_degree = 1
            db.commit()
            plans = planner.plan_campaign(db, db.get(models.Campaign, cid), datetime.now(timezone.utc))
        reasons = {p.lead_name: p.skip_reason for p in plans}
        self.assertEqual(reasons["ada"], "On the do-not-contact list.")
        self.assertEqual(reasons["bo"], "Left out by this campaign's settings: already a connection.")


if __name__ == "__main__":
    unittest.main()
