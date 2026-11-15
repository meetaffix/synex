"""The dashboard's summary, time series and per-account feeds count real rows and honour their filters."""
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
from app.deps import get_data_user
from app.main import app

atexit.register(database.engine.dispose)
NOW = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)


def ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


class FeedCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            user = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([user, other])
            db.flush()
            self.user_id, self.other_id = user.id, other.id
            self.acc1 = models.LinkedInAccount(user_id=user.id, name="One")
            self.acc2 = models.LinkedInAccount(user_id=user.id, name="Two")
            self.camp1 = models.Campaign(user_id=user.id, name="C1")
            self.camp2 = models.Campaign(user_id=user.id, name="C2")
            db.add_all([self.acc1, self.acc2, self.camp1, self.camp2])
            db.flush()
            # Four invitations: three from account one (campaign one), one from account two (campaign two).
            self.leads = {}
            for name, account, campaign, sent_days, accepted_days in [
                ("ann", self.acc1, self.camp1, 10, 8), ("bob", self.acc1, self.camp1, 3, None),
                ("cy", self.acc1, self.camp1, 2, 1), ("dee", self.acc2, self.camp2, 2, None)]:
                lead = models.Lead(user_id=user.id, first_name=name, connected_at=ago(accepted_days) if accepted_days else None)
                db.add(lead)
                db.flush()
                run = models.SequenceRun(user_id=user.id, campaign_id=campaign.id, lead_id=lead.id)
                db.add(run)
                db.flush()
                db.add(models.AgentTask(account_id=account.id, sequence_run_id=run.id, type="send_invite", status="done", committed_at=ago(sent_days)))
                self.leads[name] = lead
            # A failed invitation and a message task must not count as invitations sent.
            run = db.query(models.SequenceRun).first()
            db.add(models.AgentTask(account_id=self.acc1.id, sequence_run_id=run.id, type="send_invite", status="failed", committed_at=ago(1)))
            db.add(models.AgentTask(account_id=self.acc1.id, sequence_run_id=run.id, type="send_message", status="done", committed_at=ago(1)))
            # Ann replied one hour after we wrote, was answered 2 hours later, and is interested; cy replied, not answered.
            c1 = models.Conversation(user_id=user.id, lead_id=self.leads["ann"].id, campaign_id=self.camp1.id, account_id=self.acc1.id, status="interested", last_message_at=ago(5))
            c2 = models.Conversation(user_id=user.id, lead_id=self.leads["cy"].id, campaign_id=self.camp1.id, account_id=self.acc1.id, status="active", last_message_at=ago(0.5))
            db.add_all([c1, c2])
            db.flush()
            first = ago(5)
            db.add_all([
                models.Message(conversation_id=c1.id, direction="outbound", body="hi", sent_at=first - timedelta(hours=1)),
                models.Message(conversation_id=c1.id, direction="inbound", body="yes", sent_at=first),
                models.Message(conversation_id=c1.id, direction="outbound", body="great", sent_at=first + timedelta(hours=2)),
                models.Message(conversation_id=c2.id, direction="inbound", body="maybe", sent_at=ago(0.5)),
            ])
            # Another user's data must never appear.
            theirs = models.Lead(user_id=other.id, first_name="x", connected_at=ago(1))
            db.add(theirs)
            db.flush()
            their_campaign = models.Campaign(user_id=other.id, name="theirs")
            their_account = models.LinkedInAccount(user_id=other.id, name="theirs")
            db.add_all([their_campaign, their_account])
            db.flush()
            their_run = models.SequenceRun(user_id=other.id, campaign_id=their_campaign.id, lead_id=theirs.id)
            db.add(their_run)
            db.flush()
            db.add(models.AgentTask(account_id=their_account.id, sequence_run_id=their_run.id, type="send_invite", status="done", committed_at=ago(1)))
            db.commit()
            self.acc1_id, self.acc2_id, self.camp1_id, self.camp2_id = self.acc1.id, self.acc2.id, self.camp1.id, self.camp2.id

        def current_user():
            with SessionLocal() as db:
                return db.get(models.User, self.user_id)

        app.dependency_overrides[get_data_user] = current_user
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def get(self, path, **params):
        response = self.client.get(f"/dashboard/{path}", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class SummaryTest(FeedCase):
    def test_it_counts_only_this_users_real_invitations_acceptances_and_replies(self):
        data = self.get("summary")
        self.assertEqual(data["leadsContacted"], 4)  # the failed invitation and the message task are not counted
        self.assertEqual(data["connectionsAccepted"], 2)
        self.assertEqual(data["replies"], 2)
        self.assertEqual((data["interestedLeads"], data["interestedAnswered"]), (1, 1))
        self.assertEqual(data["medianResponseSeconds"], 7200.0)  # the one answered conversation: 2 hours

    def test_a_date_range_counts_only_what_happened_inside_it(self):
        data = self.get("summary", **{"from": ago(4).isoformat(), "to": NOW.isoformat()})
        self.assertEqual(data["leadsContacted"], 3)  # bob, cy, dee were invited in the last 4 days
        self.assertEqual(data["connectionsAccepted"], 1)  # only cy accepted in that window
        self.assertEqual(data["replies"], 1)  # only cy's reply; ann replied 5 days ago
        self.assertEqual(data["interestedLeads"], 0)  # ann's conversation was 5 days ago

    def test_campaign_and_account_filters_narrow_every_number(self):
        two = self.get("summary", campaignId=self.camp2_id)
        self.assertEqual((two["leadsContacted"], two["connectionsAccepted"], two["replies"]), (1, 0, 0))
        self.assertIsNone(two["medianResponseSeconds"])
        self.assertEqual(self.get("summary", accountId=self.acc2_id)["leadsContacted"], 1)
        self.assertEqual(self.get("summary", accountId=self.acc1_id)["leadsContacted"], 3)

    def test_an_empty_workspace_gives_zeros_and_no_median(self):
        with SessionLocal() as db:
            for model in (models.Message, models.Conversation, models.AgentTask, models.SequenceRun):
                db.query(model).delete()
            db.commit()
        self.assertEqual(self.get("summary"), {"connectionsAccepted": 0, "leadsContacted": 0, "replies": 0, "interestedLeads": 0, "interestedAnswered": 0, "medianResponseSeconds": None})
        self.assertEqual(self.get("timeseries"), {"points": []})
        self.assertEqual(self.get("accounts"), [])


class SeriesAndAccountsTest(FeedCase):
    def test_the_daily_series_has_one_point_per_day_with_the_right_counts_and_no_gaps(self):
        points = self.get("timeseries", granularity="day")["points"]
        by_date = {p["date"]: p for p in points}
        self.assertEqual(len(points), 11)  # from 10 days ago to today, every day present
        self.assertEqual(by_date[ago(10).date().isoformat()]["requests"], 1)
        self.assertEqual(by_date[ago(2).date().isoformat()]["requests"], 2)
        self.assertEqual(by_date[ago(8).date().isoformat()]["accepted"], 1)
        self.assertEqual(by_date[ago(5).date().isoformat()]["replies"], 1)
        self.assertEqual(sum(p["requests"] for p in points), 4)

    def test_the_weekly_series_buckets_start_on_a_monday(self):
        points = self.get("timeseries", granularity="week")["points"]
        self.assertTrue(points)
        for point in points:
            self.assertEqual(datetime.fromisoformat(point["date"]).weekday(), 0)
        self.assertEqual(sum(p["requests"] for p in points), 4)

    def test_per_account_numbers_use_that_accounts_own_leads(self):
        rows = {r["accountId"]: r for r in self.get("accounts")}
        one, two = rows[self.acc1_id], rows[self.acc2_id]
        self.assertEqual((one["requestsSent"], one["leadsContacted"]), (3, 3))
        self.assertEqual(one["acceptedPercent"], 66.7)  # ann and cy of ann, bob, cy
        self.assertEqual(one["replyPercent"], 66.7)  # ann and cy replied
        self.assertEqual((two["requestsSent"], two["acceptedPercent"], two["replyPercent"]), (1, 0.0, 0.0))
        self.assertEqual(set(rows), {self.acc1_id, self.acc2_id})  # the other user's account never appears
        self.assertEqual(len(self.get("accounts", accountId=self.acc2_id)), 1)

    def test_a_bad_granularity_is_refused(self):
        self.assertEqual(self.client.get("/dashboard/timeseries", params={"granularity": "year"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
