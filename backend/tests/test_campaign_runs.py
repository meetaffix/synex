"""A launched campaign's page lists every lead's progress: who they are, which step they are on, and what happens next. Owner only."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import models
from app.database import Base, SessionLocal, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "Strong-Test-Password!"


class CampaignRunsTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Olive Owner", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        self.uid = r.json()["user"]["id"]
        with SessionLocal() as db:
            campaign = models.Campaign(user_id=self.uid, name="Founders", status="active")
            db.add(campaign)
            db.flush()
            invite = models.CampaignStep(campaign_id=campaign.id, type="connection_request", order=0, message="Hi")
            wait = models.CampaignStep(campaign_id=campaign.id, type="wait", order=1, delay_hours=48)
            db.add_all([invite, wait])
            ada = models.Lead(user_id=self.uid, first_name="Ada", last_name="Lovelace", headline="Mathematician", linkedin_url="https://www.linkedin.com/in/ada")
            bo = models.Lead(user_id=self.uid, first_name="Bo", last_name="Bee", linkedin_url="https://www.linkedin.com/in/bo")
            db.add_all([ada, bo])
            db.flush()
            soon = datetime.now(timezone.utc) + timedelta(hours=2)
            db.add_all([
                models.SequenceRun(user_id=self.uid, campaign_id=campaign.id, lead_id=ada.id, current_step_id=wait.id, status="waiting_connection", next_action_at=soon),
                models.SequenceRun(user_id=self.uid, campaign_id=campaign.id, lead_id=bo.id, current_step_id=invite.id, status="stopped", stop_reason="replied"),
            ])
            db.commit()
            self.campaign_id = campaign.id

    def test_every_lead_shows_its_step_status_and_next_action(self):
        r = self.client.get(f"/campaigns/{self.campaign_id}/runs")
        self.assertEqual(r.status_code, 200, r.text)
        rows = {row["leadName"]: row for row in r.json()}
        self.assertEqual(set(rows), {"Ada Lovelace", "Bo Bee"})
        ada = rows["Ada Lovelace"]
        self.assertEqual((ada["status"], ada["stepType"], ada["stepOrder"], ada["headline"]), ("waiting_connection", "wait", 1, "Mathematician"))
        self.assertTrue(ada["nextActionAt"])
        bo = rows["Bo Bee"]
        self.assertEqual((bo["status"], bo["stopReason"], bo["stepType"]), ("stopped", "replied", "connection_request"))

    def test_people_who_were_already_connections_are_not_counted_as_invited_or_accepted(self):
        with SessionLocal() as db:
            for lead in db.query(models.Lead).all():
                lead.status = "connected"
            camp = db.get(models.Campaign, self.campaign_id)
            camp.lead_list = models.LeadList(user_id=self.uid, name="L", leads=db.query(models.Lead).all())
            db.commit()
        stats = self.client.get(f"/campaigns?id={self.campaign_id}").json()["stats"]
        self.assertEqual((stats["invitesSent"], stats["connected"], stats["acceptanceRate"]), (0, 0, 0.0))

    def test_another_account_cannot_read_it(self):
        other = TestClient(app, headers=ORIGIN)
        self.addCleanup(other.close)
        other.post("/auth", json={"action": "register", "email": "other@example.com", "fullName": "Otto Other", "password": PASSWORD})
        self.assertEqual(other.get(f"/campaigns/{self.campaign_id}/runs").status_code, 404)


class EditRunningCampaignTest(CampaignRunsTest):
    """A running campaign's sequence can be edited: text and new steps go through, a step people are on cannot be removed, an empty message is refused."""

    def steps(self):
        return self.client.get(f"/campaigns?id={self.campaign_id}").json()["steps"]

    def update(self, steps):
        return self.client.post("/campaigns", json={"action": "update", "id": self.campaign_id, "steps": steps})

    def test_the_text_of_a_step_can_change_while_running(self):
        steps = self.steps()
        steps[0]["message"] = "Hello there"
        r = self.update(steps)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.steps()[0]["message"], "Hello there")

    def test_a_step_people_are_on_cannot_be_removed(self):
        steps = [s for s in self.steps() if s["type"] != "wait"]  # Ada is on the wait step
        r = self.update(steps)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("on the wait step", r.json()["detail"])
        self.assertEqual(len(self.steps()), 2)

    def test_an_empty_message_is_refused_on_a_running_campaign(self):
        steps = self.steps() + [{"id": "new-1", "type": "message", "order": 2, "message": "", "delayHours": None, "aiConfig": None, "parentStepId": None, "branchCondition": None, "config": None}]
        r = self.update(steps)
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(len(self.steps()), 2)



class WhyNothingIsHappeningTest(CampaignRunsTest):
    """A launched campaign says why it is not sending: the worker is down, or the work is simply not due yet."""

    def monitor(self):
        r = self.client.get(f"/campaigns?id={self.campaign_id}&monitor=1")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def make_due(self):
        with SessionLocal() as db:
            for run in db.query(models.SequenceRun).filter_by(campaign_id=self.campaign_id, status="waiting_connection"):
                run.next_action_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()

    def test_work_that_is_not_due_yet_has_no_warning(self):
        self.assertIsNone(self.monitor()["waiting"])

    def test_the_timeline_lists_who_is_next_and_when(self):
        body = self.monitor()
        self.assertEqual([u["leadName"] for u in body["upcoming"]], ["Ada Lovelace"])
        self.assertEqual(body["upcoming"][0]["step"], "wait")
        self.assertEqual(body["recent"], [])

    def test_due_work_with_no_worker_says_to_start_it(self):
        self.make_due()
        body = self.monitor()
        self.assertFalse(body["workerRunning"])
        self.assertEqual(body["waiting"]["code"], "worker_down")
        self.assertIn("python -m app.outreach_worker", body["waiting"]["message"])


if __name__ == "__main__":
    unittest.main()
