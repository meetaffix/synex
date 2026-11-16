"""The dashboard funnel, per-campaign numbers and exports are counted from real rows and reconcile with them."""
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
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, models, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)
NOW = datetime.now(timezone.utc)


class FunnelTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=10)
            db.add(account)
            db.flush()
            self.camp = models.Campaign(user_id=owner.id, name="=Evil, Campaign", status="active", account_id=account.id)
            self.other = models.Campaign(user_id=owner.id, name="Quiet", status="paused", account_id=account.id)
            db.add_all([self.camp, self.other])
            db.flush()
            # five leads in the campaign: all contacted; three accepted; two replied; one interested (by label); one more lead only enrolled
            for i in range(6):
                lead = models.Lead(user_id=owner.id, first_name=f"L{i}", linkedin_url=f"https://www.linkedin.com/in/l{i}/",
                                   connected_at=NOW - timedelta(days=1) if i < 3 else None)
                db.add(lead)
                db.flush()
                run = models.SequenceRun(user_id=owner.id, campaign_id=self.camp.id, lead_id=lead.id, status="running")
                db.add(run)
                db.flush()
                if i < 5:
                    db.add(models.AgentTask(account_id=account.id, sequence_run_id=run.id, type="send_invite", status="done", idempotency_key=f"k{i}", payload={},
                                            committed_at=NOW - timedelta(days=2)))
                if i in (0, 1):
                    convo = models.Conversation(user_id=owner.id, lead_id=lead.id, campaign_id=self.camp.id, account_id=account.id,
                                                interest="meeting_booked" if i == 0 else None, last_message_at=NOW - timedelta(hours=3))
                    db.add(convo)
                    db.flush()
                    db.add(models.Message(conversation_id=convo.id, direction="inbound", body="hi", sent_at=NOW - timedelta(hours=3)))
            db.commit()
            self.owner_id, self.camp_id, self.other_id = owner.id, self.camp.id, self.other.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def stages(self, **params):
        return {s["key"]: s for s in self.client.get("/dashboard/funnel", params=params).json()["stages"]}

    def test_the_funnel_counts_each_stage_from_the_rows_and_gives_each_steps_share_of_the_previous(self):
        s = self.stages()
        self.assertEqual([s[k]["count"] for k in ("leads", "contacted", "accepted", "replied", "interested")], [6, 5, 3, 2, 1])
        self.assertIsNone(s["leads"]["percentOfPrevious"])
        self.assertEqual([s[k]["percentOfPrevious"] for k in ("contacted", "accepted", "replied", "interested")], [83.3, 60.0, 66.7, 50.0])

    def test_a_campaign_filter_and_a_date_filter_narrow_it_and_an_empty_scope_is_all_zero(self):
        self.assertEqual(self.stages(campaignId=self.other_id)["contacted"]["count"], 0)
        self.assertEqual(self.stages(campaignId=self.camp_id)["contacted"]["count"], 5)
        later = (NOW - timedelta(hours=1)).isoformat()
        s = self.stages(**{"from": later})
        self.assertEqual((s["contacted"]["count"], s["replied"]["count"]), (0, 0))  # everything happened before this window
        self.assertEqual(self.stages(**{"from": (NOW - timedelta(days=5)).isoformat()})["contacted"]["count"], 5)

    def test_the_interested_label_from_the_inbox_counts_in_the_summary_too(self):
        data = self.client.get("/dashboard/summary").json()
        self.assertEqual(data["interestedLeads"], 1)
        self.assertEqual(data["replies"], 2)
        self.assertEqual(data["connectionsAccepted"], 3)

    def test_the_campaign_table_has_each_campaigns_numbers_and_percentages_and_no_made_up_zero_rates(self):
        rows = {r["name"]: r for r in self.client.get("/dashboard/campaigns").json()}
        mine = rows["=Evil, Campaign"]
        self.assertEqual((mine["leads"], mine["contacted"], mine["accepted"], mine["replied"], mine["interested"]), (6, 5, 3, 2, 1))
        self.assertEqual((mine["acceptedPercent"], mine["replyPercent"]), (60.0, 66.7))
        self.assertEqual((rows["Quiet"]["acceptedPercent"], rows["Quiet"]["replyPercent"]), (None, None))

    def test_the_exports_are_csv_and_neutralise_a_formula_in_a_campaign_name(self):
        r = self.client.get("/dashboard/export", params={"kind": "campaigns"})
        self.assertEqual(r.headers["content-type"].split(";")[0], "text/csv")
        self.assertIn("'=Evil", r.text)
        self.assertEqual(r.text.splitlines()[0], "campaign,status,leads,contacted,accepted,replied,interested,accepted_percent,reply_percent")
        series = self.client.get("/dashboard/export", params={"kind": "timeseries", "granularity": "day"}).text.splitlines()
        self.assertEqual(series[0], "date,requests,accepted,replies")
        self.assertEqual(sum(int(line.split(",")[1]) for line in series[1:]), 5)  # the daily requests add up to the invitations sent
        self.assertEqual(self.client.get("/dashboard/export", params={"kind": "accounts"}).text.splitlines()[0], "account_id,requests_sent,accepted_percent,leads_contacted,reply_percent")

    def test_a_workspace_with_nothing_shows_zeros_not_errors(self):
        with SessionLocal() as db:
            db.query(models.AgentTask).delete()
            db.query(models.Message).delete()
            db.query(models.Conversation).delete()
            db.query(models.SequenceRun).delete()
            db.commit()
        self.assertEqual([s["count"] for s in self.client.get("/dashboard/funnel").json()["stages"]], [0, 0, 0, 0, 0])
        self.assertEqual(self.client.get("/dashboard/timeseries").json(), {"points": []})


if __name__ == "__main__":
    unittest.main()
