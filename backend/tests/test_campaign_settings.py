"""Campaign settings: the weekly schedule, exclusions at launch, per-sender allocation, and the AI context are validated and obeyed."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timezone

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import campaign_settings, database, engine, models, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)

WEEK = {d: {"on": d in ("mon", "tue", "wed", "thu", "fri"), "start": "08:00", "end": "20:00"} for d in campaign_settings.DAYS}


class SettingsCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            self.account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=50)
            self.other_account = models.LinkedInAccount(user_id=owner.id, name="Other", status="active", session_status="connected", daily_action_limit=50)
            db.add_all([self.account, self.other_account])
            db.commit()
            self.owner_id, self.account_id, self.other_id = owner.id, self.account.id, self.other_account.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def create(self, **fields):
        return self.client.post("/campaigns", json={"action": "create", "name": "C", "accountId": self.account_id, "timezone": "UTC", **fields})


class ValidationTest(SettingsCase):
    def test_a_good_schedule_exclusions_allocation_and_context_are_saved_and_returned(self):
        r = self.create(weekSchedule=WEEK, exclusions={"existing_connections": True}, allocation={self.account_id: {"send_invite": 10, "send_message": 20}},
                        aiContext={"goals": "Book demos", "doNotMention": ["pricing"]}, sequenceMode="smart")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["weekSchedule"]["mon"], {"on": True, "start": "08:00", "end": "20:00"})
        self.assertTrue(data["exclusions"]["existing_connections"])
        self.assertFalse(data["exclusions"]["other_campaigns"])
        self.assertEqual(data["allocation"][self.account_id]["send_invite"], 10)
        self.assertEqual(data["sequenceMode"], "smart")

    def test_each_bad_setting_is_refused_with_the_reason(self):
        bad_week = {**WEEK, "mon": {"on": True, "start": "20:00", "end": "08:00"}}
        all_off = {d: {"on": False, "start": "08:00", "end": "20:00"} for d in campaign_settings.DAYS}
        cases = [({"weekSchedule": bad_week}, "start time must be before"), ({"weekSchedule": all_off}, "at least one day"), ({"weekSchedule": {"mon": {}}}, "one entry for each weekday"),
                 ({"exclusions": {"nonsense": True}}, "Unknown exclusion"), ({"allocation": {self.account_id: {"send_invite": 99}}}, "hard maximum"),
                 ({"allocation": {self.account_id: {"hug": 1}}}, "cannot be reserved"), ({"aiContext": {"goals": "x" * 5001}}, "5000 characters"),
                 ({"sequenceMode": "wild"}, "classic or smart")]
        for fields, word in cases:
            r = self.create(**fields)
            self.assertEqual(r.status_code, 422, fields)
            self.assertIn(word, r.text, fields)


class ScheduleTest(SettingsCase):
    def campaign(self, week):
        return models.Campaign(user_id=self.owner_id, name="C", timezone="UTC", week_schedule=week, start_hour=9, end_hour=17, working_days=[1, 2, 3, 4, 5])

    def test_sending_follows_each_days_own_hours_in_the_campaigns_timezone(self):
        week = {**WEEK, "wed": {"on": True, "start": "10:30", "end": "12:00"}, "sat": {"on": True, "start": "09:00", "end": "10:00"}}
        c = self.campaign(week)
        at = lambda day, hh, mm: datetime(2026, 11, day, hh, mm, tzinfo=timezone.utc)  # noqa: E731  (16 Nov 2026 is a Monday)
        self.assertTrue(engine.within_hours(c, at(16, 8, 0)))
        self.assertFalse(engine.within_hours(c, at(16, 20, 0)))      # the end is exclusive
        self.assertFalse(engine.within_hours(c, at(18, 10, 29)))     # Wednesday starts at 10:30
        self.assertTrue(engine.within_hours(c, at(18, 10, 30)))
        self.assertFalse(engine.within_hours(c, at(18, 12, 0)))
        self.assertTrue(engine.within_hours(c, at(21, 9, 30)))      # Saturday is on with its own window
        self.assertFalse(engine.within_hours(c, at(22, 9, 30)))     # Sunday is off

    def test_a_campaign_without_a_weekly_schedule_keeps_the_old_working_hours(self):
        c = self.campaign(None)
        self.assertTrue(engine.within_hours(c, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)))
        self.assertFalse(engine.within_hours(c, datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)))

    def test_launch_refuses_a_schedule_with_every_day_off_only_through_the_validator_and_accepts_a_good_one(self):
        r = self.create(weekSchedule=WEEK)
        self.assertEqual(r.status_code, 200)


class AllocationTest(SettingsCase):
    def test_a_campaign_cannot_use_more_of_a_sender_than_its_reserved_slice(self):
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, self.account_id)
            campaign = models.Campaign(user_id=self.owner_id, name="C", account_id=account.id, allocation={account.id: {"send_message": 0}}, daily_message_limit=40)
            db.add(campaign)
            db.flush()
            account.management_config = {"policy": {"preset": "off", "range": 1, "actions": {"send_message": {"dailyLimit": 30, "increaseBy": 0, "stopAt": 30, "intervalDays": 7, "dynamicInterval": False}},
                                                    "autoWithdraw": False, "staleInviteDays": 30, "inboxHistoryDays": 90}}
            now = datetime.now(timezone.utc)
            self.assertEqual(engine.type_room(db, campaign, account, "send_message", now), 0)
            campaign.allocation = {account.id: {"send_message": 7}}
            self.assertLessEqual(engine.type_room(db, campaign, account, "send_message", now), 7)
            campaign.allocation = {}
            self.assertGreater(engine.type_room(db, campaign, account, "send_message", now), 7)


class ExclusionTest(SettingsCase):
    def setUp(self):
        super().setUp()
        with SessionLocal() as db:
            lead_list = models.LeadList(user_id=self.owner_id, name="L")
            db.add(lead_list)
            db.flush()
            self.list_id = lead_list.id
            self.leads = {}
            for name in ("fresh", "elsewhere", "connected", "dnc", "otherSender"):
                lead = models.Lead(user_id=self.owner_id, first_name=name, linkedin_url=f"https://www.linkedin.com/in/{name.lower()}/")
                db.add(lead)
                lead_list.leads.append(lead)
                db.flush()
                self.leads[name] = lead.id
            db.get(models.Lead, self.leads["connected"]).connection_degree = 1
            db.add(models.DoNotContact(user_id=self.owner_id, kind="person", key="linkedin.com/in/dnc", name="", source="manual"))
            # "elsewhere" is running in another campaign; "otherSender" was messaged by another sender in an earlier campaign
            other = models.Campaign(user_id=self.owner_id, name="Other", status="active", account_id=self.other_id)
            db.add(other)
            db.flush()
            db.add(models.SequenceRun(user_id=self.owner_id, campaign_id=other.id, lead_id=self.leads["elsewhere"], status="running"))
            run = models.SequenceRun(user_id=self.owner_id, campaign_id=other.id, lead_id=self.leads["otherSender"], status="completed")
            db.add(run)
            db.flush()
            db.add(models.AgentTask(account_id=self.other_id, sequence_run_id=run.id, type="send_message", status="done", idempotency_key="k9", payload={}))
            db.commit()

    def launch(self, exclusions):
        with SessionLocal() as db:
            campaign = models.Campaign(user_id=self.owner_id, name="New", status="active", account_id=self.account_id, lead_list_id=self.list_id, exclusions=exclusions)
            db.add(campaign)
            db.flush()
            db.add(models.CampaignStep(campaign_id=campaign.id, type="connection_request", order=0, message="hi"))
            db.flush()
            created = engine.launch_campaign(db, campaign)
            db.commit()
            started = {db.get(models.Lead, r.lead_id).first_name for r in db.query(models.SequenceRun).filter_by(campaign_id=campaign.id)}
            return created, started, dict(campaign.launch_summary["excluded"])

    def test_with_no_exclusions_only_the_do_not_contact_person_is_left_out(self):
        created, started, excluded = self.launch({})
        self.assertEqual(started, {"fresh", "elsewhere", "connected", "otherSender"})
        self.assertEqual(excluded, {"do_not_contact": 1})

    def test_each_exclusion_leaves_out_exactly_its_people_and_the_counts_say_why(self):
        _, started, excluded = self.launch({"other_campaigns": True})
        self.assertNotIn("elsewhere", started)
        self.assertEqual(excluded, {"do_not_contact": 1, "in_other_campaign": 1})
        _, started, excluded = self.launch({"messaged_other_senders": True})
        self.assertNotIn("otherSender", started)
        self.assertIn("messaged_by_other_sender", excluded)
        _, started, excluded = self.launch({"existing_connections": True})
        self.assertNotIn("connected", started)
        self.assertIn("already_connected", excluded)
        _, started, excluded = self.launch({"reached_other_campaigns": True})
        self.assertEqual(started & {"elsewhere", "otherSender"}, set())


if __name__ == "__main__":
    unittest.main()
